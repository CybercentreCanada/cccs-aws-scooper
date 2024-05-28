from boto3 import Session, client
from botocore.client import BaseClient


def assume_role(
    role_arn: str,
    role_session_name: str = "AssumeRole",
    region: str = "ca-central-1",
    sts_client: BaseClient = client("sts"),
) -> Session:
    """Assume given role and return its boto3 Session."""
    response = sts_client.assume_role(
        RoleArn=role_arn,
        RoleSessionName=role_session_name,
    )
    credentials = response["Credentials"]

    return Session(
        aws_access_key_id=credentials["AccessKeyId"],
        aws_secret_access_key=credentials["SecretAccessKey"],
        aws_session_token=credentials["SessionToken"],
        region_name=region,
    )
