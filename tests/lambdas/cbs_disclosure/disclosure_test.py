from json import dumps, loads
from os import environ

from boto3 import client
from moto import mock_aws
from pytest import mark, raises

BUCKET_NAME = "test"
DESTINATION_ACCOUNT_ID = "222222222222"
DESTINATION_BUCKET_POLICY = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Deny",
            "Principal": {"AWS": "*"},
            "Action": "s3:*",
            "Resource": [
                f"arn:aws:s3:::{BUCKET_NAME}",
                f"arn:aws:s3:::{BUCKET_NAME}/*",
            ],
            "Condition": {"Bool": {"aws:SecureTransport": "false"}},
        },
        {
            "Effect": "Allow",
            "Principal": {
                "AWS": f"arn:aws:iam::{DESTINATION_ACCOUNT_ID}:role/CBS-Agent-test-ca-central-CustomS3AutoDeleteObject"
            },
            "Action": [
                "s3:DeleteObject*",
                "s3:GetBucket*",
                "s3:List*",
                "s3:PutBucketPolicy",
            ],
            "Resource": [
                f"arn:aws:s3:::{BUCKET_NAME}",
                f"arn:aws:s3:::{BUCKET_NAME}/*",
            ],
        },
        {
            "Effect": "Allow",
            "Principal": {"AWS": "arn:aws:iam::111111111111:root"},
            "Action": [
                "s3:GetBucketVersioning",
                "s3:ObjectOwnerOverrideToBucketOwner",
                "s3:PutBucketVersioning",
                "s3:ReplicateDelete",
                "s3:ReplicateObject",
            ],
            "Resource": [
                f"arn:aws:s3:::{BUCKET_NAME}",
                f"arn:aws:s3:::{BUCKET_NAME}/*",
            ],
        },
        {
            "Effect": "Deny",
            "Principal": {"AWS": "*"},
            "Action": "s3:GetObject",
            "Resource": [
                f"arn:aws:s3:::{BUCKET_NAME}",
                f"arn:aws:s3:::{BUCKET_NAME}/*",
            ],
            "Condition": {
                "StringNotEquals": {
                    "aws:PrincipalArn": f"arn:aws:iam::{DESTINATION_ACCOUNT_ID}:role/CBS-ReaderRole-test-ca-central-1"
                }
            },
        },
        {
            "Effect": "Allow",
            "Principal": {"AWS": f"arn:aws:iam::{DESTINATION_ACCOUNT_ID}:root"},
            "Action": [
                "s3:Abort*",
                "s3:DeleteObject*",
                "s3:PutObject",
                "s3:PutObjectLegalHold",
                "s3:PutObjectRetention",
                "s3:PutObjectTagging",
                "s3:PutObjectVersionTagging",
            ],
            "Resource": [
                f"arn:aws:s3:::{BUCKET_NAME}",
                f"arn:aws:s3:::{BUCKET_NAME}/*",
            ],
        },
    ],
}


@mock_aws
@mark.filterwarnings("ignore::UserWarning")
def test_valid_event():
    from cbs.lambdas.cbs_disclosure.app import lambda_handler

    s3_client = client("s3")
    s3_client.create_bucket(Bucket=BUCKET_NAME)
    s3_client.put_bucket_versioning(
        Bucket=BUCKET_NAME, VersioningConfiguration={"Status": "Enabled"}
    )
    s3_client.put_bucket_policy(
        Bucket=BUCKET_NAME, Policy=dumps(DESTINATION_BUCKET_POLICY)
    )

    environ["CBS_DEVOPS_ROLE_ARN"] = "arn:aws:iam::111111111111:role/test"
    environ["CICD_PIPELINE_NAME"] = "CBS-CICD-test-ca-central-1"

    event = {"bucket_name": BUCKET_NAME}

    # Catch expected errors since the StartPipelineExecution API is not implemented in moto
    with raises(NotImplementedError):
        lambda_handler(event, None)

    response = s3_client.get_bucket_policy(Bucket=BUCKET_NAME)
    policy = loads(response["Policy"])

    for statement in policy["Statement"]:
        if "s3:ReplicateObject" in statement["Action"]:
            assert (
                False
            ), f"Statement '{statement}' was not removed from the bucket policy"


@mock_aws
def test_invalid_event():
    from cbs.lambdas.cbs_disclosure.app import lambda_handler

    event = {}

    with raises(KeyError):
        lambda_handler(event, None)
