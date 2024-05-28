from os import environ
from unittest.mock import MagicMock

from boto3 import client
from moto import mock_aws
from pytest import fixture

from . import constants


@fixture
def sqs():
    with mock_aws():
        yield client("sqs")


@fixture(autouse=True)
def queue(sqs):
    cbs_sqs_url = sqs.create_queue(QueueName="TestQueue")["QueueUrl"]
    cbs_dlq_url = sqs.create_queue(QueueName="TestDLQ")["QueueUrl"]
    environ["CBS_SQS_URL"] = cbs_sqs_url
    environ["CBS_DLQ_URL"] = cbs_dlq_url


@fixture(autouse=True)
def transport_lambda_environment_variables():
    environ["CBS_READER_ROLE_ARN"] = constants.READER_ROLE_ARN


@fixture
def mock_context():
    context = MagicMock()
    context.aws_request_id = "mockID"
    context.memory_limit_in_mb = "128"
    return context
