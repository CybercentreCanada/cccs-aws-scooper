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
from tqdm import tqdm

from scooper.utils.logger import get_logger

_logger = get_logger()


def paginate(client: type[BaseClient], command: str, array: str, **kwargs):
    elements = []
    paginator = client.get_paginator(command)

    try:
        with tqdm(
            desc=f"Getting {client.meta.service_model.service_name} data", leave=False
        ) as pbar:
            for page in paginator.paginate(**kwargs):
                elements.extend(page.get(array, []))
                pbar.update()
    except Exception as e:
        _logger.error("Pagination failed: %s", e)

    return elements


def accounts_iterator() -> list:
    try:
        accounts = paginate(
            client("organizations"),
            "list_accounts",
            "Accounts",
        )
        return accounts
    except ClientError:
        return []
