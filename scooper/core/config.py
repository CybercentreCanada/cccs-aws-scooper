"""
The resources contained herein are © His Majesty in Right of Canada as Represented by the Minister of National Defence.

FOR OFFICIAL USE All Rights Reserved. All intellectual property rights subsisting in the resources contained herein are,
and remain the property of the Government of Canada. No part of the resources contained herein may be reproduced or disseminated
(including by transmission, publication, modification, storage, or otherwise), in any form or any means, without the written
permission of the Communications Security Establishment (CSE), except in accordance with the provisions of the Copyright Act, such
as fair dealing for the purpose of research, private study, education, parody or satire. Applications for such permission shall be
made to CSE.

The resources contained herein are provided “as is”, without warranty or representation of any kind by CSE, whether express or
implied, including but not limited to the warranties of merchantability, fitness for a particular purpose and noninfringement.
In no event shall CSE be liable for any loss, liability, damage or cost that may be suffered or incurred at any time arising
from the provision of the resources contained herein including, but not limited to, loss of data or interruption of business.

CSE is under no obligation to provide support to recipients of the resources contained herein.

This licence is governed by the laws of the province of Ontario and the applicable laws of Canada. Legal proceedings related to
this licence may only be brought in the courts of Ontario or the Federal Court of Canada.

Notwithstanding the foregoing, third party components included herein are subject to the ownership and licensing provisions
noted in the files associated with those components.
"""

from datetime import timedelta
from json import JSONDecodeError, loads
from os import environ
from typing import Any, Literal

from boto3 import client
from botocore.exceptions import ClientError
from core.sts import assume_role
from pydantic import BaseModel, ValidationError, field_serializer, field_validator
from yaml import safe_dump as yaml_dump

from scooper.core.cli.callbacks import S3LifecycleRule, S3LifecycleTokenizer
from scooper.core.constants import ORG, SCOOPER
from scooper.core.pki import CertificateAuthority, LeafCertificate
from scooper.core.utils.io import (
    account_selection,
    boolean_prompt,
    bucket_input,
    display_buckets,
)
from scooper.core.utils.logger import get_logger
from scooper.core.utils.sts import STS_CLIENT, get_all_account_sessions

_logger = get_logger()


class DeploymentConfig(BaseModel, arbitrary_types_allowed=True):
    """Configuration model for deployment settings."""

    level: Literal["account", "org"]
    cross_account_role_name: str
    lifecycle_rules: list[S3LifecycleRule]
    standalone: bool
    supplementary_buckets: list[str] = []

    @field_validator("lifecycle_rules", mode="before")
    @classmethod
    def validate_lifecycle_rules(cls, lifecycle_rules: Any) -> list[S3LifecycleRule]:
        """Convert lifecycle_rules from list of strings to list of S3LifecycleRule objects."""
        if not lifecycle_rules:
            return []

        if all(isinstance(rule, str) for rule in lifecycle_rules):
            return S3LifecycleTokenizer(",".join(lifecycle_rules)).rules

        return lifecycle_rules

    @field_serializer("lifecycle_rules", when_used="json")
    def serialize_lifecycle_rules(
        self, lifecycle_rules: list[S3LifecycleRule]
    ) -> list[str]:
        """Convert lifecycle_rules from list of S3LifecycleRule objects to list of strings."""
        return [rule.raw for rule in lifecycle_rules]


class ScooperConfig:
    def __init__(self, deployment_config: DeploymentConfig) -> None:
        self._deployment_config = deployment_config
        # Environment attributes
        self.account_id = STS_CLIENT.get_caller_identity()["Account"]

        # PKI attributes
        if self.deployment_config.standalone:
            self.certificate_authority = CertificateAuthority(timedelta(days=365))
            self.leaf_certificate = LeafCertificate(self.certificate_authority)

    def confirm_account(self):
        """Confirm that the deployment level and account are correct."""
        _logger.info(
            "Running %s-level %s in account '%s'.",
            self.deployment_config.level,
            SCOOPER,
            self.account_id,
        )

        if not boolean_prompt("Is this the correct account?"):
            if not self.is_org_level():
                _logger.error(
                    "Need to run with org-level option to assume into other accounts. See `uv run -m scooper --help` for details."
                )
                raise SystemExit

            self.account_id = account_selection()
            session = assume_role(
                f"arn:aws:iam::{self.account_id}:role/{self.deployment_config.cross_account_role_name}"
            )
            credentials = session.get_credentials()
            environ["AWS_ACCESS_KEY_ID"] = credentials.access_key
            environ["AWS_SECRET_ACCESS_KEY"] = credentials.secret_key
            environ["AWS_SESSION_TOKEN"] = credentials.token

        self.load_config_dependent_attributes()

    def load_config_dependent_attributes(self) -> None:
        """Load attributes that depend on the deployment_config."""
        if self.is_org_level():
            try:
                org_client = client("organizations")
                self.root_id = org_client.list_roots()["Roots"][0]["Id"]
                self.org_id = org_client.describe_organization()["Organization"]["Id"]
                self.all_account_sessions = get_all_account_sessions(self)
            except ClientError as e:
                raise SystemExit(
                    "You need to run Scooper from your organization's management account for org-level enumeration/deployment."
                ) from e

        if self.deployment_config.standalone:
            buckets_indexed = display_buckets()
            buckets_selected = bucket_input(limit=len(buckets_indexed))
            self.deployment_config.supplementary_buckets = [
                buckets_indexed[index] for index in buckets_selected
            ]
            if self.deployment_config.supplementary_buckets:
                self.write_to_ssm()

    @property
    def deployment_config(self) -> DeploymentConfig:
        return self._deployment_config

    @deployment_config.setter
    def deployment_config(self, value: DeploymentConfig) -> None:
        """Update deployment_config with new values, prompting for overwrites if necessary."""
        for field in self._deployment_config.model_fields_set:
            current_value = getattr(self._deployment_config, field, None)
            given_value = getattr(value, field)
            if current_value is not None and current_value != given_value:
                _logger.warning(
                    "%s: '%s' provided differs from %s: '%s' found in SSM config.",
                    field,
                    given_value,
                    field,
                    current_value,
                )
                if boolean_prompt("Overwrite SSM config with new value?"):
                    setattr(self._deployment_config, field, given_value)
            else:
                setattr(self._deployment_config, field, given_value)

    def is_org_level(self) -> bool:
        """Check if ScooperConfig is set to org-level."""
        return self.deployment_config.level == ORG

    @property
    def identifier(self) -> str:
        """Identify the deployment by its organization ID, or its account ID at account level."""
        return self.org_id if self.is_org_level() else self.account_id

    def write_to_ssm(self) -> None:
        """Write ScooperConfig to SSM Parameter Store."""
        ssm_client = client("ssm")
        try:
            ssm_client.put_parameter(
                Name="/Scooper/Config",
                Description=f"{SCOOPER} Configuration",
                Value=self.deployment_config.model_dump_json(),
                Type="String",
                Overwrite=True,
            )
        except ClientError as e:
            raise SystemExit("Failed to write config to SSM.") from e

    @classmethod
    def from_ssm(cls) -> ScooperConfig | None:
        """Retrieve ScooperConfig from SSM Parameter Store."""
        ssm_client = client("ssm")
        try:
            parameter_value = ssm_client.get_parameter(Name="/Scooper/Config")[
                "Parameter"
            ]["Value"]
        except ClientError as e:
            if e.response["Error"]["Code"] == "ParameterNotFound":
                return None
            raise SystemExit("Failed to retrieve config from SSM.") from e

        try:
            return cls(DeploymentConfig(**loads(parameter_value)))
        except (JSONDecodeError, ValidationError) as e:
            raise SystemExit("Failed to parse config from SSM.") from e


class IAMRA(BaseModel):
    reader_role_arn: str
    trust_anchor_arn: str
    profile_arn: str
    certificate_path: str
    private_key_path: str


class OutputConfig(BaseModel):
    identifier: str
    account_id: str
    region: str
    bucket_name: str
    queue_url: str
    scooper_custom_query_role_name: str

    iamra: IAMRA

    def model_dump_yaml(self) -> None:
        with open("output_config.yaml", "w") as f:
            yaml_dump(self.model_dump(), f)
