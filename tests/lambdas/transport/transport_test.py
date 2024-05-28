from functools import partial
from json import dumps, loads
from logging import INFO
from os import environ
from sys import path
from typing import TYPE_CHECKING

from aws_lambda_powertools.utilities.data_classes import EventBridgeEvent
from moto import mock_aws
from pytest import mark, raises

from cbs.core import constants as core_constants
from cbs.lambdas import PATH as LAMBDAS_PATH

from . import constants
from .helpers import make_output_message, make_s3_replication_notifications

# For Lambda source code relative imports
path.append(f"{LAMBDAS_PATH}/transport")

if TYPE_CHECKING:
    from cbs.lambdas.transport.exceptions import TransportError
else:
    from exceptions import TransportError

_make_output_message = partial(make_output_message, bucket_name=constants.BUCKET_NAME)
_make_s3_replication_notifications = partial(
    make_s3_replication_notifications, bucket_name=constants.BUCKET_NAME
)

bucket_event_test_params = [
    (
        _make_s3_replication_notifications(
            f"{constants.PARTNER_ACCOUNT_ID}/CloudTrail/ca-central-1/2021/09/09/testCT.json.gz"
        ),
        _make_output_message(
            f"{constants.PARTNER_ACCOUNT_ID}/CloudTrail/ca-central-1/2021/09/09/testCT.json.gz",
            workload="cloudtrailLogs",
        ),
        None,
    ),  # S3 event notification
    (
        _make_s3_replication_notifications(
            "AWSLogs/111111111111/Config/ConfigWritabilityCheckFile"
        ),
        "0",
        "Workload is unsupported",
    ),  # Config Writability Check File
    (
        EventBridgeEvent("useless/1234/notuseful.txt"),
        "0",
        "Event is not an accepted type",
    ),  # Unknown invoke event string
    (
        EventBridgeEvent({"key1": "value1", "key2": "value2", "key3": "value3"}),
        "0",
        "Event is not an accepted type",
    ),  # Unknown invoke event json
    (
        _make_s3_replication_notifications(
            f"ssm-inventory/AWS:Application/accountid%3D{constants.PARTNER_ACCOUNT_ID}/region%3Dca-central-1/resourcetype%3DManagedInstanceInventory/i-00000000000000001.json"
        ),
        _make_output_message(
            f"ssm-inventory/AWS:Application/accountid={constants.PARTNER_ACCOUNT_ID}/region=ca-central-1/resourcetype=ManagedInstanceInventory/i-00000000000000001.json",
            workload="ssmInventory.application",
        ),
        None,
    ),  # Test file paths with equal sign like in SSM Inventory
    (
        _make_s3_replication_notifications(
            f"{constants.PARTNER_ACCOUNT_ID}/Sandbox/AWSLogs/{constants.PARTNER_ACCOUNT_ID}/vpcflowlogs/ca-central-1/2022/12/31/{constants.PARTNER_ACCOUNT_ID}_vpcflowlogs_ca-central-1_fl-0b1cccccb888e66a2_20221231T0000Z_077f4e66.log.gz"
        ),
        _make_output_message(
            f"{constants.PARTNER_ACCOUNT_ID}/Sandbox/AWSLogs/{constants.PARTNER_ACCOUNT_ID}/vpcflowlogs/ca-central-1/2022/12/31/{constants.PARTNER_ACCOUNT_ID}_vpcflowlogs_ca-central-1_fl-0b1cccccb888e66a2_20221231T0000Z_077f4e66.log.gz",
            workload="vpcFlowLogs",
        ),
        None,
    ),  # Test VPC file path in default mapping
    (
        _make_s3_replication_notifications(
            f"{constants.CBS_ID}/{core_constants.CBS_METADATA_OBJECT_KEY}/sso.json"
        ),
        _make_output_message(
            f"{constants.CBS_ID}/{core_constants.CBS_METADATA_OBJECT_KEY}/sso.json",
            workload="metadata.sso",
        ),
        None,
    ),  # Test SSO file
]


def get_sqs_message(sqs_client, queue_url: str) -> str:
    msg = sqs_client.receive_message(QueueUrl=queue_url, MessageAttributeNames=["All"])[
        "Messages"
    ][0]
    sqs_client.delete_message(QueueUrl=queue_url, ReceiptHandle=msg["ReceiptHandle"])
    msg_body = loads(msg["Body"])
    try:
        return dumps(msg_body["metadata"])
    except KeyError:
        try:
            return msg_body["Message"]
        except KeyError:
            return dumps(msg_body)


@mock_aws
@mark.parametrize("event, output, exception", bucket_event_test_params)
@mark.filterwarnings("ignore::UserWarning")
def test_event_message(sqs, caplog, mock_context, event, output, exception):
    from cbs.lambdas.transport.transport import Transport

    try:
        with caplog.at_level(INFO):
            Transport().process_s3_event(event, mock_context)
        assert get_sqs_message(sqs, environ["CBS_SQS_URL"]) == output
    except TransportError as e:
        assert str(e) == exception
        assert (
            sqs.get_queue_attributes(
                QueueUrl=environ["CBS_SQS_URL"],
                AttributeNames=["ApproximateNumberOfMessages"],
            )["Attributes"]["ApproximateNumberOfMessages"]
            == output
        )


@mock_aws
def test_event_message_dlq(sqs, mock_context):
    from cbs.lambdas.transport.transport import Transport

    # Check that TransportError is raised
    with raises(TransportError) as exc_info:
        event = _make_s3_replication_notifications("useless/1234/notuseful.txt")
        Transport().process_s3_event(event, mock_context)

    # Check DLQ
    try:
        workload = loads(get_sqs_message(sqs, environ["CBS_DLQ_URL"]))["Workload"]
    except KeyError:
        workload = None

    assert (
        exc_info.errisinstance(TransportError)
        and str(exc_info.value) == "Unsupported workload sent to DLQ"
    ), "Expected an 'Unsupported workload sent to DLQ' TransportException"

    assert workload is None, "Expected the DLQ message's workload to be None"
