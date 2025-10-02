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

from string import Template
from typing import TYPE_CHECKING

from boto3 import Session, client
from botocore.exceptions import ClientError
from cbs_common.aws.boto_types import DataRequest
from cbs_common.aws.utilities import BotoHelper, assume_role

from scooper.core.utils.logger import get_logger

if TYPE_CHECKING:
    from scooper.core.config import ScooperConfig

STS_CLIENT = client("sts")
_logger = get_logger()


def get_all_account_sessions(
    scooper_config: "ScooperConfig",
) -> dict[str, Session]:
    """Get all account sessions in organization."""
    all_member_account_sessions: dict[str, Session] = {}
    cross_account_role_template = Template(
        f"arn:aws:iam::$account:role/{scooper_config.cross_account_role_name}"
    )

    org_client = BotoHelper("organizations")
    data_request = DataRequest(method="list_accounts", array_key="Accounts")
    accounts = org_client(data_request)

    for account in accounts:
        account_id = account["Id"]
        role_arn = cross_account_role_template.substitute(account=account_id)
        try:
            all_member_account_sessions[account_id] = assume_role(
                role_arn=role_arn, sts_client=STS_CLIENT
            )
        except ClientError as e:
            if e.response["Error"]["Code"] == "AccessDenied":
                if account_id == scooper_config.account_id:
                    all_member_account_sessions[account_id] = Session()
                else:
                    _logger.exception("Failed to assume '%s'", role_arn)
            else:
                raise

    return all_member_account_sessions
