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

from scooper.core.constants import ACCOUNT, ORG, SCOOPER
from scooper.core.utils.logger import get_logger
from scooper.core.utils.paginate import paginate
from scooper.sources import LogSource
from scooper.sources.report import LoggingReport

_logger = get_logger()


class CloudTrail(LogSource):
    def __init__(self, level: str) -> None:
        super().__init__(level)
        self._service = self.__class__.__name__
        self._client = client(self._service.lower())

    def enumerate(self) -> list[dict]:
        _logger.info("Enumerating %s...", self._service)
        trails = paginate(self._client, "list_trails", "Trails")

        # Remove shadow trails
        trails = self._client.describe_trails(
            trailNameList=[trail["TrailARN"] for trail in trails],
            includeShadowTrails=False,
        )["trailList"]

        return [self._client.get_trail(Name=trail["Name"])["Trail"] for trail in trails]

    def get_report(self) -> LoggingReport:
        logging_enabled = False

        for trail in (trails := self.enumerate()):
            if (
                (trail["IsOrganizationTrail"] and self.level == ORG)
                or (not trail["IsOrganizationTrail"] and self.level == ACCOUNT)
                and trail["IncludeGlobalServiceEvents"]
                and trail["IsMultiRegionTrail"]
            ):
                if trail["HasCustomEventSelectors"]:
                    event_selectors = self._client.get_event_selectors(
                        TrailName=trail["Name"]
                    )
                    del event_selectors["TrailARN"]
                    del event_selectors["ResponseMetadata"]
                    trail.update(event_selectors)
                else:
                    _logger.info(
                        "%s trail '%s' is already configured!",
                        self.level.capitalize(),
                        trail["Name"],
                    )
                    logging_enabled = True

        return LoggingReport(
            service=self._service,
            logging_enabled=logging_enabled,
            details={
                "level": self.level,
                "trails": trails,
            },
            owned_by_scooper=any(
                SCOOPER.lower() in trail["Name"].lower() for trail in trails
            ),
        )
