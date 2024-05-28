from boto3 import Session, client
from botocore.client import BaseClient
from botocore.exceptions import ClientError
from colors import color
from core.utils.paginate import paginate
from core.utils.sts import assume_role

from .io import account_input
from .logging import LOGGER

STS_CLIENT = client("sts")
ORG_CLIENT = client("organizations")

SUPER_ADMIN_ROLE_NAMES = (
    "PBMMAccel-PipelineRole",
    "ASEA-PipelineRole",  # https://aws-samples.github.io/aws-secure-environment-accelerator/v1.5.6-a/operations/system-overview/#1313-install-execution-roles
    "OrganizationAccountAccessRole",  # https://awslabs.github.io/landing-zone-accelerator-on-aws/latest/sample-configurations/standard/authn-authz/#relationship-to-the-management-root-aws-account
    "AWSControlTowerExecution",
)


def get_account_id(sts_client: BaseClient = STS_CLIENT) -> str:
    """Get current account ID."""
    return sts_client.get_caller_identity()["Account"]


def is_mgmt_account() -> bool:
    """Check if current account is the management account."""
    organization = ORG_CLIENT.describe_organization()["Organization"]
    mstr_account_id = organization["MasterAccountId"]
    account_id = get_account_id()

    return mstr_account_id == account_id


def get_account_id_by_name(name: str) -> str:
    """Get account ID by name."""
    accounts = {
        i: (account["Name"], account["Id"])
        for i, account in enumerate(
            paginate(
                client=ORG_CLIENT,
                command="list_accounts",
                array="Accounts",
                logger=LOGGER,
            ),
            start=1,
        )
    }
    LOGGER.info("Accounts:")
    for i, account in accounts.items():
        account_name, account_id = account
        LOGGER.info("[%s]: %s (%s)", i, account_name, account_id)

    account_selection = account_input(account_name=name, limit=len(accounts))

    return accounts[account_selection][1]


def assume_super_admin_role(account_id: str, role_session_name: str) -> Session:
    """Assume super admin role in given account."""
    session = None
    # Try all the known super admin roles first
    for role_name in SUPER_ADMIN_ROLE_NAMES:
        role_arn = f"arn:aws:iam::{account_id}:role/{role_name}"
        try:
            session = assume_role(role_arn, role_session_name, sts_client=STS_CLIENT)
        except ClientError as e:
            if e.response["Error"]["Code"] == "AccessDenied":
                LOGGER.debug("Failed to assume role '%s'", role_arn)
            else:
                raise e
    # Accept user input for super admin role name
    while session is None:
        role_name = input(
            color(
                "Enter name of role with organizational account access: ",
                fg="yellow",
                style="bold",
            )
        ).strip()
        role_arn = f"arn:aws:iam::{account_id}:role/{role_name}"
        try:
            session = assume_role(role_arn, role_session_name, sts_client=STS_CLIENT)
        except ClientError:
            LOGGER.error("Failed to assume role '%s'", role_arn)

    LOGGER.debug("Successfully assumed '%s' session", role_arn)

    return session
