from functools import cached_property
from json import dumps, loads
from pathlib import Path
from typing import Union

from boto3 import Session
from botocore.client import BaseClient
from core.cbs_config import CBSConfig
from core.utils.paginate import paginate
from installer.utils.dict import dict_template
from installer.utils.io import load_json_file
from installer.utils.logging import LOGGER

from .config import ReplicationConfiguration
from .policies import REPLICATION_ROLE_CMK_POLICY_PATH


class ControlTowerCMK:
    """Find and manage a customer's Control Tower KMS key."""

    def __init__(self, management_account_session: Session) -> None:
        self.management_account_session = management_account_session

    @cached_property
    def arn(self) -> Union[str, None]:
        """Key ARN associated with Control Tower."""
        control_tower_client = self.management_account_session.client("controltower")
        landing_zones = paginate(
            control_tower_client, "list_landing_zones", "landingZones", LOGGER
        )
        if len(landing_zones) == 1:
            landing_zone_arn = landing_zones[0]["arn"]
            manifest = control_tower_client.get_landing_zone(
                landingZoneIdentifier=landing_zone_arn
            )["landingZone"]["manifest"]
            return manifest["centralizedLogging"]["configurations"]["kmsKeyArn"]
        else:
            LOGGER.debug("Found %s landing zones", len(landing_zones))

    def add_to_policy(self, policy_path: Path, **substitutions) -> None:
        """Add given policy to key's policy."""
        kms_client = self.management_account_session.client("kms")
        # Construct policy to add to key policy
        constructed_policy = dict_template(load_json_file(policy_path), **substitutions)
        # Get current policy
        current_policy = loads(kms_client.get_key_policy(KeyId=self.arn)["Policy"])
        # Add policy to existing policy
        for statement in constructed_policy["Statement"]:
            if statement not in current_policy["Statement"]:
                current_policy["Statement"].append(statement)
        # Set policy
        kms_client.put_key_policy(KeyId=self.arn, Policy=dumps(current_policy))

    def remove_from_policy(self, policy_path: Path, **substitutions) -> None:
        """Remove given policy from key's policy."""
        kms_client = self.management_account_session.client("kms")
        # Construct policy to know what to remove from key policy
        constructed_policy = dict_template(load_json_file(policy_path), **substitutions)
        # Get current policy
        current_policy = loads(kms_client.get_key_policy(KeyId=self.arn)["Policy"])
        # Remove policy from existing policy
        for statement in constructed_policy["Statement"]:
            if statement in current_policy["Statement"]:
                current_policy["Statement"].remove(statement)
        # Set policy
        kms_client.put_key_policy(KeyId=self.arn, Policy=dumps(current_policy))


class ControlTowerReplicationConfiguration(ReplicationConfiguration):
    """S3 Replication Configuration specific to LZA+CT environments."""

    def __init__(
        self,
        control_tower_cmk_arn: str,
        bucket_name: str,
        cbs_config: CBSConfig,
        session: Session,
        s3_client: BaseClient,
    ) -> None:
        super().__init__(bucket_name, cbs_config, session, s3_client)

        self.role.create_and_attach_policy(
            policy_name="cbs-control-tower-decrypt",
            policy_description="CBS policy for Control Tower CMK Decryption",
            policy_path=REPLICATION_ROLE_CMK_POLICY_PATH,
            control_tower_bucket_name=self.bucket_name,
            control_tower_cmk_arn=control_tower_cmk_arn,
        )
