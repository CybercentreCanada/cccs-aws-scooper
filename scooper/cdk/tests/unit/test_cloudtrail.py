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

from moto import mock_cloudtrail

from scooper.core.constants import ACCOUNT


def put_trails(cloudtrail_client, s3_client):
    s3_client.create_bucket(Bucket="test-bucket")
    s3_client.put_bucket_versioning(
        Bucket="test-bucket", VersioningConfiguration={"Status": "Enabled"}
    )

    cloudtrail_client.create_trail(
        Name="cloudtrailskip",
        S3BucketName="test-bucket",
        S3KeyPrefix="string",
        IncludeGlobalServiceEvents=True,
        IsMultiRegionTrail=True,
        CloudWatchLogsLogGroupArn="string",
        CloudWatchLogsRoleArn="string",
        KmsKeyId="string",
        IsOrganizationTrail=True,
        TagsList=[
            {"Key": "string", "Value": "string"},
        ],
    )

    cloudtrail_client.create_trail(
        Name="cloudtrailreal",
        S3BucketName="test-bucket",
        S3KeyPrefix="string",
        IncludeGlobalServiceEvents=True,
        IsMultiRegionTrail=True,
        CloudWatchLogsLogGroupArn="string",
        CloudWatchLogsRoleArn="string",
        KmsKeyId="string",
        IsOrganizationTrail=False,
        TagsList=[
            {"Key": "string", "Value": "string"},
        ],
    )

    cloudtrail_client.create_trail(
        Name="cloudtrailskip2",
        S3BucketName="test-bucket",
        S3KeyPrefix="string",
        IncludeGlobalServiceEvents=False,
        IsMultiRegionTrail=False,
        CloudWatchLogsLogGroupArn="string",
        CloudWatchLogsRoleArn="string",
        KmsKeyId="string",
        IsOrganizationTrail=False,
        TagsList=[
            {"Key": "string", "Value": "string"},
        ],
    )


@mock_cloudtrail
def test_enumerate(cloudtrail_client, s3_client, sts_client):
    from scooper.sources.native.cloudtrail import CloudTrail

    put_trails(cloudtrail_client, s3_client)
    report = CloudTrail(ACCOUNT).report
    confg = report.details["configuration"]
    assert (
        report.logging_enabled
        and confg["S3BucketName"] == "test-bucket"
        and not report.owned_by_scooper
    )


@mock_cloudtrail
def test_disabled(sts_client):
    from scooper.sources.native.cloudtrail import CloudTrail

    report = CloudTrail(ACCOUNT).report
    assert not report.logging_enabled
