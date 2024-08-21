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

import aws_cdk as cdk
import aws_cdk.aws_cloudtrail as cloudtrail
import aws_cdk.aws_iam as iam
import aws_cdk.aws_s3 as s3
from constructs import Construct

from scooper.core.constants import ORG
from scooper.sources.report import LoggingReport


class CloudTrail(cdk.NestedStack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        logging_report: LoggingReport,
        scooper_bucket: s3.Bucket,
        **_,
    ) -> None:
        super().__init__(scope, construct_id)

        trail_name = "{}Trail-Scooper".format(
            logging_report.details["level"].capitalize()
        )
        cloudtrail_service_principal = iam.ServicePrincipal("cloudtrail.amazonaws.com")

        scooper_bucket.add_to_resource_policy(
            iam.PolicyStatement(
                sid="CloudTrailAclCheck",
                principals=[cloudtrail_service_principal],
                actions=["s3:GetBucketAcl"],
                resources=[scooper_bucket.bucket_arn],
                conditions={
                    "StringEquals": {
                        "aws:SourceArn": f"arn:aws:cloudtrail:{self.region}:{self.account}:trail/{trail_name}"
                    }
                },
            )
        )
        scooper_bucket.add_to_resource_policy(
            iam.PolicyStatement(
                sid="CloudTrailWrite",
                principals=[cloudtrail_service_principal],
                actions=["s3:PutObject"],
                resources=[scooper_bucket.arn_for_objects("*")],
                conditions={
                    "StringEquals": {
                        "s3:x-amz-acl": "bucket-owner-full-control",
                        "aws:SourceArn": f"arn:aws:cloudtrail:{self.region}:{self.account}:trail/{trail_name}",
                    }
                },
            )
        )
        scooper_bucket.encryption_key.grant_encrypt_decrypt(
            cloudtrail_service_principal
        )

        self.cloudtrail = cloudtrail.Trail(
            self,
            trail_name,
            trail_name=trail_name,
            bucket=scooper_bucket,
            s3_key_prefix=logging_report.service,
            encryption_key=scooper_bucket.encryption_key,
            is_organization_trail=logging_report.details["level"] == ORG,
        )
