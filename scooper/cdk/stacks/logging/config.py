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

from aws_cdk import NestedStack
from aws_cdk import aws_config as config
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from constructs import Construct

from scooper.core.config import ScooperConfig
from scooper.log_sources.report import LoggingReport


class Config(NestedStack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        logging_report: LoggingReport,
        scooper_bucket: s3.Bucket,
        scooper_config: ScooperConfig,
        **_,
    ) -> None:
        super().__init__(scope, construct_id)

        name = f"{scooper_config.deployment_config.level.capitalize()}Config-Scooper"
        config_service_principal = iam.ServicePrincipal("config.amazonaws.com")

        if scooper_config.is_org_level():
            condition = {"AWS:PrincipalOrgID": scooper_config.org_id}
            aggregator_role = iam.Role(
                self,
                "AggregatorRole",
                assumed_by=config_service_principal,
                managed_policies=[
                    iam.ManagedPolicy.from_aws_managed_policy_name(
                        "service-role/AWSConfigRoleForOrganizations"
                    )
                ],
            )
            config.CfnConfigurationAggregator(
                self,
                name,
                organization_aggregation_source=config.CfnConfigurationAggregator.OrganizationAggregationSourceProperty(
                    role_arn=aggregator_role.role_arn,
                    all_aws_regions=True,
                ),
                configuration_aggregator_name=name,
            )
        else:
            condition = {"AWS:SourceAccount": scooper_config.account_id}
            recorder_role = iam.Role(
                self,
                "RecorderRole",
                assumed_by=config_service_principal,
                managed_policies=[
                    iam.ManagedPolicy.from_aws_managed_policy_name(
                        "service-role/AWS_ConfigRole"
                    )
                ],
            )
            recorder_role.add_to_policy(
                iam.PolicyStatement(
                    actions=["s3:PutObject*", "s3:GetBucketAcl"], resources=["*"]
                )
            )
            recorder_role.add_to_policy(
                iam.PolicyStatement(
                    actions=["kms:Encrypt", "kms:GenerateDataKey"],
                    resources=[scooper_bucket.encryption_key.key_arn],
                )
            )
            config.CfnConfigurationRecorder(
                self,
                name,
                name=name,
                role_arn=recorder_role.role_arn,
                recording_group=config.CfnConfigurationRecorder.RecordingGroupProperty(
                    all_supported=True,
                    include_global_resource_types=True,
                    recording_strategy=config.CfnConfigurationRecorder.RecordingStrategyProperty(
                        use_only="ALL_SUPPORTED_RESOURCE_TYPES"
                    ),
                ),
            )
            config.CfnDeliveryChannel(
                self,
                "DeliveryChannel",
                name="ScooperConfigDeliveryChannel",
                s3_bucket_name=scooper_bucket.bucket_name,
                s3_key_prefix=logging_report.service,
                s3_kms_key_arn=scooper_bucket.encryption_key.key_arn,
                config_snapshot_delivery_properties=config.CfnDeliveryChannel.ConfigSnapshotDeliveryPropertiesProperty(
                    delivery_frequency="One_Hour"
                ),
            )

        scooper_bucket.add_to_resource_policy(
            iam.PolicyStatement(
                sid="AWSConfigBucketPermissionsCheck",
                principals=[config_service_principal],
                actions=["s3:GetBucketAcl"],
                resources=[scooper_bucket.bucket_arn],
                conditions={"StringEquals": condition},
            )
        )
        scooper_bucket.add_to_resource_policy(
            iam.PolicyStatement(
                sid="AWSConfigBucketExistenceCheck",
                principals=[config_service_principal],
                actions=["s3:ListBucket"],
                resources=[scooper_bucket.bucket_arn],
                conditions={"StringEquals": condition},
            )
        )
        scooper_bucket.add_to_resource_policy(
            iam.PolicyStatement(
                sid="AWSConfigBucketDelivery",
                principals=[config_service_principal],
                actions=["s3:PutObject"],
                resources=[scooper_bucket.arn_for_objects("*")],
                conditions={
                    "StringEquals": {
                        "s3:x-amz-acl": "bucket-owner-full-control",
                        **condition,
                    },
                },
            )
        )
        scooper_bucket.encryption_key.grant_encrypt_decrypt(config_service_principal)
