from csv import DictReader
from io import StringIO
from os import getenv

from aws_lambda_powertools import Logger
from botocore.config import Config
from botocore.exceptions import ClientError
from common_functions import get_all_accounts
from core import constants
from core.utils.paginate import paginate
from core.utils.sts import assume_role

config = Config(retries={"max_attempts": 4, "mode": "standard"})


class IAMMetadata:
    def __init__(self, mgmt_account_id: str) -> None:
        self._logger = Logger(service=self.__class__.__name__)
        # Assume CCCS reader role
        cccs_reader_role_session = assume_role(
            role_arn=getenv("CCCS_READER_ROLE_ARN"),
            role_session_name=f"{getenv('AWS_LAMBDA_FUNCTION_NAME')}-Assume-CCCSReaderRole",
        )
        cccs_reader_role_sts_client = cccs_reader_role_session.client("sts")

        # Assume CBS global reader role within management account
        cbs_reader_role_session = assume_role(
            role_arn=constants.CBS_GLOBAL_READER_ROLE_TEMPLATE.substitute(
                account=mgmt_account_id
            ),
            role_session_name="CBS-ListAccounts",
            sts_client=cccs_reader_role_sts_client,
        )
        org_client = cbs_reader_role_session.client("organizations")
        self.org_id = org_client.describe_organization()["Organization"]["Id"]
        # Get list of all member account ids within org
        accounts = [account["Id"] for account in get_all_accounts(org_client)]

        # Get IAM clients for all CBS global reader roles across org
        self._clients = {}
        for account in accounts:
            try:
                self._clients[account] = assume_role(
                    role_arn=constants.CBS_GLOBAL_READER_ROLE_TEMPLATE.substitute(
                        account=account
                    ),
                    role_session_name=f"CBS-{account}-IAMMetadata",
                    sts_client=cccs_reader_role_sts_client,
                ).client("iam", config=config)
            except ClientError as e:
                if e.response["Error"]["Code"] == "AccessDenied":
                    self._logger.warning(
                        f"Failed to assume '{constants.CBS_GLOBAL_READER_ROLE_TEMPLATE.substitute(account=account)}'"
                    )

        self.report = self.get_report()

    def _generate_credential_reports(self) -> None:
        """Generate credential report in each account."""
        for account_id, iam_client in self._clients.items():
            self._logger.info(
                "Generating credential report in account '%s'...", account_id
            )
            iam_client.generate_credential_report()

    def _get_credential_reports(
        self, report: dict[str, None]
    ) -> dict[str, list[dict[str, str]]]:
        """Get credential report in each account."""
        for account_id, iam_client in self._clients.items():
            self._logger.info(
                "Getting credential report in account '%s'...", account_id
            )
            response = iam_client.get_credential_report()
            content = response["Content"].decode()
            users_report = list(DictReader(StringIO(content)))
            for user in users_report:
                user["account"] = account_id
                report["users"].append(user)

        return report

    def _get_users(
        self, report: dict[str, list[dict[str, str]]]
    ) -> dict[str, list[dict[str, str]]]:
        for account_id, iam_client in self._clients.items():
            self._logger.info("Getting users in account '%s'...", account_id)
            users = paginate(
                client=iam_client,
                command="list_users",
                array="Users",
                logger=self._logger,
            )
            for user in users:
                for summary in report["users"]:
                    if summary["user"] == user["UserName"]:
                        summary["path"] = user["Path"]
                        summary["user_id"] = user["UserId"]

        return report

    def _get_virtual_mfa_devices(
        self, report: dict[str, list[dict[str, str]]]
    ) -> dict[str, list[dict[str, str]]]:
        for account_id, iam_client in self._clients.items():
            self._logger.info(
                "Getting virtual MFA devices in account '%s'...", account_id
            )
            virtual_mfa_devices = paginate(
                client=iam_client,
                command="list_virtual_mfa_devices",
                array="VirtualMFADevices",
                logger=self._logger,
            )
            for virtual_mfa_device in virtual_mfa_devices:
                for summary in report["users"]:
                    if summary["user"] == virtual_mfa_device.get("User", {}).get(
                        "UserName"
                    ):
                        # Drop the user dict since it's duplicate data
                        del virtual_mfa_device["User"]
                        summary["virtual_mfa_device"] = virtual_mfa_device

        return report

    def get_report(self) -> dict[str, list[dict[str, str]]]:
        report = {
            "organization": self.org_id,
            "users": [],
        }

        self._generate_credential_reports()
        report = self._get_credential_reports(report)
        report = self._get_users(report)
        report = self._get_virtual_mfa_devices(report)

        return report
