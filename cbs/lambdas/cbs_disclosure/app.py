from json import dumps, loads
from os import getenv

from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.typing import LambdaContext
from boto3 import client
from common_functions import trigger_codepipeline
from core.utils.sts import assume_role

logger = Logger(service=getenv("AWS_LAMBDA_FUNCTION_NAME"))


def lambda_handler(event: dict[str, str], _: LambdaContext) -> None:
    bucket_name = event["bucket_name"]
    s3_client = client("s3")

    logger.info("Getting '%s' bucket policy", bucket_name)
    policy = loads(s3_client.get_bucket_policy(Bucket=bucket_name)["Policy"])

    for statement in policy["Statement"]:
        if "s3:ReplicateObject" in statement["Action"]:
            policy["Statement"].remove(statement)
            logger.info("Successfully removed replication statement from policy")

    s3_client.put_bucket_policy(Bucket=bucket_name, Policy=dumps(policy))
    logger.info("Successfully updated '%s' bucket policy", bucket_name)

    logger.info("Triggering CI/CD pipeline to remove partner's CloudWatch Alarms...")
    cbs_devops_role_session = assume_role(
        role_arn=getenv("CBS_DEVOPS_ROLE_ARN"),
        role_session_name="DisclosureExpiryReached",
    )
    cp_client = cbs_devops_role_session.client("codepipeline")
    trigger_codepipeline(
        getenv("CICD_PIPELINE_NAME"), "DisclosureExpiryReached", cp_client
    )
    logger.info("Successfully triggered CI/CD pipeline")
