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

from datetime import datetime
from itertools import groupby
from typing import Iterator, Union

from boto3 import client
from botocore.exceptions import ClientError

from scooper.sources import LogSource
from scooper.sources.report import LoggingReport
from scooper.utils.enum import paginate
from scooper.utils.logger import setup_logging


class SSOMetadata(LogSource):
    def __init__(self, level: str) -> None:
        super().__init__()
        self._level = level
        self._services = "sso-admin", "identitystore", "ds"
        self._clients = {service: client(service) for service in self._services}
        self._logger = setup_logging(self.__class__.__name__)

    def _get_sso_users(self, identity_store_id: str) -> None:
        users = paginate(
            self._clients["identitystore"],
            "list_users",
            "Users",
            IdentityStoreId=identity_store_id,
        )
        for user in users:
            self._report["Users"].append(user)

    def _get_sso_groups(self, identity_store_id: str) -> None:
        groups = paginate(
            self._clients["identitystore"],
            "list_groups",
            "Groups",
            IdentityStoreId=identity_store_id,
        )
        for group in groups:
            group["GroupMemberships"] = self._get_group_membership_data(
                identity_store_id, group["GroupId"]
            )
            self._report["Groups"].append(group)

    def _get_group_membership_data(self, identity_store_id: str, group_id: str) -> list:
        group_memberships = paginate(
            self._clients["identitystore"],
            "list_group_memberships",
            "GroupMemberships",
            IdentityStoreId=identity_store_id,
            GroupId=group_id,
        )
        return group_memberships

    def _get_sso_permission_sets(self, instance_arn: str) -> None:
        permission_sets = paginate(
            self._clients["sso-admin"],
            "list_permission_sets",
            "PermissionSets",
            InstanceArn=instance_arn,
        )
        for permission in permission_sets:
            pset_data = self._clients["sso-admin"].describe_permission_set(
                InstanceArn=instance_arn, PermissionSetArn=permission
            )["PermissionSet"]
            pset_data["Accounts"] = self._get_accounts_for_provisioned_permission_set(
                pset_data["PermissionSetArn"], instance_arn
            )
            self._report["PermissionSets"].append(pset_data)

    def _get_accounts_for_provisioned_permission_set(
        self, pset_arn: str, instance_arn: str
    ) -> Union[list[dict[str, str], list[dict[str, str]]]]:
        accounts_for_provisioned_pset = paginate(
            self._clients["sso-admin"],
            "list_accounts_for_provisioned_permission_set",
            "AccountIds",
            InstanceArn=instance_arn,
            PermissionSetArn=pset_arn,
        )
        return [
            self._get_account_assignments(account_id, instance_arn, pset_arn)
            for account_id in accounts_for_provisioned_pset
        ]

    def _get_account_assignments(
        self, account_id: str, instance_arn: str, permission_set_arn: str
    ) -> Union[dict[str, str], list[dict[str, str]]]:
        account_assignments = paginate(
            self._clients["sso-admin"],
            "list_account_assignments",
            "AccountAssignments",
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
            self._clients["ds"],
            "describe_directories",
            "DirectoryDescriptions",
        )
        self._report["Directories"].extend(directories)

    def enumerate(self) -> Iterator[dict[str, str]]:
        self._logger.info("Enumerating %s...", self._services)
        try:
            instances = paginate(
                self._clients["sso-admin"],
                "list_instances",
                "Instances",
            )
            yield from instances
        except ClientError:
            self._logger.error("Can't enumerate %s", self._services, exc_info=True)
            yield from []

    def get_report(self) -> LoggingReport:
        self._report = {
            "event_time": datetime.utcnow(),
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

        return LoggingReport(
            service=self.__class__.__name__,
            enabled=any(self._report.values()),
            details=self._report,
            owned_by_scooper=True,
        )
