from datetime import datetime, timezone
from itertools import groupby
from os import getenv
from typing import Generator

from aws_lambda_powertools import Logger
from botocore.exceptions import ClientError
from core import constants
from core.utils.paginate import paginate
from core.utils.sts import assume_role


class SSOMetadata:
    def __init__(self, mgmt_account_id: str) -> None:
        self._services = "sso-admin", "identitystore", "ds"

        # Assume CCCS reader role
        cccs_reader_role_session = assume_role(
            role_arn=getenv("CCCS_READER_ROLE_ARN"),
            role_session_name=f"{getenv('AWS_LAMBDA_FUNCTION_NAME')}-Assume-CCCSReaderRole",
        )
        cccs_reader_role_sts_client = cccs_reader_role_session.client("sts")

        # Assume global reader role in partner's management account
        self._clients = {
            service: assume_role(
                role_arn=constants.CBS_GLOBAL_READER_ROLE_TEMPLATE.substitute(
                    account=mgmt_account_id
                ),
                role_session_name=f"CBS-{service}-Metadata",
                sts_client=cccs_reader_role_sts_client,
            ).client(service)
            for service in self._services
        }
        self._logger = Logger(service=self.__class__.__name__)
        self.report = self.get_report()

    def _get_sso_users(self, identity_store_id: str) -> None:
        users = paginate(
            client=self._clients["identitystore"],
            command="list_users",
            array="Users",
            logger=self._logger,
            IdentityStoreId=identity_store_id,
        )
        for user in users:
            self._report["Users"].append(user)

    def _get_sso_groups(self, identity_store_id: str) -> None:
        groups = paginate(
            client=self._clients["identitystore"],
            command="list_groups",
            array="Groups",
            logger=self._logger,
            IdentityStoreId=identity_store_id,
        )
        for group in groups:
            group["GroupMemberships"] = self._get_group_membership_data(
                identity_store_id, group["GroupId"]
            )
            self._report["Groups"].append(group)

    def _get_group_membership_data(self, identity_store_id: str, group_id: str):
        group_memberships = paginate(
            client=self._clients["identitystore"],
            command="list_group_memberships",
            array="GroupMemberships",
            logger=self._logger,
            IdentityStoreId=identity_store_id,
            GroupId=group_id,
        )
        return group_memberships

    def _get_sso_permission_sets(self, instance_arn: str) -> None:
        permission_sets = paginate(
            client=self._clients["sso-admin"],
            command="list_permission_sets",
            array="PermissionSets",
            logger=self._logger,
            InstanceArn=instance_arn,
        )
        for permission in permission_sets:
            pset_data = self._clients["sso-admin"].describe_permission_set(
                InstanceArn=instance_arn, PermissionSetArn=permission
            )["PermissionSet"]
            pset_data["Policies"] = self._get_permission_set_policies(
                pset_data["PermissionSetArn"], instance_arn
            )
            pset_data["Accounts"] = self._get_accounts_for_provisioned_permission_set(
                pset_data["PermissionSetArn"], instance_arn
            )
            self._report["PermissionSets"].append(pset_data)

    def _get_permission_set_policies(
        self, pset_arn: str, instance_arn: str
    ) -> dict[str, list[dict[str, str]] | str | dict[str, dict[str, str]]]:
        policies = {}

        if managed_policies := paginate(
            client=self._clients["sso-admin"],
            command="list_managed_policies_in_permission_set",
            array="AttachedManagedPolicies",
            logger=self._logger,
            InstanceArn=instance_arn,
            PermissionSetArn=pset_arn,
        ):
            policies["ManagedPolicies"] = managed_policies

        if customer_managed_policy_references := paginate(
            client=self._clients["sso-admin"],
            command="list_customer_managed_policy_references_in_permission_set",
            array="CustomerManagedPolicyReferences",
            logger=self._logger,
            InstanceArn=instance_arn,
            PermissionSetArn=pset_arn,
        ):
            policies["CustomerManagedPolicyReferences"] = (
                customer_managed_policy_references
            )

        if inline_policy := self._clients[
            "sso-admin"
        ].get_inline_policy_for_permission_set(
            InstanceArn=instance_arn,
            PermissionSetArn=pset_arn,
        )[
            "InlinePolicy"
        ]:
            policies["InlinePolicy"] = inline_policy

        try:
            permissions_boundary = self._clients[
                "sso-admin"
            ].get_permissions_boundary_for_permission_set(
                InstanceArn=instance_arn,
                PermissionSetArn=pset_arn,
            )[
                "PermissionsBoundary"
            ]
        except self._clients["sso-admin"].exceptions.ResourceNotFoundException:
            permissions_boundary = {}

        if permissions_boundary:
            policies["PermissionsBoundary"] = permissions_boundary

        return policies

    def _get_accounts_for_provisioned_permission_set(
        self, pset_arn: str, instance_arn: str
    ) -> list[dict[str, str] | list[dict[str, str]]]:
        accounts_for_provisioned_pset = paginate(
            client=self._clients["sso-admin"],
            command="list_accounts_for_provisioned_permission_set",
            array="AccountIds",
            logger=self._logger,
            InstanceArn=instance_arn,
            PermissionSetArn=pset_arn,
        )
        return [
            self._get_account_assignments(account_id, instance_arn, pset_arn)
            for account_id in accounts_for_provisioned_pset
        ]

    def _get_account_assignments(
        self, account_id: str, instance_arn: str, permission_set_arn: str
    ) -> dict[str, str] | list[dict[str, str]]:
        account_assignments = paginate(
            client=self._clients["sso-admin"],
            command="list_account_assignments",
            array="AccountAssignments",
            logger=self._logger,
            InstanceArn=instance_arn,
            AccountId=account_id,
            PermissionSetArn=permission_set_arn,
        )

        account_assignments_by_principal = [
            {**lst[0], "PrincipalId": [d["PrincipalId"] for d in lst]}
            for lst in [
                list(group)
                for _, group in groupby(
                    account_assignments, key=lambda d: (d["PrincipalType"])
                )
            ]
        ]

        if len(account_assignments_by_principal) == 1:
            return account_assignments_by_principal[0]
        elif len(account_assignments_by_principal) > 1:
            return account_assignments_by_principal

    def _get_sso_directories(self) -> None:
        directories = paginate(
            client=self._clients["ds"],
            command="describe_directories",
            array="DirectoryDescriptions",
            logger=self._logger,
        )
        self._report["Directories"].extend(directories)

    def enumerate(self) -> Generator[dict[str, str], None, None] | None:
        self._logger.info("Enumerating %s...", self._services)
        try:
            instances = paginate(
                client=self._clients["sso-admin"],
                command="list_instances",
                array="Instances",
                logger=self._logger,
            )
            yield from instances
        except ClientError:
            self._logger.error("Can't enumerate %s", self._services, exc_info=True)
            yield from []

    def get_report(self) -> dict:
        self._report = {
            "event_time": datetime.now(timezone.utc),
            "Users": [],
            "Groups": [],
            "PermissionSets": [],
            "Directories": [],
        }
        for instance in self.enumerate():
            self._get_sso_users(instance["IdentityStoreId"])
            self._get_sso_groups(instance["IdentityStoreId"])
            self._get_sso_permission_sets(instance["InstanceArn"])
        self._get_sso_directories()

        return self._report
