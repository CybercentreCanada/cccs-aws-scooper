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

from click import Choice, option

from scooper.core.cli.callbacks import lifecycle_tokenizer
from scooper.core.constants import ACCOUNT, ORG

cloudtrail_scoop = option(
    "--cloudtrail-scoop",
    is_flag=True,
    default=False,
    help="Perform historical CloudTrail data collection of current account and region",
    required=False,
)
configure_logging = option(
    "--configure-logging",
    is_flag=True,
    default=False,
    help="Deploy Scooper resources",
    required=False,
)
destroy = option(
    "--destroy",
    is_flag=True,
    default=False,
    help="Destroy Scooper resources",
    required=False,
)
level = option(
    "--level",
    help="Level of enumeration/resource creation to perform",
    type=Choice([ACCOUNT, ORG]),
    default=ACCOUNT,
)
lifecycle_rules = option(
    "--lifecycle-rules",
    help="Comma-separated S3 storage class(es) and duration(s) in days of lifecycle protection for Scooper S3 bucket",
    required=False,
    callback=lifecycle_tokenizer,
)
role_name = option(
    "--role-name",
    help="Name of role with organization account access",
    default="OrganizationAccountAccessRole",
)
