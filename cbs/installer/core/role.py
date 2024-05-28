from __future__ import annotations

from json import dumps
from pathlib import Path

from boto3 import Session
from botocore.client import BaseClient
from botocore.exceptions import ClientError
from core.utils.paginate import paginate
from installer.utils.dict import dict_template
from installer.utils.io import load_json_file
from installer.utils.logging import LOGGER
from installer.utils.string import enforce_max_string_length
from installer.utils.sts import get_account_id

from .constants import CBS


class Role:
    """IAM Role class to help with common operations."""

    def __init__(
        self,
        session: Session,
        iam_client: BaseClient,
        name: str,
        arn: str,
        tags: list[dict[str, str]],
    ) -> None:
        self.session = session
        self.iam_client = iam_client

        self.name = name
        self.arn = arn
        self.tags = tags

    @property
    def attached_policies(self) -> list[dict]:
        """Get role's attached policies."""
        return paginate(
            client=self.iam_client,
            command="list_attached_role_policies",
            array="AttachedPolicies",
            logger=LOGGER,
            RoleName=self.name,
        )

    def get_policy(self, policy_arn: str) -> dict:
        """Get policy by ARN."""
        policy_info = self.iam_client.get_policy(PolicyArn=policy_arn)["Policy"]
        policy_version = self.iam_client.get_policy_version(
            PolicyArn=policy_arn, VersionId=policy_info["DefaultVersionId"]
        )["PolicyVersion"]
        return policy_version["Document"]

    @staticmethod
    def construct_policy(policy_path: Path, **substitutions) -> dict:
        """Construct policy and make any template substitutions."""
        policy = load_json_file(policy_path)
        return dict_template(policy, **substitutions)

    def create_and_attach_policy(
        self,
        policy_name: str,
        policy_description: str,
        policy_path: Path,
        **substitutions,
    ) -> None:
        """Create policy and attach to role instance."""
        policy_name = enforce_max_string_length(policy_name, 128)
        policy_description = enforce_max_string_length(policy_description, 1000)

        try:
            response = self.iam_client.create_policy(
                PolicyName=policy_name,
                Description=policy_description,
                PolicyDocument=dumps(
                    Role.construct_policy(policy_path, **substitutions)
                ),
                Tags=self.tags,
            )
        except ClientError as e:
            if e.response["Error"]["Code"] == "EntityAlreadyExists":
                account_id = get_account_id(self.session.client("sts"))
                response = self.iam_client.get_policy(
                    PolicyArn=f"arn:aws:iam::{account_id}:policy/{policy_name}"
                )
            else:
                raise e

        self.iam_client.attach_role_policy(
            RoleName=self.name,
            PolicyArn=response["Policy"]["Arn"],
        )

    @classmethod
    def create(
        cls,
        session: Session,
        role_name: str,
        role_description: str,
        assume_role_policy_path: Path,
        tags: list[dict[str, str]],
    ) -> Role:
        """Create an IAM role and its associated object instance."""
        iam_client = session.client("iam")
        role_name = enforce_max_string_length(role_name, 64)
        role_description = enforce_max_string_length(role_description, 1000)

        try:
            response = iam_client.create_role(
                RoleName=role_name,
                Description=role_description,
                AssumeRolePolicyDocument=dumps(load_json_file(assume_role_policy_path)),
                Tags=tags,
            )
        except ClientError as e:
            if e.response["Error"]["Code"] == "EntityAlreadyExists":
                response = iam_client.get_role(RoleName=role_name)
            else:
                raise

        return cls(
            session=session,
            iam_client=iam_client,
            name=role_name,
            arn=response["Role"]["Arn"],
            tags=tags,
        )

    def delete_policies(self, only_cbs: bool = False) -> None:
        """Detach all role policies and optionally delete any that are CBS-created."""
        for policy in self.attached_policies:
            policy_name = policy["PolicyName"]
            policy_arn = policy["PolicyArn"]
            if only_cbs:
                if policy_name.startswith(CBS):
                    self.iam_client.detach_role_policy(
                        RoleName=self.name, PolicyArn=policy_arn
                    )
                    self.iam_client.delete_policy(PolicyArn=policy_arn)
            else:
                self.iam_client.detach_role_policy(
                    RoleName=self.name, PolicyArn=policy_arn
                )
                if policy_name.startswith(CBS):
                    self.iam_client.delete_policy(PolicyArn=policy_arn)

    def delete(self) -> None:
        """Delete/detach all role policies then delete role."""
        self.delete_policies()
        self.iam_client.delete_role(RoleName=self.name)
