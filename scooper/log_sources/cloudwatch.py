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

from boto3 import client
from botocore.client import BaseClient
from botocore.exceptions import ClientError
from core.utils.paginate import paginate

from scooper.core.config import ScooperConfig
from scooper.core.utils.logger import get_logger
from scooper.log_sources import LogSource
from scooper.log_sources.report import LoggingReport

_logger = get_logger()


class CloudWatch(LogSource):
    def __init__(self, scooper_config: ScooperConfig) -> None:
        super().__init__(scooper_config)
        self._service = self.__class__.__name__
        self._client = client("logs")

    def _get_log_groups(self, logs_client: BaseClient | None = None) -> list[dict]:
        _client = self._client if logs_client is None else logs_client

        return paginate(
            client=_client, operation="describe_log_groups", array="logGroups"
        )

    def enumerate(self) -> dict:
        _logger.info("Enumerating %s-level %s Log Groups...", self.level, self._service)

        if self.scooper_config.is_org_level():
            cw_log_groups = {}

            for account_id, session in self.scooper_config.all_account_sessions.items():
                _logger.info("Enumerating Log Groups in account '%s'...", account_id)
                try:
                    cw_log_groups[account_id] = self._get_log_groups(
                        session.client("logs")
                    )
                except ClientError as e:
                    _logger.error(
                        "Failed to enumerate Log Groups in account '%s': %s",
                        account_id,
                        e,
                    )
                    cw_log_groups[account_id] = []

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
