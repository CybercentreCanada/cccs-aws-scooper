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
from datetime import timedelta
from typing import Literal

from boto3 import Session, client
from botocore.exceptions import ClientError
from pydantic import BaseModel
from yaml import safe_dump as yaml_dump

from scooper.core.constants import ORG
from scooper.core.pki import CertificateAuthority, LeafCertificate
from scooper.core.utils.sts import STS_CLIENT, get_all_account_sessions


@dataclass
class ScooperConfig:
    level: Literal["account", "org"]
    cross_account_role_name: str
    standalone: bool = False

    certificate_authority: CertificateAuthority = field(init=False)
    leaf_certificate: LeafCertificate = field(init=False)

    root_id: str = field(init=False)
    org_id: str = field(init=False)
    account_id: str = field(init=False)
    all_account_sessions: dict[str, Session] = field(init=False)

    def __post_init__(self) -> None:
        self.account_id = STS_CLIENT.get_caller_identity()["Account"]

        if self.is_org_level():
            try:
                org_client = client("organizations")
                self.root_id = org_client.list_roots()["Roots"][0]["Id"]
                self.org_id = org_client.describe_organization()["Organization"]["Id"]
                self.all_account_sessions = get_all_account_sessions(self)
            except ClientError as e:
                raise SystemExit(
                    "You need to run Scooper from your organization's management account for org-level enumeration/deployment."
                ) from e

        if self.standalone:
            self.certificate_authority = CertificateAuthority(timedelta(days=365))
            self.leaf_certificate = LeafCertificate(self.certificate_authority)

    def is_org_level(self) -> bool:
        return self.level == ORG


class IAMRA(BaseModel):
    reader_role_arn: str
    trust_anchor_arn: str
    profile_arn: str
    certificate_path: str
    private_key_path: str


class OutputConfig(BaseModel):
    identifier: str
    account_id: str
    region: str
    bucket_name: str
    queue_url: str
    scooper_custom_query_role_name: str

    iamra: IAMRA

    def model_dump_yaml(self) -> None:
        with open("output_config.yaml", "w") as f:
            yaml_dump(self.model_dump(), f)
