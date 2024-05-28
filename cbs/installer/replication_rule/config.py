from boto3 import Session
from botocore.client import BaseClient
from botocore.exceptions import ClientError
from core.cbs_config import CBSConfig
from installer.core.constants import CBS
from installer.core.role import Role

from .policies import ASSUME_ROLE_POLICY_PATH, CROSS_ACCOUNT_REPLICATION_POLICY_PATH


class ReplicationConfiguration:
    """S3 Replication Configuration class"""

    def __init__(
        self,
        bucket_name: str,
        cbs_config: CBSConfig,
        session: Session,
        s3_client: BaseClient,
    ) -> None:
        self.session = session
        self.s3_client = s3_client
        self.bucket_name = bucket_name
        self.cbs_config = cbs_config
        self.config = self.get_config()
        tags = [{"Key": "Owner", "Value": CBS.upper()}]

        if (role_arn := self.config.get("Role")) is None:
            self.role = Role.create(
                session=session,
                role_name=f"cbs-replication-{self.bucket_name}",
                role_description="Role needed by CBS to perform S3 replication",
                assume_role_policy_path=ASSUME_ROLE_POLICY_PATH,
                tags=tags,
            )
        else:
            self.role = Role(
                session=session,
                iam_client=session.client("iam"),
                name=role_arn.split("/")[-1],
                arn=role_arn,
                tags=tags,
            )

        self.role.create_and_attach_policy(
            policy_name=f"cbs-replicate-{self.bucket_name}-to-{self.cbs_config.destination_bucket_name}",
            policy_description="CBS policy for cross-account S3 replication",
            policy_path=CROSS_ACCOUNT_REPLICATION_POLICY_PATH,
            source_bucket_name=self.bucket_name,
            source_bucket_encryption_key_arn=self.source_bucket_encryption_key_arn,
            destination_bucket_name=self.cbs_config.destination_bucket_name,
            destination_bucket_encryption_key_arn=self.cbs_config.destination_bucket_key_arn,
        )

    @property
    def source_bucket_encryption_key_arn(self) -> str:
        """Source bucket's encryption key ARN."""
        encryption = self.s3_client.get_bucket_encryption(
            Bucket=self.bucket_name,
        )[
            "ServerSideEncryptionConfiguration"
        ]["Rules"][0]
        if (
            encryption["ApplyServerSideEncryptionByDefault"]["SSEAlgorithm"]
            == "aws:kms"
        ):
            return encryption["ApplyServerSideEncryptionByDefault"]["KMSMasterKeyID"]
        elif (
            encryption["ApplyServerSideEncryptionByDefault"]["SSEAlgorithm"] == "AES256"
        ):
            kms_client = self.session.client("kms")
            response = kms_client.describe_key(
                KeyId="alias/aws/s3",
            )
            return response["KeyMetadata"]["Arn"]
        raise NotImplementedError(
            f"SSE algorithm {encryption['ApplyServerSideEncryptionByDefault']['SSEAlgorithm']} not supported"
        )

    def get_config(self) -> dict:
        """Get current replication configuration."""
        try:
            return self.s3_client.get_bucket_replication(Bucket=self.bucket_name)[
                "ReplicationConfiguration"
            ]
        except ClientError:
            return dict()

    def set_cbs_config(self) -> None:
        """Add CBS replication rule configuration to bucket."""
        cbs_replication_rule = self.construct_replication_rule()
        if self.config:
            for rule in self.config["Rules"]:
                if (
                    rule["Destination"]["Bucket"]
                    == f"arn:aws:s3:::{self.cbs_config.destination_bucket_name}"
                ):
                    raise ValueError(
                        f"CBS replication rule already exists on bucket '{self.bucket_name}'"
                    )
            self.config["Rules"].append(cbs_replication_rule)

        self.s3_client.put_bucket_replication(
            Bucket=self.bucket_name,
            ReplicationConfiguration=self.config
            or dict(Role=self.role.arn, Rules=[cbs_replication_rule]),
        )

    def remove_cbs_config(self) -> None:
        """Remove CBS replication rule configuration from bucket."""
        for rule in self.config["Rules"]:
            if (
                rule["Destination"]["Bucket"]
                == f"arn:aws:s3:::{self.cbs_config.destination_bucket_name}"
            ):
                self.config["Rules"].remove(rule)
        if self.config["Rules"]:
            self.role.delete_policies(only_cbs=True)
            self.s3_client.put_bucket_replication(
                Bucket=self.bucket_name,
                ReplicationConfiguration=self.config,
            )
        else:
            self.role.delete()
            self.s3_client.delete_bucket_replication(Bucket=self.bucket_name)

    def construct_replication_rule(self) -> dict:
        """Construct CBS replication rule based on partner's destination bucket parameters."""
        if self.config:
            try:
                existing_priorities = [
                    rule["Priority"] for rule in self.config["Rules"]
                ]
            except KeyError:
                # V1 schema: https://docs.aws.amazon.com/AmazonS3/latest/userguide/replication-add-config.html#replication-backward-compat-considerations
                rule = self.config["Rules"][0]
                existing_priorities = [0]
                # Convert V1 to V2
                del rule["Prefix"]
                rule["Priority"] = 0
                rule["Filter"] = {}
                rule["DeleteMarkerReplication"] = {"Status": "Disabled"}
        else:
            existing_priorities = [-1]
        return {
            "ID": CBS,
            "Priority": max(existing_priorities) + 1,
            "Filter": {},
            "Status": "Enabled",
            "SourceSelectionCriteria": {
                "SseKmsEncryptedObjects": {"Status": "Enabled"}
            },
            "Destination": {
                "Bucket": f"arn:aws:s3:::{self.cbs_config.destination_bucket_name}",
                "Account": self.cbs_config.destination_account_id,
                "AccessControlTranslation": {"Owner": "Destination"},
                "EncryptionConfiguration": {
                    "ReplicaKmsKeyID": self.cbs_config.destination_bucket_key_arn,
                },
                "ReplicationTime": {"Status": "Enabled", "Time": {"Minutes": 15}},
                "Metrics": {"Status": "Enabled", "EventThreshold": {"Minutes": 15}},
            },
            "DeleteMarkerReplication": {"Status": "Disabled"},
        }
