from datetime import datetime
from time import sleep

from boto3 import Session
from installer.core.constants import CBS
from installer.core.role import Role
from installer.utils.sts import get_account_id

from .policies import ASSUME_ROLE_POLICY_PATH, REPLICATE_EXISTING_OBJECTS_POLICY_PATH


class S3BatchOperationsJob:
    """S3 Batch Operations Job class"""

    def __init__(
        self,
        source_bucket_name: str,
        start_date: datetime,
        end_date: datetime,
        session: Session,
    ) -> None:
        self.s3_control_client = session.client("s3control")

        self.account_id = get_account_id(session.client("sts"))
        self.source_bucket_name = source_bucket_name
        self.start_date = start_date
        self.end_date = end_date
        self.tags = [{"Key": "Owner", "Value": CBS.upper()}]

        self.role = Role.create(
            session=session,
            role_name=f"cbs-batch-replication-{self.source_bucket_name}",
            role_description="Role needed by CBS to perform S3 batch replication",
            assume_role_policy_path=ASSUME_ROLE_POLICY_PATH,
            tags=self.tags,
        )
        self.role.create_and_attach_policy(
            policy_name=f"cbs-batch-replication-{self.source_bucket_name}",
            policy_description="CBS policy for S3 batch replication",
            policy_path=REPLICATE_EXISTING_OBJECTS_POLICY_PATH,
            source_bucket_name=self.source_bucket_name,
        )

    def get_active_jobs(self) -> list[dict]:
        """Get list of active batch operation jobs."""
        return self.s3_control_client.list_jobs(
            AccountId=self.account_id,
            JobStatuses=[
                "Active",
                "Cancelling",
                "Completing",
                "Failing",
                "New",
                "Pausing",
                "Preparing",
                "Ready",
            ],
        )["Jobs"]

    def create_batch_operations_job(self) -> None:
        """Create batch replication job for objects between start_date and end_date."""
        existing_priorities = [job["Priority"] for job in self.get_active_jobs()] or [
            -1
        ]
        # Sometimes the S3 batch operations service isn't aware of the new role it's able to assume yet so we wait here for a bit
        sleep(5)
        self.s3_control_client.create_job(
            AccountId=self.account_id,
            RoleArn=self.role.arn,
            Operation={"S3ReplicateObject": {}},
            Priority=max(existing_priorities) + 1,
            ConfirmationRequired=False,
            Description=f"CBS Batch Replication ({self.start_date.date()} to {self.end_date.date()})",
            ManifestGenerator={
                "S3JobManifestGenerator": {
                    "ExpectedBucketOwner": self.account_id,
                    "SourceBucket": f"arn:aws:s3:::{self.source_bucket_name}",
                    "Filter": {
                        "EligibleForReplication": True,
                        "CreatedAfter": self.start_date,
                        "CreatedBefore": self.end_date,
                    },
                    "EnableManifestOutput": False,
                }
            },
            Report={"Enabled": False},
            Tags=self.tags,
        )
