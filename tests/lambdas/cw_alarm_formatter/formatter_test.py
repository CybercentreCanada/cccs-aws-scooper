from datetime import datetime, timedelta, timezone
from os import environ
from sys import path

from boto3 import client
from boto3.dynamodb.types import TypeSerializer
from moto import mock_aws
from pytest import fixture

from cbs.core import constants
from cbs.lambdas import PATH

path.append(f"{PATH}/cw_alarm_formatter")

from cbs.lambdas.cw_alarm_formatter import app

SNS_MESSAGE = {
    "Message": '{"AlarmName": "CBS-ReplicationAlarm-log-dev-testing"}',
}
SNS_EVENT = {
    "Sns": SNS_MESSAGE,
    "Message": SNS_MESSAGE,
    "sns_message": {"Sns": SNS_MESSAGE},
}
TABLE_NAME = "ALARM_SUPPRESSION_TABLE_NAME"


@fixture
def dynamodb():
    with mock_aws():
        yield client("dynamodb")


@fixture
def sns():
    with mock_aws():
        yield client("sns")


@fixture
def sqs():
    with mock_aws():
        yield client("sqs")


@fixture(autouse=True)
def alarm_suppression_table(dynamodb) -> None:
    dynamodb.create_table(
        AttributeDefinitions=[
            {"AttributeName": constants.CBS_ID, "AttributeType": "S"},
            {"AttributeName": constants.ALARM_TYPE, "AttributeType": "S"},
        ],
        TableName=TABLE_NAME,
        KeySchema=[
            {"AttributeName": constants.CBS_ID, "KeyType": "HASH"},
            {"AttributeName": constants.ALARM_TYPE, "KeyType": "RANGE"},
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


@fixture
def queue_arn_and_url(sqs) -> tuple[str]:
    sqs_url = sqs.create_queue(QueueName="test")["QueueUrl"]
    sqs_arn = sqs.get_queue_attributes(QueueUrl=sqs_url, AttributeNames=["QueueArn"])[
        "Attributes"
    ]["QueueArn"]
    return sqs_arn, sqs_url


@fixture(autouse=True)
def cloudwatch_alarms_topic(sns, queue_arn_and_url) -> None:
    sns_arn = sns.create_topic(Name="CW_ALARMS")["TopicArn"]
    environ["CLOUDWATCH_ALARMS_TOPIC"] = sns_arn
    sns.subscribe(TopicArn=sns_arn, Protocol="sqs", Endpoint=queue_arn_and_url[0])


def test_lambda_handler_alarm_formatted_success(sqs, queue_arn_and_url) -> None:
    app.lambda_handler({"Records": [SNS_EVENT]}, None)

    response = sqs.receive_message(QueueUrl=queue_arn_and_url[1])
    assert "Messages" in response

    message = response["Messages"][0]
    assert "ReplicationAlarm" in message["Body"]


def test_lambda_handler_alarm_suppressed_success(
    dynamodb, sqs, queue_arn_and_url
) -> None:
    serializer = TypeSerializer()
    replication_expiry = datetime.now(timezone.utc) + timedelta(days=2)

    dynamodb.put_item(
        TableName=TABLE_NAME,
        Item={
            constants.CBS_ID: serializer.serialize("log"),
            constants.ALARM_TYPE: serializer.serialize("ReplicationAlarm"),
            constants.SUPPRESSION_EXPIRY: serializer.serialize(
                replication_expiry.isoformat()
            ),
        },
    )

    app.lambda_handler({"Records": [SNS_EVENT]}, None)

    response = sqs.receive_message(QueueUrl=queue_arn_and_url[1])
    assert "Messages" not in response
