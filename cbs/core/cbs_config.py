from dataclasses import dataclass
from importlib.resources import read_text
from json import loads

from boto3 import client
from botocore.exceptions import ClientError


@dataclass
class CBSConfig:
    destination_account_id: str
    destination_bucket_name: str
    destination_bucket_key_arn: str


class RemoteConfig:
    def __init__(self, bucket_name: str, **kwargs) -> None:
        if log_archive_account_id := kwargs.get("log_archive_account_id"):
            self.log_archive_account_id = log_archive_account_id
        else:
            sts_client = client("sts")
            self.log_archive_account_id = sts_client.get_caller_identity()["Account"]

        self.s3_client = kwargs.get("s3_client", client("s3"))

        self.config_bucket_name = bucket_name
        self.kwargs = kwargs
        self.config = self.get_config()

    @classmethod
    def from_file(cls, package: str, filename: str, **kwargs):
        remote_config = loads(read_text(package, filename))
        config = remote_config | kwargs
        return cls(**config)

    def get_config(self) -> CBSConfig:
        try:
            response = self.s3_client.get_object(
                Bucket=self.config_bucket_name,
                Key=f"{self.log_archive_account_id}/cbs_config.json",
            )
            return CBSConfig(**loads(response["Body"].read()))
        except ClientError as e:
            if e.response["Error"]["Code"] == "AccessDenied":
                raise PermissionError(
                    f"Account '{self.log_archive_account_id}' does not have permission to access bucket '{self.config_bucket_name}'."
                )
            else:
                raise e
