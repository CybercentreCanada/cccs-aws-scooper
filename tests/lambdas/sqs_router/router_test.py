from os import environ
from sys import path

from boto3 import client
from moto import mock_aws
from pytest import fixture, raises

from cbs.lambdas import PATH as LAMBDAS_PATH

# # For Lambda source code relative imports
path.append(f"{LAMBDAS_PATH}/sqs_router")


SQS_EVENT = {
    "Records": [
        {
            "messageId": "6ad5e50d-a1ec-4e73-8c61-dddcbsaws",
            "receiptHandle": "AQEBuCnvF1XBczWsgXcu6kV2AL3hBxVCBSCBSfxV7fXiEO2u5w4g0taH9CX1/2l1KCYox9j62sj2sHEKMuToGYhzFJVdVWVkd2+k7xjX+fRQPm2a1jI6V8YRVK6K8sIO1Lsf/bBkLLEr04BufLA9FCtrtMuaiIbT/Asj6yrFi96vU1RQKjpn2Ycf6+zMuX/6AnHv0Iev4ABbY95uC9vP3mWrlPbWaLY3YKbLKd9e7r8y7BZw8az6tJUaEvzKBsXUE5EQkn4P8LX/TsNc20prdCZvSkZ7SgDwik/VBDzg/nASZ2N7d3/TEAPsEtTPJHvcIahYFzk6IPAOD4tyHfp66BmnZACTYLU3UHkwg0m/F/4augfqDy8wrt3DT",
            "body": '{"metadata": {"Workload": "cloudtrail", "Release": "1.8.2", "File": "o-hnzdj0000/AWSLogs/o-o-hnzdj0000/2222222222222/CloudTrail/eu-south-1/2023/02/16/2222222222222_CloudTrail_eu-south-1_PBMMAccel-Org-Trail_ca-central-1_20230216T214058Z.json.gz", "Bucket": "pbmmaccel-logarchive-phase0-cacentral1-k2-d2", "ReaderArn": "arn:aws:iam::111111111111:role/CbsASEAReaderRole", "Cbs-Identifier": "CBS-TEST-2"}, "event": {"Records": [{"eventVersion": "2.1", "eventSource": "aws:s3", "awsRegion": "ca-central-1", "eventTime": "2023-02-16T22:16:07.193Z", "eventName": "ObjectCreated:Put", "userIdentity": {"principalId": "AWS:AROACBS:regionalDeliverySession"}, "requestParameters": {"sourceIPAddress": "52.119.146.235"}, "responseElements": {"x-amz-request-id": "8888Y497", "x-amz-id-2": "J3cza9l9wdydC76qt2FzCt1Q/bbUQR9A42jruJs76tK3XkB7eCMZXKQY="}, "s3": {"s3SchemaVersion": "1.0", "configurationId": "CbsEventNotifcation", "bucket": {"name": "pbmmaccel-logarchive-phase0-cacentral1-k2-d2", "ownerIdentity": {"principalId": "AJ4X54CYX6W9"}, "arn": "arn:aws:s3:::pbmmaccel-logarchive-phase0-cacentral1-k2-d2"}, "object": {"key": "o-o-hnzdj0000/AWSLogs/o-o-hnzdj0000/2222222222222/CloudTrail/eu-south-1/2023/02/16/2222222222222_CloudTrail_eu-south-1_PBMMAccel-Org-Trail_ca-central-1_20230216T214058Z.json.gz", "size": 761, "eTag": "cbsetag", "versionId": "cbsvID", "sequencer": "000999"}}}]}}',
            "attributes": {
                "ApproximateReceiveCount": "1",
                "AWSTraceHeader": "Root=1-test-1854e0104d3670bb4968960b;Parent=123test;Sampled=0",
                "SentTimestamp": "1676585768226",
                "SenderId": "AROACBSAWS:CbsTransportLambda",
                "ApproximateFirstReceiveTimestamp": "1676585768227",
            },
            "messageAttributes": {},
            "md5OfBody": "c88888888eb63815b140809b672d3d5",
            "eventSource": "aws:sqs",
            "eventSourceARN": "arn:aws:sqs:ca-central-1:111111111111:CbsSQS",
            "awsRegion": "ca-central-1",
        }
    ]
}


@fixture
def sqs():
    with mock_aws():
        yield client("sqs")


@fixture(autouse=True)
def queue(sqs):
    queue_url = sqs.create_queue(QueueName="test")["QueueUrl"]
    environ["CBS_SQS_URL"] = queue_url


def test_partner_on_old_agent(sqs):
    from cbs.lambdas.sqs_router.app import lambda_handler

    lambda_handler(SQS_EVENT, None)

    response = sqs.receive_message(QueueUrl=environ["CBS_SQS_URL"])

    assert (
        SQS_EVENT["Records"][0]["body"] == response["Messages"][0]["Body"]
    ), "Received event does not match routed event"


def test_malformed_event():
    from cbs.lambdas.sqs_router.app import lambda_handler

    with raises(KeyError):
        lambda_handler({}, None)
