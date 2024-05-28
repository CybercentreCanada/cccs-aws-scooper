from json import dumps

from aws_lambda_powertools.utilities.data_classes import EventBridgeEvent

from cbs.core.constants import DEFAULT_VPC_FLOW_LOG_FIELDS
from docs import VERSION

from . import constants


def make_s3_replication_notifications(object_key, bucket_name):
    return EventBridgeEvent(
        {
            "version": "0",
            "id": "fake-id",
            "detail-type": "AWS API Call via CloudTrail",
            "source": "aws.s3",
            "account": constants.CBS_ACCOUNT,
            "time": "2023-22-99T19:08:30Z",
            "region": "ca-central-1",
            "resources": [],
            "detail": {
                "eventVersion": "1.08",
                "userIdentity": {
                    "type": "AWSAccount",
                    "principalId": "AROANOTREAL:s3-replication",
                    "accountId": constants.PARTNER_ACCOUNT_ID,
                    "invokedBy": constants.S3_SERVICE,
                },
                "eventTime": "2023-22-99T19:08:30Z",
                "eventSource": constants.S3_SERVICE,
                "eventName": "PutObject",
                "awsRegion": "ca-central-1",
                "sourceIPAddress": constants.S3_SERVICE,
                "userAgent": constants.S3_SERVICE,
                "requestParameters": {
                    "bucketName": bucket_name,
                    "x-amz-server-side-encryption-context": "NULL",
                    "x-amz-server-side-encryption-aws-kms-key-id": f"arn:aws:kms:ca-central-1:{constants.CBS_ACCOUNT}:key/333",
                    "Host": "s3.ca-central-1.amazonaws.com",
                    "x-amz-server-side-encryption": "aws:kms",
                    "x-amz-version-id": "null.null",
                    "key": object_key,
                    "x-amz-storage-class": "STANDARD",
                },
                "responseElements": {
                    "x-amz-server-side-encryption-aws-kms-key-id": f"arn:aws:kms:ca-central-1:{constants.CBS_ACCOUNT}:key/333",
                    "x-amz-server-side-encryption": "aws:kms",
                    "x-amz-server-side-encryption-context": "NULL==",
                    "x-amz-version-id": "null.null",
                },
                "additionalEventData": {
                    "SignatureVersion": "SigV4",
                    "CipherSuite": "SHASHA",
                    "bytesTransferredIn": 42,
                    "SSEApplied": "SSE_KMS",
                    "AuthenticationMethod": "AuthHeader",
                    "x-amz-id-2": "NULL",
                    "bytesTransferredOut": 0,
                },
                "requestID": "3NYQHSHMD8AC4GV2",
                "eventID": "808a6ad7-c7dc-4893-81fe-589b37fb74f4",
                "readOnly": False,
                "resources": [
                    {
                        "type": "AWS::S3::Object",
                        "ARN": f"arn:aws:s3:::{bucket_name}/{object_key}",
                    },
                    {
                        "accountId": constants.CBS_ACCOUNT,
                        "type": "AWS::S3::Bucket",
                        "ARN": f"arn:aws:s3:::{bucket_name}",
                    },
                ],
                "eventType": "AwsApiCall",
                "managementEvent": False,
                "recipientAccountId": constants.CBS_ACCOUNT,
                "sharedEventID": "12345",
                "vpcEndpointId": "vpce-123",
                "eventCategory": "Data",
            },
        }
    )


def make_output_message(object_key: str, bucket_name: str, workload: str) -> str:
    output = {
        "Cbs-Identifier": constants.CBS_ID,
        "Workload": workload,
        "File": object_key,
        "Bucket": bucket_name,
        "ReaderArn": constants.READER_ROLE_ARN,
        "Release": VERSION,
    }

    if workload == "cloudwatch.vpcFlowLogs":
        output["CbsCustomFields"] = ",".join(DEFAULT_VPC_FLOW_LOG_FIELDS)

    return dumps(output)
