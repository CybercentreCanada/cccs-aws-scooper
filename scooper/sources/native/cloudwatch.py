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

from typing import Optional

from boto3 import client
from botocore.client import BaseClient

from scooper.core.config import ScooperConfig
from scooper.core.constants import ORG
from scooper.core.utils.logger import get_logger
from scooper.core.utils.organizations import get_all_accounts
from scooper.core.utils.paginate import paginate
from scooper.core.utils.sts import assume_role
from scooper.sources import LogSource
from scooper.sources.report import LoggingReport

_logger = get_logger()


class CloudWatch(LogSource):
    def __init__(self, level: str, scooper_config: ScooperConfig) -> None:
        super().__init__(level)
        self._scooper_config = scooper_config
        self._service = self.__class__.__name__
        self._client = client("logs")

    def _get_log_groups(self, logs_client: Optional[BaseClient] = None) -> list[dict]:
        if logs_client is None:
            # For account-level use
            _client = self._client
        else:
            # For org-level use
            _client = logs_client

        return paginate(_client, "describe_log_groups", "logGroups")

    def enumerate(self) -> dict:
        _logger.info("Enumerating %s-level %s Log Groups...", self.level, self._service)

        if self.level == ORG:
            cw_log_groups = {}
            for account in get_all_accounts():
                account_id = account["Id"]
                _logger.info(
                    "Enumerating Log Groups in account '%s' (%s)...",
                    account["Name"],
                    account_id,
                )
                if account_id == self._scooper_config.account_id:
                    cw_log_groups[account_id] = self._get_log_groups()
                else:
                    logs_client = assume_role(
                        role_arn=f"arn:aws:iam::{account_id}:role/{self._scooper_config.org_role_name}",
                        service="logs",
                    )
                    if logs_client is not None:
                        cw_log_groups[account_id] = self._get_log_groups(logs_client)
            return cw_log_groups
        else:
            return self._get_log_groups()

    def get_report(self) -> LoggingReport:
        log_groups = self.enumerate()

        return LoggingReport(
            service=self._service,
            logging_enabled=len(log_groups) > 0,
            details={
                "level": self.level,
                "log_groups": log_groups,
            },
        )
