from json import dumps
from os import environ
from sys import path

from boto3 import client
from boto3.dynamodb.types import TypeSerializer
from moto import mock_aws
from pytest import fixture, mark

from cbs.core import constants
from cbs.lambdas import PATH
from cbs.lambdas.dlq_triage.sanitize import ObjectKeySanitizer

path.append(f"{PATH}/dlq_triage")

SERIALIZER = TypeSerializer()
OBJECT_KEY_SANITIZER = ObjectKeySanitizer()

TABLE_NAME = "UNKNOWN_WORKLOADS_TABLE_NAME"
TOPIC_NAME = "UNKNOWN_WORKLOADS_TOPIC_ARN"


def create_sqs_event(object_key: str) -> dict:
    return {
        "Records": [
            {
                "eventVersion": "2.0",
                "eventSource": "aws:sqs",
                "awsRegion": "us-east-1",
                "messageId": "059f36b4-87a3-44ab-83d2-661975830a7d",
                "body": dumps(
                    {
                        "cbs_id": constants.CBS_ID,
                        "accelerator": "asea",
                        "object_key": object_key,
                    }
                ),
                "attributes": {"sent_timestamp": 100000000},
            }
        ]
    }


@fixture
def dynamodb():
    with mock_aws():
        yield client("dynamodb")


@fixture
def sns():
    with mock_aws():
        yield client("sns")


@fixture(autouse=True)
def unknown_workloads_table(dynamodb):
    dynamodb.create_table(
        AttributeDefinitions=[
            {"AttributeName": "object_key", "AttributeType": "S"},
        ],
        TableName=TABLE_NAME,
        KeySchema=[
            {"AttributeName": "object_key", "KeyType": "HASH"},
        ],
        BillingMode="PROVISIONED",
        ProvisionedThroughput={"ReadCapacityUnits": 1, "WriteCapacityUnits": 1},
        StreamSpecification={
            "StreamEnabled": False,
        },
        SSESpecification={"Enabled": False},
        Tags=[
            {"Key": "string", "Value": "string"},
        ],
        TableClass="STANDARD",
        DeletionProtectionEnabled=False,
    )
    environ[TABLE_NAME] = TABLE_NAME


@fixture(autouse=True)
def unknown_workloads_topic(sns):
    unknown_workloads_topic_arn = sns.create_topic(Name=TOPIC_NAME)["TopicArn"]
    environ[TOPIC_NAME] = unknown_workloads_topic_arn


def test_lambda_handler_workload_exists(dynamodb):
    from cbs.lambdas.dlq_triage.app import lambda_handler

    object_key = "/here/or/there/not/sure/where/file.json"
    sanitized_object_key = OBJECT_KEY_SANITIZER(object_key)

    dynamodb.update_item(
        TableName=TABLE_NAME,
        Key={"object_key": SERIALIZER.serialize(sanitized_object_key)},
        UpdateExpression="set first_received = :first_received, hit_count = :hit_count",
        ExpressionAttributeValues={
            ":first_received": SERIALIZER.serialize("1970-01-01 22:46:42.222"),
            ":hit_count": SERIALIZER.serialize(1),
        },
    )

    lambda_handler(create_sqs_event(object_key), None)

    response = dynamodb.get_item(
        TableName=TABLE_NAME,
        Key={
            "object_key": SERIALIZER.serialize(sanitized_object_key),
        },
    )
    assert response["Item"]["hit_count"]["N"] == "2"


def test_lambda_handler_unknown_workload_doesnt_exist(dynamodb):
    from cbs.lambdas.dlq_triage.app import lambda_handler

    object_key = "/here/nor/there/not/sure/where"

    lambda_handler(create_sqs_event(object_key), None)

    sanitized_object_key = OBJECT_KEY_SANITIZER(object_key)

    response = dynamodb.get_item(
        TableName=TABLE_NAME,
        Key={
            "object_key": SERIALIZER.serialize(sanitized_object_key),
        },
    )

    assert response["Item"]["hit_count"]["N"] == "1"


@mark.filterwarnings("ignore::UserWarning")
def test_lambda_handler_workload_exists_but_is_known_workload(dynamodb):
    from cbs.lambdas.dlq_triage.app import lambda_handler

    object_key = "cloudwatchlogs/ssm"

    dynamodb.update_item(
        TableName=TABLE_NAME,
        Key={"object_key": SERIALIZER.serialize(object_key)},
        UpdateExpression="set first_received = :first_received, hit_count = :hit_count",
        ExpressionAttributeValues={
            ":first_received": SERIALIZER.serialize("1970-01-01 22:49:41.111"),
            ":hit_count": SERIALIZER.serialize(1),
        },
    )

    lambda_handler(create_sqs_event(object_key), None)

    response = dynamodb.get_item(
        TableName=TABLE_NAME,
        Key={
            "object_key": SERIALIZER.serialize(object_key),
        },
    )

    assert response["Item"]["hit_count"]["N"] == "1"
