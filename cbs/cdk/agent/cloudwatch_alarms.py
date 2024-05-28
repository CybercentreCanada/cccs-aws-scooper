from functools import partial

import aws_cdk as cdk
from aws_cdk import aws_cloudwatch as cloudwatch
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_iam as iam
from aws_cdk import aws_kms as kms
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_lambda_event_sources as lambda_event_sources
from aws_cdk import aws_sns as sns
from aws_cdk import aws_sns_subscriptions as sns_subscriptions
from constructs import Construct

from cbs.cdk.cbs_constructs.cbs_alarm import CBSAlarm
from cbs.cdk.config import CBSConfig
from cbs.cdk.helpers import create_resource_name
from cbs.core import constants
from cbs.core.utils.datetime import is_expired
from cbs.lambdas import PATH as LAMBDAS_PATH


class CloudWatchAlarms(cdk.NestedStack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        config: CBSConfig,
        partners_data: dict[str, dict[str, str]],
        deployed_partners: dict[str, bool],
        partners_1_0: tuple[str],
        alarm_suppression_table: dynamodb.Table,
        powertools_layer: lambda_.ILayerVersion,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Add in 1.0 partners so we can create alarms for them too
        partners_data = partners_data | {
            partner: {constants.CBS_ID: partner} for partner in partners_1_0
        }
        deployed_partners = deployed_partners | {
            partner: True for partner in partners_1_0
        }

        self._create_resource_name = partial(
            create_resource_name, scope=self, environment=config.Environment
        )

        master_key = kms.Key(
            self,
            "CloudWatchAlarmsTopicKey",
            description="Master Key for CloudWatch Alarms Topic",
            enable_key_rotation=True,
            policy=iam.PolicyDocument(
                statements=[
                    iam.PolicyStatement(
                        principals=[iam.AccountPrincipal(self.account)],
                        actions=["kms:*"],
                        resources=["*"],
                    ),
                    iam.PolicyStatement(
                        principals=[iam.ServicePrincipal("cloudwatch.amazonaws.com")],
                        actions=["kms:Decrypt", "kms:GenerateDataKey*"],
                        resources=["*"],
                    ),
                ],
            ),
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )

        alarm_topic_intermediate = sns.Topic(
            self,
            "CloudWatchAlarmsTopicIntermediate",
            topic_name=self._create_resource_name("CloudWatchAlarmsTopicIntermediate"),
            master_key=master_key,
        )

        alarm_topic_final = sns.Topic(
            self,
            "CloudWatchAlarmsTopicFinal",
            topic_name=self._create_resource_name("CloudWatchAlarmsTopicFinal"),
            master_key=master_key,
        )

        if opsgenie_url := config.OpsGenieURL:
            alarm_topic_final.add_subscription(
                sns_subscriptions.UrlSubscription(opsgenie_url)
            )

        for partner_data in partners_data.values():
            if (deployed := partner_data.get(constants.DEPLOYED)) is None:
                deployed = deployed_partners[partner_data[constants.CBS_ID]]
            if (
                disclosure_expiry := partner_data.get(constants.DISCLOSURE_EXPIRY)
            ) is not None:
                expired = is_expired(
                    disclosure_expiry, constants.DISCLOSURE_EXPIRY_FORMAT
                )
            else:
                expired = False
            if deployed and not expired:
                if bucket_name := partner_data.get(constants.BUCKET_NAME):
                    CBSAlarm(
                        self,
                        f"IndigestionAlarm-{partner_data[constants.CBS_ID]}",
                        alarm_name=self._create_resource_name(
                            f"IndigestionAlarm-{partner_data[constants.CBS_ID]}"
                        ),
                        alarm_description=f"Alerts to an absence of GetRequests on {partner_data[constants.CBS_ID]}'s bucket",
                        metric=cloudwatch.Metric(
                            metric_name="GetRequests",
                            namespace="AWS/S3",
                            dimensions_map={
                                "BucketName": bucket_name,
                                "FilterId": "RequestMetrics",
                            },
                            period=cdk.Duration.minutes(5),
                            statistic=cloudwatch.Stats.SUM,
                            unit=cloudwatch.Unit.COUNT,
                        ),
                        threshold=0,
                        comparison_operator=cloudwatch.ComparisonOperator.LESS_THAN_OR_EQUAL_TO_THRESHOLD,
                        evaluation_periods=1,
                        datapoints_to_alarm=1,
                        treat_missing_data=cloudwatch.TreatMissingData.BREACHING,
                        topic=alarm_topic_intermediate,
                    )

                    CBSAlarm(
                        self,
                        f"ReplicationAlarm-{partner_data[constants.CBS_ID]}",
                        alarm_name=self._create_resource_name(
                            f"ReplicationAlarm-{partner_data[constants.CBS_ID]}"
                        ),
                        alarm_description=f"Alerts to a suspected replication failure on {partner_data[constants.CBS_ID]}'s bucket",
                        metric=cloudwatch.MathExpression(
                            expression="IF((RATE(m1) * PERIOD(m1)) == 0, 1, 0)",  # Calculates slope and returns 1 if slope is flat
                            using_metrics={
                                "m1": cloudwatch.Metric(
                                    metric_name="NumberOfObjects",
                                    namespace="AWS/S3",
                                    dimensions_map={
                                        "BucketName": bucket_name,
                                        "StorageType": "AllStorageTypes",
                                    },
                                    period=cdk.Duration.days(1),
                                )
                            },
                            period=cdk.Duration.days(1),
                            label="IsFlatline",
                        ),
                        threshold=1,
                        comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
                        evaluation_periods=1,
                        datapoints_to_alarm=1,
                        treat_missing_data=cloudwatch.TreatMissingData.BREACHING,
                        topic=alarm_topic_intermediate,
                    )

                CBSAlarm(
                    self,
                    f"CloudTrailWorkloadAlarm-{partner_data[constants.CBS_ID]}",
                    alarm_name=self._create_resource_name(
                        f"CloudTrailWorkloadAlarm-{partner_data[constants.CBS_ID]}"
                    ),
                    alarm_description=f"Alerts to missing CloudTrail workloads for {partner_data[constants.CBS_ID]}",
                    metric=cloudwatch.Metric(
                        metric_name="CloudTrailWorkloadCount",
                        namespace="CBS",
                        dimensions_map={"CbsId": partner_data[constants.CBS_ID]},
                        period=cdk.Duration.minutes(5),
                        statistic=cloudwatch.Stats.SUM,
                    ),
                    threshold=0,
                    comparison_operator=cloudwatch.ComparisonOperator.LESS_THAN_OR_EQUAL_TO_THRESHOLD,
                    evaluation_periods=1,
                    datapoints_to_alarm=1,
                    treat_missing_data=cloudwatch.TreatMissingData.BREACHING,
                    topic=alarm_topic_intermediate,
                )

                CBSAlarm(
                    self,
                    f"CoreWorkloadAlarm-{partner_data[constants.CBS_ID]}",
                    alarm_name=self._create_resource_name(
                        f"CoreWorkloadAlarm-{partner_data[constants.CBS_ID]}"
                    ),
                    alarm_description=f"Alerts to missing core workloads (Config or VPC) for {partner_data[constants.CBS_ID]}",
                    metric=cloudwatch.Metric(
                        metric_name="CoreWorkloadCount",
                        namespace="CBS",
                        dimensions_map={"CbsId": partner_data[constants.CBS_ID]},
                        period=cdk.Duration.hours(1),
                        statistic=cloudwatch.Stats.SUM,
                    ),
                    threshold=0,
                    comparison_operator=cloudwatch.ComparisonOperator.LESS_THAN_OR_EQUAL_TO_THRESHOLD,
                    evaluation_periods=1,
                    datapoints_to_alarm=1,
                    treat_missing_data=cloudwatch.TreatMissingData.BREACHING,
                    topic=alarm_topic_intermediate,
                )

                CBSAlarm(
                    self,
                    f"CloudWatchWorkloadAlarm-{partner_data[constants.CBS_ID]}",
                    alarm_name=self._create_resource_name(
                        f"CloudWatchWorkloadAlarm-{partner_data[constants.CBS_ID]}"
                    ),
                    alarm_description=f"Alerts to missing CloudWatch workloads for {partner_data[constants.CBS_ID]}",
                    metric=cloudwatch.Metric(
                        metric_name="CloudWatchWorkloadCount",
                        namespace="CBS",
                        dimensions_map={"CbsId": partner_data[constants.CBS_ID]},
                        period=cdk.Duration.hours(1),
                        statistic=cloudwatch.Stats.SUM,
                    ),
                    threshold=0,
                    comparison_operator=cloudwatch.ComparisonOperator.LESS_THAN_OR_EQUAL_TO_THRESHOLD,
                    evaluation_periods=1,
                    datapoints_to_alarm=1,
                    treat_missing_data=cloudwatch.TreatMissingData.BREACHING,
                    topic=alarm_topic_intermediate,
                )

                CBSAlarm(
                    self,
                    f"MetadataWorkloadAlarm-{partner_data[constants.CBS_ID]}",
                    alarm_name=self._create_resource_name(
                        f"MetadataWorkloadAlarm-{partner_data[constants.CBS_ID]}"
                    ),
                    alarm_description=f"Alerts to missing accelerator metadata workloads for {partner_data[constants.CBS_ID]}",
                    metric=cloudwatch.Metric(
                        metric_name="MetadataWorkloadCount",
                        namespace="CBS",
                        dimensions_map={"CbsId": partner_data[constants.CBS_ID]},
                        period=cdk.Duration.days(1),
                        statistic=cloudwatch.Stats.SUM,
                    ),
                    threshold=0,
                    comparison_operator=cloudwatch.ComparisonOperator.LESS_THAN_OR_EQUAL_TO_THRESHOLD,
                    evaluation_periods=1,
                    datapoints_to_alarm=1,
                    treat_missing_data=cloudwatch.TreatMissingData.BREACHING,
                    topic=alarm_topic_intermediate,
                )

        cw_alarm_formatter: lambda_.Function = lambda_.Function(
            self,
            "CWAlarmFormatterLambda",
            function_name=self._create_resource_name("CWAlarmFormatterLambda"),
            handler="app.lambda_handler",
            runtime=lambda_.Runtime.PYTHON_3_11,
            code=lambda_.Code.from_asset(LAMBDAS_PATH + "/cw_alarm_formatter/"),
            memory_size=256,
            timeout=cdk.Duration.seconds(3),
            environment={
                "ALARM_SUPPRESSION_TABLE_NAME": alarm_suppression_table.table_name,
                "CLOUDWATCH_ALARMS_TOPIC": alarm_topic_final.topic_arn,
            },
            layers=[powertools_layer],
        )
        cw_alarm_formatter.add_event_source(
            lambda_event_sources.SnsEventSource(alarm_topic_intermediate)
        )
        alarm_suppression_table.grant_read_data(cw_alarm_formatter)

        alarm_topic_final.grant_publish(cw_alarm_formatter.role)
        alarm_topic_final.add_to_resource_policy(
            iam.PolicyStatement(
                principals=[cw_alarm_formatter.role],
                actions=["sns:Publish"],
                resources=[alarm_topic_final.topic_arn],
            )
        )

        master_key.grant_decrypt(cw_alarm_formatter.role)
        master_key.add_to_resource_policy(
            iam.PolicyStatement(
                principals=[cw_alarm_formatter.role],
                actions=["kms:Decrypt", "kms:GenerateDataKey*"],
                resources=["*"],
            )
        )
