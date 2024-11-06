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

from dataclasses import dataclass, field
from typing import Literal, Optional

from botocore.exceptions import ClientError

from scooper.core.constants import ORG
from scooper.core.utils.organizations import ORG_CLIENT
from scooper.core.utils.sts import STS_CLIENT


@dataclass
class ScooperConfig:
    level: Literal["account", "org"]
    org_role_name: Optional[str] = None
    databricks_reader: bool = False
    experimental_features: bool = False

    root_id: str = field(init=False)
    org_id: str = field(init=False)

    def __post_init__(self) -> None:
        if self.level == ORG:
            try:
                self.root_id = ORG_CLIENT.list_roots()["Roots"][0]["Id"]
                self.org_id = ORG_CLIENT.describe_organization()["Organization"]["Id"]
            except ClientError:
                raise SystemExit(
                    "You need to run Scooper from your organization's management account for org-level enumeration"
                )

        self.account_id = STS_CLIENT.get_caller_identity()["Account"]
