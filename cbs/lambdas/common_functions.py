from datetime import datetime
from json import JSONEncoder
from os import getenv
from typing import TYPE_CHECKING, Any, TypeVar

from aws_lambda_powertools import Logger
from boto3 import client, resource
from boto3.dynamodb.types import TypeDeserializer, TypeSerializer
from botocore.client import BaseClient
from botocore.exceptions import BotoCoreError, ClientError

try:
    from core import constants
    from core.utils.paginate import paginate
    from core.utils.sts import assume_role
except ModuleNotFoundError:
    from cbs.core import constants
    from cbs.core.utils.paginate import paginate
    from cbs.core.utils.sts import assume_role

if TYPE_CHECKING:
    from cbs.lambdas.transport.cbs_event import CBSEvent

logger = Logger(service=__name__)
DynamoDB = TypeVar("DynamoDB", bound=resource)


def read_from_s3(
    bucket_name: str,
    object_key: str,
    s3_client: BaseClient = client("s3"),
) -> str:
    """Read given object from given bucket and return its contents."""
    return s3_client.get_object(
        Bucket=bucket_name,
        Key=object_key,
    )["Body"].read()


def write_to_s3(
    body: bytes,
    bucket_name: str,
    object_key: str,
    s3_client: BaseClient = client("s3"),
) -> None:
    """Write given bytes to given bucket."""
    s3_client.put_object(
        Body=body,
        Bucket=bucket_name,
        Key=object_key,
    )


def is_bucket_empty(
    bucket_name: str | None, s3_client: BaseClient = client("s3")
) -> bool:
    """Check if given bucket is empty."""
    if bucket_name is None:
        return True

    response = s3_client.list_objects_v2(Bucket=bucket_name, MaxKeys=1)
    return "Contents" not in response


def get_partner_inventory_table_item(key: str, cbs_event: "CBSEvent") -> Any:
    """Get given attribute's value from partner inventory table."""
    if devops_role_arn := getenv("CBS_DEVOPS_ROLE_ARN"):
        session = assume_role(
            role_arn=devops_role_arn,
            role_session_name="GetPartnerInventoryTableItem",
        )
        dynamodb_client = session.client("dynamodb")
    else:
        dynamodb_client = client("dynamodb")

    type_serializer = TypeSerializer()
    response = dynamodb_client.get_item(
        TableName=getenv("INVENTORY_TABLE_NAME"),
        Key={
            constants.ACCOUNT_ID: type_serializer.serialize(
                cbs_event.partner_account_id
            ),
            constants.CBS_ID: type_serializer.serialize(cbs_event.cbs_id),
        },
    )
    if "Item" in response:
        attribute = response["Item"].get(key)

        if attribute is not None:
            return TypeDeserializer().deserialize(attribute)


def update_partner_inventory_table(key: str, value: Any, cbs_event: "CBSEvent") -> None:
    """Update given partner's inventory table entry with given key-value pair."""
    logger.info(
        "Updating %s's DynamoDB '%s' entry to '%s'",
        cbs_event.cbs_id,
        key,
        str(value),
    )

    if devops_role_arn := getenv("CBS_DEVOPS_ROLE_ARN"):
        session = assume_role(
            role_arn=devops_role_arn,
            role_session_name="UpdatePartnerInventoryTableItem",
        )
        dynamodb_client = session.client("dynamodb")
    else:
        dynamodb_client = client("dynamodb")

    inventory_table_name = getenv("INVENTORY_TABLE_NAME")
    type_serializer = TypeSerializer()
    response = dynamodb_client.get_item(
        TableName=inventory_table_name,
        Key={
            constants.ACCOUNT_ID: type_serializer.serialize(
                cbs_event.partner_account_id
            ),
            constants.CBS_ID: type_serializer.serialize(cbs_event.cbs_id),
        },
    )

    if "Item" in response:
        try:
            dynamodb_client.update_item(
                TableName=inventory_table_name,
                Key={
                    constants.ACCOUNT_ID: {"S": cbs_event.partner_account_id},
                    constants.CBS_ID: {"S": cbs_event.cbs_id},
                },
                UpdateExpression="set #fn = :val1",
                ExpressionAttributeNames={"#fn": key},
                ExpressionAttributeValues={":val1": type_serializer.serialize(value)},
            )
            logger.info(
                "Successfully updated %s's '%s' value to '%s'",
                cbs_event.cbs_id,
                key,
                str(value),
            )
        except BotoCoreError:
            logger.exception(
                "Failed to update %s's '%s' value to '%s'",
                cbs_event.cbs_id,
                key,
                str(value),
            )
            raise
    else:
        logger.error("Failed to find '%s' in DynamoDB table", cbs_event.cbs_id)
        raise LookupError(f"Failed to find '{cbs_event.cbs_id}' in DynamoDB table")


def trigger_codepipeline(
    name: str,
    client_request_token: str = "TriggeringCodePipeline",
    codepipeline_client: BaseClient = client("codepipeline"),
) -> None:
    """Trigger given CodePipeline execution."""
    codepipeline_client.start_pipeline_execution(
        name=name, clientRequestToken=client_request_token
    )


def get_all_accounts(org_client: BaseClient) -> list[str]:
    """Get list of all accounts within organization."""
    try:
        return paginate(
            client=org_client,
            command="list_accounts",
            array="Accounts",
            logger=logger,
        )
    except ClientError:
        return []


def is_supported_workload(object_key: str) -> bool:
    """Check if `object_key` is a supported workload."""
    for unsupported_workload in constants.UNSUPPORTED_WORKLOADS:
        if unsupported_workload in object_key:
            return False
    return True


class DateTimeEncoder(JSONEncoder):
    """JSON encoder to serialize datetime objects"""

    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return JSONEncoder.default(self, obj)
