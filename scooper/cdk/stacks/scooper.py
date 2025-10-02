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

from aws_cdk import CfnOutput, CfnResource, Duration, Fn, NestedStack, Stack
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as events_targets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_kms as kms
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_sqs as sqs
from constructs import Construct
from cryptography.hazmat.primitives.serialization import Encoding

from scooper.cdk.custom_constructs.role import Role
from scooper.cdk.stacks.custom_queries.stack import CustomQueries
from scooper.core.cli.callbacks import S3LifecycleRule
from scooper.core.config import ScooperConfig
from scooper.core.constants import SCOOPER
from scooper.core.lambda_layer import CBS_COMMON_LAMBDA_LAYER_ARN
from scooper.core.utils.logger import get_logger
from scooper.log_sources.report import LoggingReport

_logger = get_logger()


class Scooper(Stack):
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
        self.lifecycle_rules = lifecycle_rules

        self._scooper_bucket = None
        self._scooper_queue = None
        self._scooper_reader_role = None

        for logging_report in logging_reports:
            if logging_report.cdk_needed():
                if logging_report.logging_enabled:
                    _logger.info(
                        "%s is enabled and owned by Scooper!", logging_report.service
                    )
                else:
                    _logger.info("%s is disabled!", logging_report.service)
                    _logger.info("Configuring %s logging...", logging_report.service)
                try:
                    module = import_module(
                        f"scooper.cdk.nested_stacks.{logging_report.service.lower()}"
                    )
                    stack: NestedStack = getattr(module, logging_report.service)
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

        CfnOutput(self, "BucketName", value=self.scooper_bucket.bucket_name)

        if self.scooper_config.standalone:
            custom_queries_stack = CustomQueries(
                self,
                "CustomQueriesStack",
                scooper_config=self.scooper_config,
                scooper_reader_role=self.scooper_reader_role,
            )

            CfnOutput(self, "Region", value=self.region)
            CfnOutput(self, "QueueUrl", value=self.scooper_queue.queue_url)
            CfnOutput(self, "ReaderRoleArn", value=self.scooper_reader_role.role_arn)
            CfnOutput(
                self,
                "ScooperCustomQueryRoleName",
                value=custom_queries_stack.role_name,
            )
            CfnOutput(
                self,
                "TrustAnchorArn",
                value=Fn.get_att(
                    self.trust_anchor.logical_id, "TrustAnchorArn"
                ).to_string(),
            )
            CfnOutput(
                self,
                "ProfileArn",
                value=Fn.get_att(self.profile.logical_id, "ProfileArn").to_string(),
            )

    @property
    def scooper_bucket(self) -> s3.Bucket:
        if self._scooper_bucket is None:
            encryption_key = kms.Key(
                self,
                "ScooperBucketKey",
                alias="scooper/bucket",
                description="Key used by Scooper for SSE of log objects",
                enable_key_rotation=True,
            )

            self._scooper_bucket = s3.Bucket(
                self,
                "ScooperBucket",
                encryption_key=encryption_key,
                event_bridge_enabled=True,
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
                            transition_after=Duration.days(lifecycle_rule.duration),
                        )
                    )
                else:
                    expiry = lifecycle_rule.duration

            if transitions or expiry is not None:
                self._scooper_bucket.add_lifecycle_rule(
                    enabled=True,
                    expiration=(Duration.days(expiry) if expiry is not None else None),
                    noncurrent_versions_to_retain=1,
                    transitions=transitions if transitions else None,
                )

            if self.scooper_config.standalone:
                # Allow Databricks role to read bucket
                self._scooper_bucket.add_to_resource_policy(
                    iam.PolicyStatement(
                        principals=[self.scooper_reader_role],
                        actions=["s3:GetObject*", "s3:GetBucket*", "s3:List*"],
                        resources=[
                            self._scooper_bucket.bucket_arn,
                            self._scooper_bucket.arn_for_objects("*"),
                        ],
                    )
                )
                self._scooper_bucket.grant_read(self.scooper_reader_role)
                # Allow Databricks role to decrypt contents of bucket
                encryption_key.add_to_resource_policy(
                    iam.PolicyStatement(
                        principals=[self.scooper_reader_role],
                        actions=["kms:Decrypt"],
                        resources=["*"],
                    )
                )
                encryption_key.grant_decrypt(self.scooper_reader_role)

                events.Rule(
                    self,
                    "ScooperEvents",
                    rule_name="ScooperEvents",
                    event_pattern=events.EventPattern(
                        source=["aws.s3"],
                        detail_type=["Object Created"],
                        detail={"bucket": {"name": [self._scooper_bucket.bucket_name]}},
                    ),
                    targets=[events_targets.SqsQueue(self.scooper_queue)],
                )

        return self._scooper_bucket

    @property
    def scooper_queue(self) -> sqs.Queue:
        if self._scooper_queue is None:
            encryption_master_key = kms.Key(
                self,
                "ScooperQueueKey",
                alias="scooper/queue",
                description="Key used by Scooper for queue encryption",
                enable_key_rotation=True,
            )

            self._scooper_queue = sqs.Queue(
                self,
                "ScooperQueue",
                queue_name="ScooperQueue",
                encryption_master_key=encryption_master_key,
                enforce_ssl=True,
            )

            if self.scooper_config.standalone:
                self._scooper_queue.grant_consume_messages(self.scooper_reader_role)

        return self._scooper_queue

    @property
    def scooper_reader_role(self) -> Role:
        if self._scooper_reader_role is None:
            self._scooper_reader_role = Role(
                self,
                "ScooperReaderRole",
                role_name="ScooperReaderRole",
            )
            # Allow IAM Roles Anywhere to assume the role
            self._scooper_reader_role.assume_role_policy.add_statements(
                iam.PolicyStatement(
                    principals=[iam.ServicePrincipal("rolesanywhere.amazonaws.com")],
                    actions=[
                        "sts:AssumeRole",
                        "sts:SetSourceIdentity",
                        "sts:TagSession",
                    ],
                    conditions={
                        "StringEquals": {
                            "aws:PrincipalTag/x509Subject/CN": SCOOPER,
                        },
                    },
                )
            )
            self._scooper_reader_role.add_to_policy(
                iam.PolicyStatement(
                    actions=["lambda:GetLayerVersion"],
                    resources=[f"{CBS_COMMON_LAMBDA_LAYER_ARN}:*"],
                )
            )

            self.trust_anchor = CfnResource(
                self,
                "TrustAnchor",
                type="AWS::RolesAnywhere::TrustAnchor",
                properties={
                    "Name": "ScooperTrustAnchor",
                    "Source": {
                        "SourceData": {
                            "X509CertificateData": self.scooper_config.certificate_authority.certificate.public_bytes(
                                Encoding.PEM
                            ).decode()
                        },
                        "SourceType": "CERTIFICATE_BUNDLE",
                    },
                    "Enabled": True,
                },
            )

            self.profile = CfnResource(
                self,
                "Profile",
                type="AWS::RolesAnywhere::Profile",
                properties={
                    "Name": "ScooperProfile",
                    "RoleArns": [self._scooper_reader_role.role_arn],
                    "DurationSeconds": 3600,
                    "Enabled": True,
                },
            )

        return self._scooper_reader_role
