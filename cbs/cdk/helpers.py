from os import getenv
from re import match
from sys import modules

import aws_cdk as cdk
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_iam as iam
from aws_cdk import custom_resources as cr
from boto3.dynamodb.types import TypeSerializer
from constructs import Construct

from cbs.cdk.config import CBSConfig
from cbs.core import constants
from cbs.core.types import Partner


def create_resource_name(
    resource_name: str, scope: cdk.Stack = None, environment: str = None
) -> str:
    if environment is None and scope is not None:
        environment = scope.tags.tag_values()["Environment"]
    if scope is None:
        region = getenv("CDK_DEFAULT_REGION", "ca-central-1")
    else:
        region = scope.region
    return f"CBS-{resource_name}-{environment.lower()}-{region}"


def create_inventory_table(
    scope: Construct,
    table_name: str,
    database_management_account: str,
    agent_account: str,
    initialise_data: dict[str, Partner] = None,
) -> dynamodb.Table:
    """Creates a DynamoDB table for storing information about partners
    Returns:
        Table: Partner inventory table
    """
    inventory_table = dynamodb.Table(
        scope,
        table_name,
        partition_key=dynamodb.Attribute(
            name=constants.ACCOUNT_ID, type=dynamodb.AttributeType.STRING
        ),
        sort_key=dynamodb.Attribute(
            name=constants.CBS_ID, type=dynamodb.AttributeType.STRING
        ),
        encryption=dynamodb.TableEncryption.AWS_MANAGED,
        billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
        table_name=table_name,
        point_in_time_recovery=True,
        deletion_protection=True,
        removal_policy=(
            cdk.RemovalPolicy.DESTROY
            if scope._config.Environment == "dev"
            else cdk.RemovalPolicy.RETAIN
        ),
    )

    # Management role for Azure DevOps user to use for writing new partners to DB
    database_management_role = iam.Role(
        scope,
        "DevopsDBRole",
        assumed_by=iam.AccountPrincipal(database_management_account),
    )

    inventory_table.grant_write_data(database_management_role)

    table_initialization_role = iam.Role(
        scope,
        "TableInitializationRole",
        assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
        managed_policies=[
            iam.ManagedPolicy.from_aws_managed_policy_name(
                "service-role/AWSLambdaBasicExecutionRole"
            ),
        ],
    )
    inventory_table.grant_write_data(table_initialization_role)
    inventory_table.grant_write_data(
        iam.AccountPrincipal(account_id=agent_account).with_conditions(
            {
                "StringEquals": {
                    "aws:PrincipalArn": f"arn:aws:iam::{agent_account}:role/TableUpdateRole"
                }
            }
        )
    )

    if initialise_data:
        initialise_data_call = cr.AwsSdkCall(
            service="DynamoDB",
            action="batchWriteItem",
            physical_resource_id=cr.PhysicalResourceId.of(
                table_name + "_initialization"
            ),
            parameters={
                "RequestItems": {
                    table_name: get_batch_items_from_initialize_data(initialise_data)
                },
                "ReturnConsumedCapacity": "TOTAL",
            },
        )

        table_initialization_resource = cr.AwsCustomResource(
            scope,
            "InventoryTableInitializationResource",
            on_update=None,
            on_create=initialise_data_call,
            role=table_initialization_role,
        )
        table_initialization_resource.node.add_dependency(inventory_table)

    return inventory_table


def create_alarm_suppression_table(scope: Construct, table_name: str) -> dynamodb.Table:
    """Creates a DynamoDB table for storing information about partner alarms to be suppressed
    Returns:
        Table: Partner alarm suppression dynamo db table
    """
    alarm_suppression_table = dynamodb.Table(
        scope,
        table_name,
        partition_key=dynamodb.Attribute(
            name=constants.CBS_ID, type=dynamodb.AttributeType.STRING
        ),
        sort_key=dynamodb.Attribute(
            name=constants.ALARM_TYPE, type=dynamodb.AttributeType.STRING
        ),
        time_to_live_attribute=constants.SUPPRESSION_EXPIRY,
        encryption=dynamodb.TableEncryption.AWS_MANAGED,
        billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
        table_name=table_name,
        point_in_time_recovery=True,
        removal_policy=(
            cdk.RemovalPolicy.DESTROY
            if scope._config.Environment == "dev"
            else cdk.RemovalPolicy.RETAIN
        ),
        deletion_protection=True,
    )

    return alarm_suppression_table


def get_batch_items_from_initialize_data(
    initialise_data: dict[str, dict[str, str]]
) -> list[dict[str, dict[str, dict[str, str]]]]:
    """
    Formats a list of partner dictionaries (with values for AccountId/CbsId/Accelerator)
    into a list of Items for the Dynamo BatchWriteItem's API.
    """
    serializer = TypeSerializer()

    return [
        {
            "PutRequest": {
                "Item": {
                    constants.ACCOUNT_ID: serializer.serialize(partner),
                    constants.CBS_ID: serializer.serialize(
                        initialise_data[partner][constants.CBS_ID]
                    ),
                    constants.ACCELERATOR: serializer.serialize(
                        initialise_data[partner][constants.ACCELERATOR]
                    ),
                }
            }
        }
        for partner in initialise_data
    ]


def is_pytest() -> bool:
    return "pytest" in modules


def is_valid_iam_role_arn(value: str) -> bool:
    """Checks whether the given value is a valid IAM role ARN"""
    arn_pattern = r"^arn:aws:iam::\d{12}:role/[a-zA-Z0-9+=,.@_-]+$"
    return match(arn_pattern, value) is not None


def is_valid_iam_user_arn(value: str) -> bool:
    """Checks whether the given value is a valid IAM user ARN"""
    arn_pattern = r"^arn:aws:iam::\d{12}:user/[a-zA-Z0-9+=,.@_-]+$"
    return match(arn_pattern, value) is not None


def is_valid_iam_group_arn(value: str) -> bool:
    """Checks whether the given value is a valid IAM group ARN"""
    arn_pattern = r"^arn:aws:iam::\d{12}:group/[a-zA-Z0-9+=,.@_-]+$"
    return match(arn_pattern, value) is not None


def create_or_import_role(
    ctx: cdk.Stack, config: CBSConfig, role_input: str, role_id: str
) -> iam.Role:
    """
    If only an ARN is given, try to import role.
    If a name is provided, try to import role if ImportUsersOrRoles is True
    """
    if is_valid_iam_role_arn(role_input):
        return iam.Role.from_role_arn(scope=ctx, id=role_id, role_arn=role_input)
    elif config.ImportUsersOrRoles:
        return iam.Role.from_role_name(scope=ctx, id=role_id, role_name=role_input)
    else:
        return iam.Role(
            scope=ctx,
            id=role_id,
            role_name=role_input,
            assumed_by=iam.AccountPrincipal(ctx.account),
        )


def create_or_import_user(
    ctx: cdk.Stack, config: CBSConfig, user_input: str, user_id: str
) -> iam.User:
    """
    If only an ARN is given, try to import user.
    If a name is provided, try to import user if ImportUsersOrRoles is True
    """
    if is_valid_iam_user_arn(user_input):
        return iam.User.from_user_arn(scope=ctx, id=user_id, user_arn=user_input)
    elif config.ImportUsersOrRoles:
        return iam.User.from_user_name(scope=ctx, id=user_id, user_name=user_input)
    else:
        raise ValueError("Unable to create IAM user")


def create_or_import_group(
    ctx: cdk.Stack, config: CBSConfig, group_input: str, group_id: str
) -> iam.Group:
    """
    If only an ARN is given, try to import group.
    If a name is provided, try to import group if ImportUsersOrRoles is True
    """
    if is_valid_iam_group_arn(group_input):
        return iam.Group.from_group_arn(scope=ctx, id=group_id, group_arn=group_input)
    elif config.ImportUsersOrRoles:
        return iam.Group.from_group_name(scope=ctx, id=group_id, group_name=group_input)
    else:
        raise ValueError("Unable to create IAM group")
