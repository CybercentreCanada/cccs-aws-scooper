from os import environ
from sys import path

from boto3 import client
from boto3.dynamodb.types import TypeSerializer
from moto import mock_aws
from pytest import fixture

from cbs.core import constants
from cbs.lambdas import PATH
from docs import VERSION

path.append(PATH)


@fixture(autouse=True)
def lambda_environment_variables():
    environ["AWS_LAMBDA_FUNCTION_NAME"] = "test"
    environ["CBS_DEVOPS_ROLE_ARN"] = "arn:aws:iam::123456789012:role/test"
    environ["POWERTOOLS_DEV"] = "true"  # Pretty print logs
    environ["VERSION"] = VERSION


@fixture
def dynamodb():
    with mock_aws():
        yield client("dynamodb", region_name="ca-central-1")


@fixture(autouse=True)
def partner_inventory_table(dynamodb):
    table_name = f"CBS-{constants.INVENTORY_TABLE_NAME}-test-ca-central-1"
    dynamodb.create_table(
        TableName=table_name,
        KeySchema=[
            {"AttributeName": constants.ACCOUNT_ID, "KeyType": "HASH"},
            {"AttributeName": constants.CBS_ID, "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": constants.ACCOUNT_ID, "AttributeType": "S"},
            {"AttributeName": constants.CBS_ID, "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    serializer = TypeSerializer()
    dynamodb.put_item(
        TableName=table_name,
        Item={
            constants.ACCOUNT_ID: serializer.serialize("222222222222"),
            constants.CBS_ID: serializer.serialize("CBS-AWS-TEST"),
            constants.ORG_ID: serializer.serialize("o-test"),
            constants.ACCELERATOR: serializer.serialize("lza"),
            constants.DEPLOYED: serializer.serialize(True),
            constants.VPC_CUSTOM_FIELDS: serializer.serialize(
                ",".join(constants.DEFAULT_VPC_FLOW_LOG_FIELDS)
            ),
        },
    )
    environ["INVENTORY_TABLE_NAME"] = table_name
