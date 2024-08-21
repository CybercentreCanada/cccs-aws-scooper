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

from importlib import import_module

import aws_cdk as cdk
import aws_cdk.aws_iam as iam
import aws_cdk.aws_kinesis as kinesis
import aws_cdk.aws_kinesisfirehose as firehose
import aws_cdk.aws_kms as kms
import aws_cdk.aws_logs as logs
import aws_cdk.aws_s3 as s3
from constructs import Construct

from scooper.core.cli.callbacks import S3LifecycleRule
from scooper.core.config import ScooperConfig
from scooper.core.constants import ORG
from scooper.core.utils.logger import get_logger
from scooper.sources.report import LoggingReport

_logger = get_logger()


class Scooper(cdk.Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        scooper_config: ScooperConfig,
        logging_reports: list[LoggingReport],
        lifecycle_rules: list[S3LifecycleRule],
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.scooper_config = scooper_config
        self.is_org_level = self.scooper_config.level == ORG
        self.reports = logging_reports
        self.lifecycle_rules = lifecycle_rules

        self._scooper_key = None
        self._scooper_bucket = None
        self._databricks_reader = None
        self._cwl_role = None
        self._firehose_role = None
        self._scooper_stream = None
        self._scooper_firehose = None
        self._scooper_cross_account = None

        for logging_report in logging_reports:
            if self.check_logging(logging_report):
                if logging_report.logging_enabled:
                    _logger.info(
                        "%s is enabled and owned by Scooper!", logging_report.service
                    )
                else:
                    _logger.info("%s is disabled!", logging_report.service)
                    _logger.info("Configuring %s logging...", logging_report.service)
                try:
                    module = import_module(
                        f"scooper.cdk.stacks.{logging_report.service.lower()}"
                    )
                    stack = getattr(module, logging_report.service)
                    stack(
                        self,
                        f"{logging_report.service}Stack",
                        logging_report=logging_report,
                        scooper_bucket=self.scooper_bucket,
                        scooper_config=self.scooper_config,
                    )
                except ModuleNotFoundError:
                    _logger.warning(
                        "CDK stack for '%s' not found!", logging_report.service
                    )
            elif logging_report.logging_enabled and not logging_report.owned_by_scooper:
                _logger.info("%s is enabled!", logging_report.service)

        cdk.CfnOutput(self, "BucketName", value=self.scooper_bucket.bucket_name)

    def check_logging(self, logging_report: LoggingReport) -> bool:
        return (logging_report.logging_enabled and logging_report.owned_by_scooper) or (
            not logging_report.logging_enabled and not logging_report.owned_by_scooper
        )

    @property
    def scooper_key(self) -> kms.Key:
        if self._scooper_key is None:
            self._scooper_key = kms.Key(
                self,
                "ScooperKey",
                description="Key used by Scooper for SSE of log objects",
                enable_key_rotation=True,
            )

            if self.is_org_level and self.scooper_config.experimental_features:
                self._scooper_key.add_to_resource_policy(
                    iam.PolicyStatement(
                        principals=[self.firehose_role],
                        actions=["kms:Decrypt", "kms:GenerateDataKey"],
                        resources=["*"],
                    )
                )
                self._scooper_key.grant_encrypt_decrypt(self.firehose_role)

        return self._scooper_key

    @property
    def scooper_bucket(self) -> s3.Bucket:
        if self._scooper_bucket is None:
            self._scooper_bucket = s3.Bucket(
                self,
                "ScooperBucket",
                encryption_key=self.scooper_key,
                enforce_ssl=True,
                versioned=True,
            )

            transitions = []
            expiry = None

            for lifecycle_rule in self.lifecycle_rules:
                if isinstance(lifecycle_rule.storage_class, s3.StorageClass):
                    transitions.append(
                        s3.Transition(
                            storage_class=lifecycle_rule.storage_class,
                            transition_after=cdk.Duration.days(lifecycle_rule.duration),
                        )
                    )
                else:
                    expiry = lifecycle_rule.duration

            if transitions or expiry is not None:
                self._scooper_bucket.add_lifecycle_rule(
                    enabled=True,
                    expiration=(
                        cdk.Duration.days(expiry) if expiry is not None else None
                    ),
                    noncurrent_versions_to_retain=1,
                    transitions=transitions if transitions else None,
                )

            if self.scooper_config.databricks_reader:
                # Allow Databricks role to read bucket
                self._scooper_bucket.add_to_resource_policy(
                    iam.PolicyStatement(
                        principals=[self.databricks_reader.role],
                        actions=["s3:GetObject*", "s3:GetBucket*", "s3:List*"],
                        resources=[
                            self._scooper_bucket.bucket_arn,
                            self._scooper_bucket.arn_for_objects("*"),
                        ],
                    )
                )
                self._scooper_bucket.grant_read(self.databricks_reader.role)
                # Allow Databricks role to decrypt contents of bucket
                self.scooper_key.add_to_resource_policy(
                    iam.PolicyStatement(
                        principals=[self.databricks_reader.role],
                        actions=["kms:Decrypt"],
                        resources=["*"],
                    )
                )
                self.scooper_key.grant_decrypt(self.databricks_reader.role)

            if self.is_org_level and self.scooper_config.experimental_features:
                self._scooper_bucket.add_to_resource_policy(
                    iam.PolicyStatement(
                        principals=[self.firehose_role],
                        actions=[
                            "s3:AbortMultipartUpload",
                            "s3:GetBucketLocation",
                            "s3:GetObject",
                            "s3:ListBucket",
                            "s3:ListBucketMultipartUploads",
                            "s3:PutObject",
                        ],
                        resources=[
                            self._scooper_bucket.bucket_arn,
                            self.scooper_bucket.arn_for_objects("*"),
                        ],
                    )
                )
                self._scooper_bucket.grant_read_write(self.firehose_role)

        return self._scooper_bucket

    @property
    def databricks_reader(self):
        if self._databricks_reader is None:
            self._databricks_reader_user = iam.User(
                self,
                "DatabricksReaderUser",
                user_name="DatabricksReaderUser",
            )
            self._databricks_reader_role = iam.Role(
                self,
                "DatabricksReaderRole",
                role_name="DatabricksReaderRole",
                assumed_by=self._databricks_reader_user,
            )
            self._databricks_reader_user.add_to_policy(
                iam.PolicyStatement(
                    actions=["sts:AssumeRole"],
                    resources=[self._databricks_reader_role.role_arn],
                )
            )

            class DatabricksReader:
                def __init__(self, user: iam.User, role: iam.Role) -> None:
                    self.user = user
                    self.role = role

            self._databricks_reader = DatabricksReader(
                user=self._databricks_reader_user, role=self._databricks_reader_role
            )

        return self._databricks_reader

    @property
    def cwl_role(self) -> iam.Role:
        if (
            self._cwl_role is None
            and self.is_org_level
            and self.scooper_config.experimental_features
        ):
            self._cwl_role = iam.Role(
                self,
                "CWLRole",
                role_name="CWLtoKinesisRole",
                assumed_by=iam.ServicePrincipal("logs.amazonaws.com"),
            )
            account_ids = []

            for report in self.reports:
                if report.service == "VPC":
                    account_ids = report.details["flow_logs"].keys()

            self._cwl_role.assume_role_policy.add_statements(
                iam.PolicyStatement(
                    principals=[iam.ServicePrincipal("logs.amazonaws.com")],
                    actions=["sts:AssumeRole"],
                    conditions={
                        "StringLike": {
                            "aws:SourceArn": [
                                *[
                                    f"arn:aws:logs:{self.region}:{source_account_id}:*"
                                    for source_account_id in account_ids
                                ],
                                f"arn:aws:logs:{self.region}:{self.account}:*",
                            ]
                        }
                    },
                )
            )
            self._cwl_role.assume_role_policy.add_statements(
                iam.PolicyStatement(
                    principals=[iam.ServicePrincipal("firehose.amazonaws.com")],
                    actions=["sts:AssumeRole"],
                )
            )

        return self._cwl_role

    @property
    def scooper_stream(self) -> kinesis.Stream:
        if (
            self._scooper_stream is None
            and self.is_org_level
            and self.scooper_config.experimental_features
        ):
            self._scooper_stream = kinesis.Stream(
                self, "ScooperStream", stream_name="ScooperStream"
            )
            self.stream_grant = self._scooper_stream.grant_read_write(self.cwl_role)

        return self._scooper_stream

    @property
    def firehose_role(self) -> iam.Role:
        if self._firehose_role is None and self.scooper_config.experimental_features:
            self._firehose_role = iam.Role(
                self,
                "FirehoseRole",
                role_name="FirehoseRole",
                assumed_by=iam.ServicePrincipal("firehose.amazonaws.com"),
            )

        return self._firehose_role

    @property
    def scooper_firehose(self) -> firehose.CfnDeliveryStream:
        if (
            self._scooper_firehose is None
            and self.is_org_level
            and self.scooper_config.experimental_features
        ):
            self._scooper_firehose = firehose.CfnDeliveryStream(
                self,
                "ScooperFirehose",
                delivery_stream_name="ScooperFirehose",
                delivery_stream_type="KinesisStreamAsSource",
                kinesis_stream_source_configuration=firehose.CfnDeliveryStream.KinesisStreamSourceConfigurationProperty(
                    kinesis_stream_arn=self.scooper_stream.stream_arn,
                    role_arn=self.cwl_role.role_arn,
                ),
                extended_s3_destination_configuration=firehose.CfnDeliveryStream.ExtendedS3DestinationConfigurationProperty(
                    bucket_arn=self.scooper_bucket.bucket_arn,
                    role_arn=self.firehose_role.role_arn,
                    compression_format="GZIP",
                ),
            )
            self._scooper_firehose.node.add_dependency(self.cwl_role)
            self._scooper_firehose.node.add_dependency(self.firehose_role)

        return self._scooper_firehose

    @property
    def scooper_cross_account(self) -> logs.CrossAccountDestination:
        if (
            self._scooper_cross_account is None
            and self.is_org_level
            and self.scooper_config.experimental_features
        ):
            self._scooper_cross_account = logs.CrossAccountDestination(
                self,
                "ScooperCrossAccount",
                destination_name="ScooperCrossAccount",
                role=self.cwl_role,
                target_arn=self.scooper_stream.stream_arn,
            )
            self._scooper_cross_account.add_to_policy(
                iam.PolicyStatement(
                    principals=[iam.StarPrincipal()],
                    actions=["logs:PutSubscriptionFilter"],
                    resources=["*"],
                    conditions={
                        "StringEquals": {
                            "aws:PrincipalOrgID": [self.scooper_config.org_id]
                        }
                    },
                )
            )
            self._scooper_cross_account.node.add_dependency(self.scooper_stream)
            self._scooper_cross_account.node.add_dependency(self.stream_grant)

        return self._scooper_cross_account
