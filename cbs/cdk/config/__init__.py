from re import match

from boto3 import client
from botocore.exceptions import ClientError
from pydantic import BaseModel, field_validator, validate_email
from yaml import dump, safe_load


class CBSConfig(BaseModel):
    # Environment
    Environment: str
    AgentAccount: str | None
    OnlyAgent: bool
    UsePAT: bool

    # Variables
    PartnerConfigBucket: str | None  # 2.0 partners
    PartnerInventoryBucket: str | None  # 1.0 partners
    SQSArn: str | None  # 1.0 SQS
    OpsGenieURL: str | None
    UnknownWorkloadsEmails: list[str]

    # IAM
    UseRole: bool
    ImportUsersOrRoles: bool
    DevOpsUser: str
    DevOpsGroup: str
    ReaderUser: str
    ReaderUserGroup: str
    GrafanaUser: str
    GrafanaUserGroup: str

    @field_validator("AgentAccount")
    @classmethod
    def check_account_id(cls, v: str | None) -> str | None:
        if v is not None:
            assert match(r"^[\d]{12}$", v), "Account ID must be exactly 12 digits long"
        return v

    @field_validator("SQSArn")
    @classmethod
    def check_sqs_arn(cls, v: str | None) -> str | None:
        if v is not None:
            assert match(
                r"^arn:aws:sqs:[a-z]{2}-[a-z]{4,9}-[\d]:[\d]{12}:[\w]+$", v
            ), "Invalid SQS ARN"
        return v

    @field_validator("UnknownWorkloadsEmails")
    @classmethod
    def check_emails(cls, v: str | list[str] | None) -> str | list[str] | None:
        if isinstance(v, str):
            _, email = validate_email(v)
            return email
        elif isinstance(v, list):
            emails = []
            for email in v:
                _, email = validate_email(email)
                emails.append(email)
            return emails


class ConfigManager:
    def __init__(self, environment: str) -> CBSConfig:
        self.client = client("ssm")

        with open(f"./config/{environment}.yaml", "r") as f:
            self.local_config = CBSConfig(**safe_load(f))

        self.remote_config = self.get_config()
        update_config = False

        if self.remote_config is None:
            self.set_config()
            self.remote_config = self.get_config()

        if self.local_config != self.remote_config:
            local_config_dict = dict(self.local_config)
            remote_config_dict = dict(self.remote_config)
            for k, v in local_config_dict.items():
                if v and remote_config_dict[k] != v:
                    remote_config_dict[k] = v
                    update_config = True

        if update_config:
            self.set_config(remote_config_dict)

    def get_config(self) -> CBSConfig | None:
        try:
            config = self.client.get_parameter(Name="cbs_config", WithDecryption=True)[
                "Parameter"
            ]["Value"]
            return CBSConfig(**safe_load(config))
        except ClientError:
            return None

    def set_config(self, updated_config: dict = None) -> None:
        if updated_config:
            self.remote_config = CBSConfig(**updated_config)
        self.client.put_parameter(
            Name="cbs_config",
            Description="CBS Configuration",
            Value=(
                dump(dict(self.local_config))
                if not updated_config
                else dump(updated_config)
            ),
            Type="SecureString",
            Overwrite=True,
        )
