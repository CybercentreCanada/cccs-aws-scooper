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

from boto3 import Session
from botocore.config import Config
from botocore.exceptions import ClientError
from cbs_common.aws.boto_types import DataRequest
from cbs_common.aws.iam_metadata import IAMMetadata as CBSCommonIAMMetadata
from cbs_common.aws.utilities import BotoHelper, assume_role

from scooper.core.constants import ORG
from scooper.core.utils.logger import get_logger

config = Config(retries={"mode": "adaptive", "max_attempts": 16})
_logger = get_logger()


class IAMMetadata(CBSCommonIAMMetadata):
    def __init__(
        self, level: str, organizational_account_access_role_template: Template
    ) -> None:
        self._clients = {}
        session = Session()
        sts_client = session.client("sts")
        current_account_id = sts_client.get_caller_identity()["Account"]

        if level == ORG:
            org_client = BotoHelper("organizations")
            data_request = DataRequest(method="list_accounts", array_key="Accounts")
            accounts = org_client(data_request)
            for account in accounts:
                if account["Id"] != current_account_id:
                    account_id = account["Id"]
                    role_arn = organizational_account_access_role_template.substitute(
                        account=account_id
                    )
                    try:
                        self._clients[account_id] = assume_role(
                            role_arn=role_arn, sts_client=sts_client
                        ).client("iam", config=config)
                    except ClientError as e:
                        if e.response["Error"]["Code"] == "AccessDenied":
                            _logger.exception("Failed to assume '%s'", role_arn)
                        else:
                            raise

        self._clients[current_account_id] = session.client("iam", config=config)
