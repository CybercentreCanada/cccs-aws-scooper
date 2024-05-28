from functools import partial

import aws_cdk as cdk
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_iam as iam
from aws_cdk import aws_kms as kms
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_lambda_event_sources as lambda_event_sources
from aws_cdk import aws_sns as sns
from aws_cdk import aws_sns_subscriptions as sns_subscriptions
from aws_cdk import aws_sqs as sqs
from constructs import Construct

from cbs.cdk.config import CBSConfig
from cbs.cdk.helpers import create_resource_name
from cbs.lambdas import PATH as LAMBDAS_PATH


class DlqTriageLambda(cdk.NestedStack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        config: CBSConfig,
        layers: list[lambda_.ILayerVersion],
        cbs_dlq: sqs.Queue,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        _create_resource_name = partial(
            create_resource_name,
            scope=self,
            environment=config.Environment,
        )

        if config.Environment == "dev":
            unknown_workloads_table = dynamodb.Table(
                self,
                "UnknownWorkloadsTable",
                table_name=_create_resource_name("UnknownWorkloadsTable"),
                partition_key=dynamodb.Attribute(
                    name="object_key", type=dynamodb.AttributeType.STRING
                ),
                billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
                removal_policy=cdk.RemovalPolicy.DESTROY,
                deletion_protection=True,
                point_in_time_recovery=True,
            )
        else:
            unknown_workloads_table: dynamodb.ITable = dynamodb.Table.from_table_name(
                self,
                "UnknownWorkloadsTable",
                _create_resource_name("UnknownWorkloadsTable"),
            )

        master_key: kms.Key = kms.Key(
            self,
            "UnknownWorkloadsTopicKey",
            description="Master Key for Unknown Workloads SNS Topic",
            enable_key_rotation=True,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )
        unknown_workloads_topic: sns.Topic = sns.Topic(
            self,
            "UnknownWorkloadsTopic",
            topic_name=_create_resource_name("UnknownWorkloadsTopic"),
            master_key=master_key,
        )
        if unknown_workloads_emails := config.UnknownWorkloadsEmails:
            for email in unknown_workloads_emails:
                unknown_workloads_topic.add_subscription(
                    sns_subscriptions.EmailSubscription(email)
                )

        self.dlq_triager: lambda_.Function = lambda_.Function(
            self,
            "DLQTriagerLambda",
            function_name=_create_resource_name("DLQTriagerLambda"),
            handler="app.lambda_handler",
            runtime=lambda_.Runtime.PYTHON_3_11,
            code=lambda_.Code.from_asset(LAMBDAS_PATH + "/dlq_triage/"),
            memory_size=256,
            timeout=cdk.Duration.seconds(3),
            environment={
                "UNKNOWN_WORKLOADS_TABLE_NAME": unknown_workloads_table.table_name,
                "UNKNOWN_WORKLOADS_TOPIC_ARN": unknown_workloads_topic.topic_arn,
            },
            layers=layers,
        )
        self.dlq_triager.add_event_source(lambda_event_sources.SqsEventSource(cbs_dlq))

        unknown_workloads_table.grant_read_write_data(self.dlq_triager)
        master_key.add_to_resource_policy(
            iam.PolicyStatement(
                principals=[self.dlq_triager.role],
                actions=["kms:Decrypt", "kms:GenerateDataKey*"],
                resources=["*"],
            ),
        )
        unknown_workloads_topic.grant_publish(self.dlq_triager)
