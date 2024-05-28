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
from json import JSONEncoder, dump, dumps
from pathlib import Path

from boto3 import client

from scooper.utils.logger import setup_logging

logger = setup_logging(__name__, is_module=False)


class ScooperEncoder(JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        elif isinstance(obj, set):
            return list(obj)
        return JSONEncoder.default(self, obj)


def write_dict_to_s3(
    obj: dict, bucket_name: str, object_key: str, s3_client=client("s3")
) -> None:
    obj_as_json = dumps(obj, cls=ScooperEncoder, indent=2).encode()
    s3_client.put_object(Body=obj_as_json, Bucket=bucket_name, Key=object_key)

    logger.info("Object written to s3://%s/%s", bucket_name, object_key)


def write_dict_to_file(obj: dict, path: Path) -> None:
    if not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w") as out:
        dump(obj, out, cls=ScooperEncoder, indent=2)

    logger.info("Object written to %s", path)
