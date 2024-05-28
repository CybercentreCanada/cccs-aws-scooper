from functools import partial
from json import dumps, loads

import aws_cdk as cdk
from aws_cdk import aws_cloudwatch as cloudwatch
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as eventbridge_targets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_kms as kms
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_lambda_event_sources as lambda_event_sources
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_scheduler as scheduler
from aws_cdk import aws_sqs as sqs
from aws_cdk import aws_stepfunctions as sfn
from aws_cdk import aws_stepfunctions_tasks as sfn_tasks
from aws_cdk import custom_resources as cr
from boto3 import client
from boto3.dynamodb.types import TypeSerializer
from constructs import Construct

from cbs.cdk import helpers
from cbs.cdk.agent.cloudwatch_alarms import CloudWatchAlarms
from cbs.cdk.agent.disclosure import CBSDisclosure
from cbs.cdk.agent.dlq_triage_lambda import DlqTriageLambda
from cbs.cdk.config import CBSConfig
from cbs.core import constants
from cbs.core.types import Partner
from cbs.core.utils.datetime import is_expired
from cbs.core.utils.sts import assume_role
from cbs.lambdas import PATH as LAMBDAS_PATH
from docs import VERSION


class AgentStack(cdk.Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        config: CBSConfig,
        partners: dict[str, Partner],
        inventory_table: dynamodb.Table = None,
        partner_config_bucket: s3.Bucket = None,
        terraform_backend_bucket: s3.Bucket = None,
        devops_role: iam.Role = None,
        **kwargs,
    ) -> None:
        """Deploys resources to facilitate S3 bucket replication

        Args:
            scope (Construct): CDK app
            construct_id (str): Stack name
            config (CBSConfig): Environment specific configuration parameters
            partners (dict[str, Partner]): Partners to create resources for
            inventory_table (dynamodb.Table, optional): Partner inventory table. Defaults to None
            partner_config_bucket (s3.Bucket, optional): Partner config bucket. Defaults to None
            devops_role (iam.Role, optional): CI/CD DevOps role for updating inventory table. Defaults to None
        """
        super().__init__(scope, construct_id, **kwargs)

        self._s3_client = client("s3")
        self._config = config
        self._partners = partners
        self._deployed_partners = self.get_deployed_partners()
        _1_0_partners = self.get_1_0_partners()

        self._create_resource_name = partial(
            helpers.create_resource_name, scope=self, environment=config.Environment
        )

        if devops_role:
            self.devops_role_arn = devops_role.role_arn
        else:
            # Create DevOps Role if none is provided, i.e. deploying only agent
            devops_role: iam.Role = iam.Role(
                self,
                "DevOpsRole",
                role_name=self._create_resource_name("DevOpsRole"),
                assumed_by=iam.AccountPrincipal(self.account),
            )
            self.devops_role_arn = devops_role.role_arn

        # Create Powertools, Common Functions, and Constants Lambda Layers
        self.create_lambda_layers()
        # Create Metric Filters on Transport and SQS Router Lambdas
        self.create_metric_filters()

        # Create Reader and Grafana Users
        (
            cbs_reader_user,
            self.cbs_reader_role,
            self.cbs_grafana_role,
        ) = self.create_users_and_roles()
        # Create SQS and DLQ
        cbs_sqs, cbs_dlq = self.create_sqs_and_dlq()
        # Grant permission to Reader Role to consume messages from SQS
        cbs_sqs.grant_consume_messages(cbs_reader_user)
        # Create CBS Disclosure Lambda and Scheduler Role
        self.cbs_disclosure = CBSDisclosure(
            self,
            "CBSDisclosure",
            self._config,
            self.devops_role_arn,
            [self.powertools_layer, self.core_layer, self.common_functions_layer],
        )
        # Create CCCS Reader Role to read from partner accounts
        cccs_reader_role = iam.Role(
            self,
            "CCCSReaderRole",
            role_name=self._create_resource_name("CCCSReaderRole"),
            assumed_by=iam.AccountPrincipal(self.account),
        )
        # Allow CCCS Reader Role to assume cbs-global-reader in partner accounts
        cccs_reader_role.add_to_policy(
            iam.PolicyStatement(
                actions=["sts:AssumeRole"],
                resources=[
                    constants.CBS_GLOBAL_READER_ROLE_TEMPLATE.substitute(account="*")
                ],
            )
        )
        # Deny CCCS Reader Role assume role on expired disclosure partners
        for partner in self._partners.values():
            if (
                disclosure_expiry := partner.get(constants.DISCLOSURE_EXPIRY)
            ) is not None and (
                mgmt_account_id := partner.get(constants.MGMT_ACCOUNT_ID)
            ) is not None:
                if is_expired(disclosure_expiry, constants.DISCLOSURE_EXPIRY_FORMAT):
                    cccs_reader_role.add_to_policy(
                        iam.PolicyStatement(
                            effect=iam.Effect.DENY,
                            actions=["sts:AssumeRole"],
                            resources=[
                                constants.CBS_GLOBAL_READER_ROLE_TEMPLATE.substitute(
                                    account=mgmt_account_id
                                )
                            ],
                        )
                    )
        # Create SSO Metadata Lambda
        self.sso_lambda = self.create_sso_lambda(cccs_reader_role)
        # Create IAM Metadata Lambda
        self.iam_lambda = self.create_iam_lambda(cccs_reader_role)
        # Create S3 destination buckets for partners
        self.create_partner_buckets()
        # Create SQS Router Lambda if a 1.0 SQS exists
        if old_sqs_arn := config.SQSArn:
            old_sqs = sqs.Queue.from_queue_arn(self, "OldSQS", old_sqs_arn)
            self.create_sqs_router_lambda(old_sqs, cbs_sqs)

        # Create State Machine to orchestrate Metadata Lambdas per partner
        self.create_state_machine()
        # Create Alarm Suppression DynamoDB Table
        self.alarm_suppression_table = helpers.create_alarm_suppression_table(
            self, self._create_resource_name("AlarmSuppressionTable")
        )
        # Create Transport Lambda
        transport_lambda = self.create_transport_lambda(cbs_sqs, cbs_dlq)
        # Create DLQ Triage Lambda to handle unknown workloads from Transport Lambda
        self.create_dlq_triage_lambda(cbs_dlq)
        # Create EventBridge Rules to route events to Transport Lambda
        self.create_eventbridge_rule(transport_lambda, cbs_dlq)

        # Create CloudWatch Alarms for all partners
        CloudWatchAlarms(
            self,
            "CloudWatchAlarmsStack",
            self._config,
            self._partners,
            self._deployed_partners,
            _1_0_partners,
            self.alarm_suppression_table,
            self.powertools_layer,
        )

        # Create partner inventory table and partner config bucket if necessary
        if self._config.OnlyAgent or (
            inventory_table is None and partner_config_bucket is None
        ):
            self.inventory_table = helpers.create_inventory_table(
                scope=self,
                table_name=self._create_resource_name(constants.INVENTORY_TABLE_NAME),
                database_management_account=self.account,
                agent_account=self.account,
                initialise_data=self._partners,
            )
            self.inventory_table.grant_read_write_data(devops_role)
            self.partner_config_bucket = s3.Bucket(
                self,
                "PartnerConfigBucket",
                versioned=True,
                removal_policy=cdk.RemovalPolicy.DESTROY,
                enforce_ssl=True,
            )
            self.terraform_backend_bucket = s3.Bucket(
                self,
                "TerraformBackendBucket",
                versioned=True,
                removal_policy=cdk.RemovalPolicy.DESTROY,
                enforce_ssl=True,
            )
        else:
            self.inventory_table = inventory_table
            self.partner_config_bucket = partner_config_bucket
            self.terraform_backend_bucket = terraform_backend_bucket

        # Grant DevOps Role batch write permissions to partner inventory table
        devops_role.add_to_policy(
            iam.PolicyStatement(
                actions=["dynamodb:BatchWriteItem"],
                resources=[self.inventory_table.table_arn],
            )
        )
        # Write partner information to inventory table and config bucket
        self.create_s3_output_custom_resource()

    def create_users_and_roles(self) -> tuple[iam.Role]:
        """Creates needed groups, users, and roles for Reader and Grafana"""
        if self._config.UseRole:
            cbs_reader_user = helpers.create_or_import_role(
                self, self._config, self._config.ReaderUser, "ReaderUserRole"
            )
            cbs_grafana_user = helpers.create_or_import_role(
                self, self._config, self._config.GrafanaUser, "GrafanaUserRole"
            )
        else:
            # Add users to groups and attach permissions to groups as per best practices
            cbs_reader_user = helpers.create_or_import_user(
                self, self._config, self._config.ReaderUser, "ReaderUser"
            )
            reader_group = helpers.create_or_import_group(
                self, self._config, self._config.ReaderUserGroup, "ReaderUserGroup"
            )

            grafana_group = helpers.create_or_import_group(
                self, self._config, self._config.GrafanaUserGroup, "GrafanaUserGroup"
            )
            cbs_grafana_user = helpers.create_or_import_user(
                self, self._config, self._config.GrafanaUser, "GrafanaUser"
            )

        cbs_reader_role: iam.Role = iam.Role(
            self,
            "ReaderRole",
            role_name=self._create_resource_name("ReaderRole"),
            assumed_by=cbs_reader_user,
        )

        cbs_grafana_role: iam.Role = iam.Role(
            self,
            "GrafanaMonitoringRole",
            role_name=self._create_resource_name("GrafanaMonitoringRole"),
            assumed_by=iam.CompositePrincipal(
                cbs_grafana_user, iam.AccountPrincipal(self.account)
            ),
        )

        if self._config.UseRole:
            cbs_reader_role.grant_assume_role(cbs_reader_user)
            cbs_grafana_role.grant_assume_role(cbs_grafana_user)
        else:
            reader_group.attach_inline_policy(
                iam.Policy(
                    self,
                    "ReaderAssumePolicy",
                    statements=[
                        iam.PolicyStatement(
                            actions=["sts:AssumeRole"],
                            resources=[cbs_reader_role.role_arn],
                        )
                    ],
                )
            )
            grafana_group.attach_inline_policy(
                iam.Policy(
                    self,
                    "GrafanaAssumePolicy",
                    statements=[
                        iam.PolicyStatement(
                            actions=["sts:AssumeRole"],
                            resources=[cbs_grafana_role.role_arn],
                        )
                    ],
                )
            )

        cbs_grafana_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "cloudwatch:DescribeAlarms",
                    "cloudwatch:ListMetrics",
                    "cloudwatch:GetMetricStatistics",
                    "cloudwatch:GetMetricData",
                    "logs:DescribeLogGroups",
                    "logs:GetQueryResults",
                ],
                resources=["*"],  # Least permissions needed with grafana
            )
        )

        return cbs_reader_user, cbs_reader_role, cbs_grafana_role

    def create_partner_buckets(self) -> None:
        """Creates a bucket for each partner"""
        for account_id, info in self._partners.items():
            self._partners[account_id].update(
                self._create_partner_bucket(
                    account_id,
                    info[constants.CBS_ID],
                    info.get(constants.DISCLOSURE_EXPIRY),
                )
            )

    def _create_partner_bucket(
        self, account_id: str, cbs_id: str, disclosure_expiry: str | None
    ) -> dict:
        """Configures S3 bucket replication for each given partner"""
        partner_bucket: s3.Bucket = s3.Bucket(
            self,
            cbs_id,
            event_bridge_enabled=True,
            versioned=True,
            removal_policy=(
                cdk.RemovalPolicy.RETAIN
                if self._config.Environment == "prod"
                else cdk.RemovalPolicy.DESTROY
            ),
            object_ownership=s3.ObjectOwnership.BUCKET_OWNER_ENFORCED,
            bucket_key_enabled=True,
            auto_delete_objects=self._config.Environment != "prod",
            encryption=s3.BucketEncryption.KMS,
            encryption_key=kms.Key(
                self,
                f"{cbs_id}Key",
                description=f"Bucket Key for {cbs_id}",
                enable_key_rotation=True,
            ),
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            metrics=[s3.BucketMetrics(id="RequestMetrics")],
        )

        if disclosure_expiry is None or not is_expired(
            disclosure_expiry, constants.DISCLOSURE_EXPIRY_FORMAT
        ):
            # Configure replication for destination bucket
            partner_bucket.add_to_resource_policy(
                self._create_account_policy_statement(
                    account_id=account_id,
                    actions=[
                        "s3:GetBucketVersioning",
                        "s3:PutBucketVersioning",
                        "s3:ReplicateObject",
                        "s3:ReplicateDelete",
                        "s3:ObjectOwnerOverrideToBucketOwner",
                    ],
                    resources=[
                        partner_bucket.bucket_arn,
                        partner_bucket.arn_for_objects("*"),
                    ],
                )
            )

        # Allow partner account to encrypt replicated objects in destination bucket
        partner_bucket.encryption_key.add_to_resource_policy(
            self._create_account_policy_statement(
                account_id=account_id,
                actions=["kms:Encrypt"],
                resources=["*"],
            )
        )
        # Allow reader role and lambda service role read permissions on partner bucket
        partner_bucket.grant_read(self.cbs_reader_role)
        # Allow metadata lambdas to write to the bucket
        partner_bucket.grant_write(
            self.sso_lambda,
            objects_key_pattern=f"{cbs_id}/{constants.CBS_METADATA_OBJECT_KEY}/*",
        )
        partner_bucket.grant_write(
            self.iam_lambda,
            objects_key_pattern=f"{cbs_id}/{constants.CBS_METADATA_OBJECT_KEY}/*",
        )
        # Deny all other principals GET access on partner bucket
        partner_bucket.add_to_resource_policy(
            iam.PolicyStatement(
                effect=iam.Effect.DENY,
                principals=[iam.AnyPrincipal()],
                actions=["s3:GetObject"],
                resources=[
                    partner_bucket.bucket_arn,
                    partner_bucket.arn_for_objects("*"),
                ],
                conditions={
                    "StringNotEquals": {
                        "aws:PrincipalArn": [self.cbs_reader_role.role_arn]
                    }
                },
            )
        )
        # Allow SQS Router to list objects (for checking if bucket is empty)
        if self._config.SQSArn:
            partner_bucket.add_to_resource_policy(
                iam.PolicyStatement(
                    principals=[iam.ServicePrincipal("lambda.amazonaws.com")],
                    actions=["s3:ListBucket"],
                    resources=[
                        partner_bucket.bucket_arn,
                        partner_bucket.arn_for_objects("*"),
                    ],
                    conditions={"StringEquals": {"aws:SourceAccount": self.account}},
                )
            )

        match self._config.Environment:
            # Configure object lifecycle rule based on environment
            case "prod":
                partner_bucket.add_lifecycle_rule(
                    enabled=True,
                    expiration=cdk.Duration.days(355),
                    noncurrent_version_expiration=cdk.Duration.days(1),
                    noncurrent_versions_to_retain=1,
                    transitions=[
                        s3.Transition(
                            storage_class=s3.StorageClass.GLACIER_INSTANT_RETRIEVAL,
                            transition_after=cdk.Duration.days(14),
                        )
                    ],
                )
            case "stage":
                partner_bucket.add_lifecycle_rule(
                    enabled=True, expiration=cdk.Duration.days(30)
                )  # Glacier IR has 90 day minimum storage charge, not useful for stage
            case "dev":
                partner_bucket.add_lifecycle_rule(
                    enabled=True, expiration=cdk.Duration.days(7)
                )

        if disclosure_expiry is not None:
            # Grant CBS Disclosure Lambda bucket policy edit permissions
            partner_bucket.add_to_resource_policy(
                iam.PolicyStatement(
                    actions=["s3:GetBucketPolicy", "s3:PutBucketPolicy"],
                    principals=[self.cbs_disclosure.cbs_disclosure_lambda.role],
                    resources=[partner_bucket.bucket_arn],
                )
            )
            self.cbs_disclosure.cbs_disclosure_lambda.add_to_role_policy(
                iam.PolicyStatement(
                    actions=["s3:GetBucketPolicy", "s3:PutBucketPolicy"],
                    resources=[partner_bucket.bucket_arn],
                )
            )
            # Create one-time schedule for CBS Disclosure
            scheduler.CfnSchedule(
                self,
                f"{cbs_id}-DisclosureSchedule",
                name=self._create_resource_name(f"{cbs_id}-DisclosureSchedule"),
                description=f"Ends CBS collection of {cbs_id}'s data at specified disclosure expiry",
                schedule_expression=f"at({disclosure_expiry})",
                flexible_time_window=scheduler.CfnSchedule.FlexibleTimeWindowProperty(
                    mode="OFF"
                ),
                target=scheduler.CfnSchedule.TargetProperty(
                    arn=self.cbs_disclosure.cbs_disclosure_lambda.function_arn,
                    role_arn=self.cbs_disclosure.scheduler_role.role_arn,
                    input=dumps({"bucket_name": partner_bucket.bucket_name}),
                ),
            )

        return {
            constants.BUCKET_NAME: partner_bucket.bucket_name,
            constants.KMS_ARN: partner_bucket.encryption_key.key_arn,
            constants.DEPLOYED: self._deployed_partners.get(cbs_id, False),
        }

    def _create_account_policy_statement(
        self, account_id: str, actions: list[str], resources: list[str]
    ) -> iam.PolicyStatement:
        """Returns a policy statement for an AWS account principal"""
        statement = iam.PolicyStatement(actions=actions, resources=resources)
        statement.add_aws_account_principal(account_id)

        return statement

    def create_eventbridge_rule(
        self, transport_lambda: lambda_.Function, cbs_dlq: sqs.Queue
    ) -> None:
        """Creates EventBridge Rules to route events to Transport Lambda"""
        s3_rule = events.Rule(
            self,
            "S3ReplicationEventsToTransportLambda",
            rule_name=self._create_resource_name(
                "S3ReplicationEventsToTransportLambda"
            ),
            description="Directs all S3 replication events to our Transport Lambda for processing",
            event_pattern=events.EventPattern(
                detail_type=["AWS API Call via CloudTrail"],
                source=["aws.s3"],
                detail={
                    "userIdentity": {
                        "principalId": [{"suffix": ":s3-replication"}],
                        "accountId": [
                            partner
                            for partner in self._partners
                            if not is_expired(
                                self._partners[partner].get(
                                    constants.DISCLOSURE_EXPIRY
                                ),
                                constants.DISCLOSURE_EXPIRY_FORMAT,
                            )
                        ]
                        or [self.account],
                    },
                    "eventName": ["PutObject"],
                    "additionalEventData": {
                        "bytesTransferredIn": [{"numeric": [">", 0]}]
                    },
                },
            ),
            targets=[
                eventbridge_targets.LambdaFunction(
                    handler=transport_lambda,
                    dead_letter_queue=cbs_dlq,
                    retry_attempts=2,
                )
            ],
        )
        s3_rule.apply_removal_policy(cdk.RemovalPolicy.DESTROY)

        cbs_metadata_rule = events.Rule(
            self,
            "CBSMetadataToTransportLambda",
            rule_name=self._create_resource_name("MetadataToTransportLambda"),
            description="Directs all CBS Metadata events to our Transport Lambda for processing",
            event_pattern=events.EventPattern(
                detail_type=["Object Created"],
                source=["aws.s3"],
                detail={
                    "object": {
                        "key": [
                            {"wildcard": f"*/{constants.CBS_METADATA_OBJECT_KEY}/*"}
                        ]
                    },
                },
            ),
            targets=[
                eventbridge_targets.LambdaFunction(
                    handler=transport_lambda,
                    dead_letter_queue=cbs_dlq,
                    retry_attempts=2,
                )
            ],
        )
        cbs_metadata_rule.apply_removal_policy(cdk.RemovalPolicy.DESTROY)

    def get_deployed_partners(self) -> dict[str, bool]:
        """Gets 2.0 partner deployment statuses based on whether their bucket is empty or not"""
        try:
            # Assume CDK lookup role in agent account if given
            if self._config.AgentAccount:
                session = assume_role(
                    role_arn=f"arn:aws:iam::{self._config.AgentAccount}:role/cdk-hnb659fds-lookup-role-{self._config.AgentAccount}-{self.region}",
                    region=self.region,
                    role_session_name="ListBuckets",
                )
                s3_client = session.client("s3")
            else:
                s3_client = self._s3_client

            buckets = s3_client.list_buckets()["Buckets"]
            cbs_ids = tuple(
                partner_data[constants.CBS_ID]
                for partner_data in self._partners.values()
            )
            cbs_id_to_bucket_name_map = {}

            for bucket in buckets:
                bucket_name = bucket["Name"]
                try:
                    tag_set = s3_client.get_bucket_tagging(Bucket=bucket_name)["TagSet"]
                    for tag in tag_set:
                        if tag["Key"] == "aws:cloudformation:logical-id":
                            for cbs_id in cbs_ids:
                                if tag["Value"].startswith(cbs_id.replace("-", "")):
                                    cbs_id_to_bucket_name_map[cbs_id] = bucket_name
                except Exception:
                    continue

            deployed_partners = {}

            for cbs_id, bucket_name in cbs_id_to_bucket_name_map.items():
                deployed_partners[cbs_id] = (
                    s3_client.list_objects_v2(Bucket=bucket_name, MaxKeys=1)["KeyCount"]
                    > 0
                )

            return deployed_partners
        except Exception as e:
            if self._config.Environment in {"dev", "test"}:
                return {
                    partner_data[constants.CBS_ID]: True
                    for partner_data in self._partners.values()
                }
            else:
                raise e

    def get_1_0_partners(self) -> tuple[str]:
        """Get 1.0 partner CBS IDs based on 1.0 partner inventory file"""
        try:
            partners = loads(
                self._s3_client.get_object(
                    Bucket=self._config.PartnerInventoryBucket,
                    Key="partner-accounts.json",
                )["Body"].read()
            )
            return tuple(partner["accountId"] for partner in partners)
        except Exception as e:
            if self._config.Environment in {"dev", "test"}:
                return tuple()
            else:
                raise e

    def create_sqs_and_dlq(self) -> tuple[sqs.Queue]:
        """Creates an SQS & DLQ for the Transport Lambda"""
        sqs_key = kms.Key(
            self,
            "SQSKey",
            description="CBS SQS Encryption Key",
            enable_key_rotation=True,
        )

        cbs_dlq: sqs.Queue = sqs.Queue(
            self,
            "DLQ",
            queue_name=self._create_resource_name("DLQ"),
            encryption=sqs.QueueEncryption.KMS,
            encryption_master_key=sqs_key,
            data_key_reuse=cdk.Duration.hours(12),
            enforce_ssl=True,
        )

        cbs_sqs: sqs.Queue = sqs.Queue(
            self,
            "SQS",
            queue_name=self._create_resource_name("SQS"),
            encryption=sqs.QueueEncryption.KMS,
            encryption_master_key=sqs_key,
            data_key_reuse=cdk.Duration.hours(12),
            enforce_ssl=True,
            dead_letter_queue=sqs.DeadLetterQueue(max_receive_count=1, queue=cbs_dlq),
        )

        return cbs_sqs, cbs_dlq

    def create_lambda_layers(self) -> None:
        """Creates Lambda Layers"""
        self.powertools_layer = lambda_.LayerVersion.from_layer_version_arn(
            self,
            "PowertoolsLayer",
            layer_version_arn=f"arn:aws:lambda:{self.region}:017000801446:layer:AWSLambdaPowertoolsPythonV2:69",
        )
        self.core_layer = lambda_.LayerVersion(
            self,
            "CoreLayer",
            layer_version_name=self._create_resource_name("CoreLayer"),
            code=lambda_.Code.from_asset(
                path="../" if not helpers.is_pytest() else "cbs/",
                bundling=cdk.BundlingOptions(
                    image=lambda_.Runtime.PYTHON_3_11.bundling_image,
                    command=[
                        "bash",
                        "-c",
                        "mkdir -p /asset-output/python && cp -au core/ /asset-output/python",
                    ],
                ),
            ),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_11],
        )
        self.common_functions_layer = lambda_.LayerVersion(
            self,
            "CommonFunctionsLayer",
            layer_version_name=self._create_resource_name("CommonFunctionsLayer"),
            code=lambda_.Code.from_asset(
                path="../" if not helpers.is_pytest() else "cbs/",
                bundling=cdk.BundlingOptions(
                    image=lambda_.Runtime.PYTHON_3_11.bundling_image,
                    command=[
                        "bash",
                        "-c",
                        "mkdir -p /asset-output/python/common_functions && cp -au lambdas/common_functions.py /asset-output/python/common_functions/__init__.py",
                    ],
                ),
            ),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_11],
        )

    def create_sqs_router_lambda(self, old_sqs: sqs.IQueue, new_sqs: sqs.Queue):
        """SQS message router for partners not yet on 2.0 of the agent."""
        sqs_router: lambda_.Function = lambda_.Function(
            self,
            "SQSRouterLambda",
            function_name=self._create_resource_name("SQSRouterLambda"),
            handler="app.lambda_handler",
            runtime=lambda_.Runtime.PYTHON_3_11,
            code=lambda_.Code.from_asset(LAMBDAS_PATH + "/sqs_router/"),
            memory_size=256,
            timeout=cdk.Duration.seconds(3),
            environment={
                "CBS_DEVOPS_ROLE_ARN": self.devops_role_arn,
                "CBS_SQS_URL": new_sqs.queue_url,
                "INVENTORY_TABLE_NAME": self._create_resource_name(
                    constants.INVENTORY_TABLE_NAME
                ),
                "VERSION": VERSION,
            },
            layers=[
                self.powertools_layer,
                self.core_layer,
                self.common_functions_layer,
            ],
        )
        # Allow SQS Router to list objects of partner buckets to check whether they're empty
        sqs_router.add_to_role_policy(
            iam.PolicyStatement(
                actions=["s3:ListBucket"],
                resources=["arn:aws:s3:::*"],
            )
        )
        # Allow Grafana Role read permissions on SQS Router Lambda CWLs
        self.cbs_grafana_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "logs:GetLogGroupFields",
                    "logs:StartQuery",
                    "logs:StopQuery",
                    "logs:GetLogEvents",
                ],
                resources=[
                    f"arn:aws:logs:*:{self.account}:log-group:/aws/lambda/{sqs_router.function_name}:log-stream:*",
                    f"arn:aws:logs:*:{self.account}:log-group:/aws/lambda/{sqs_router.function_name}",
                ],
            )
        )
        # Allow lambda to assume devops role for reading partner table
        sqs_router.add_to_role_policy(
            iam.PolicyStatement(
                actions=["sts:AssumeRole"],
                resources=[self.devops_role_arn],
            )
        )
        # Add 1.0 SQS as Lambda's event source
        sqs_router.add_event_source(lambda_event_sources.SqsEventSource(old_sqs))
        # Grant Lambda consume permissions on 1.0 SQS
        sqs_router.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "sqs:DeleteMessage",
                    "sqs:GetQueueAttributes",
                    "sqs:ReceiveMessage",
                ],
                resources=[old_sqs.queue_arn],
            )
        )
        # Grant Lambda send permissions to 2.0 SQS
        new_sqs.grant_send_messages(sqs_router)

    def create_transport_lambda(
        self, cbs_sqs: sqs.Queue, cbs_dlq: sqs.Queue
    ) -> lambda_.Function:
        """Creates the Transport Lambda to process S3 replication events"""
        function_name = "TransportLambda"
        transport_lambda: lambda_.Function = lambda_.Function(
            self,
            function_name,
            function_name=self._create_resource_name(function_name),
            handler="app.lambda_handler",
            runtime=lambda_.Runtime.PYTHON_3_11,
            code=lambda_.Code.from_asset(
                LAMBDAS_PATH + "/transport/",
                # Install PyYAML
                bundling=cdk.BundlingOptions(
                    image=lambda_.Runtime.PYTHON_3_11.bundling_image,
                    command=[
                        "bash",
                        "-c",
                        "pip install -r requirements.txt -t /asset-output && cp -au . /asset-output",
                    ],
                ),
            ),
            memory_size=256,
            timeout=cdk.Duration.seconds(4),
            environment={
                "CBS_ALARM_SUPPRESSION_TABLE_NAME": self.alarm_suppression_table.table_name,
                "CBS_DEVOPS_ROLE_ARN": self.devops_role_arn,
                "CBS_DLQ_URL": cbs_dlq.queue_url,
                "CBS_READER_ROLE_ARN": self.cbs_reader_role.role_arn,
                "CBS_SQS_URL": cbs_sqs.queue_url,
                "CICD_PIPELINE_NAME": self._create_resource_name("CICD"),
                "INVENTORY_TABLE_NAME": self._create_resource_name(
                    constants.INVENTORY_TABLE_NAME
                ),
                "VERSION": VERSION,
            },
            dead_letter_queue=cbs_dlq,
            layers=[
                self.powertools_layer,
                self.core_layer,
                self.common_functions_layer,
            ],
        )

        # Allow Grafana role to read lambda's CWLs
        self.cbs_grafana_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "logs:GetLogGroupFields",
                    "logs:StartQuery",
                    "logs:StopQuery",
                    "logs:GetLogEvents",
                ],
                resources=[
                    f"arn:aws:logs:*:{self.account}:log-group:/aws/lambda/{transport_lambda.function_name}:log-stream:*",
                    f"arn:aws:logs:*:{self.account}:log-group:/aws/lambda/{transport_lambda.function_name}",
                ],
            )
        )
        # Allow lambda to assume reader role for reading metadata files
        self.cbs_reader_role.grant_assume_role(transport_lambda.role)
        self.cbs_reader_role.assume_role_policy.add_statements(
            iam.PolicyStatement(
                actions=["sts:AssumeRole"],
                principals=[transport_lambda.role],
            )
        )
        # Allow lambda to assume devops role to update inventory table
        transport_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["sts:AssumeRole"],
                resources=[self.devops_role_arn],
            )
        )
        # Allow lambda to send messages to SQS
        cbs_sqs.grant_send_messages(transport_lambda)
        # Allow lambda to r/w the alarm suppression table
        self.alarm_suppression_table.grant_read_write_data(transport_lambda)

        return transport_lambda

    def create_sso_lambda(self, cccs_reader_role: iam.Role) -> lambda_.Function:
        function_name = "SSOMetadataLambda"
        sso_lambda: lambda_.Function = lambda_.Function(
            self,
            function_name,
            function_name=self._create_resource_name(function_name),
            handler="app.lambda_handler",
            runtime=lambda_.Runtime.PYTHON_3_11,
            code=lambda_.Code.from_asset(LAMBDAS_PATH + "/sso_metadata/"),
            memory_size=256,
            timeout=cdk.Duration.seconds(30),
            environment={"CCCS_READER_ROLE_ARN": cccs_reader_role.role_arn},
            layers=[
                self.powertools_layer,
                self.core_layer,
                self.common_functions_layer,
            ],
        )
        # Allow lambda to assume the CCCS reader role to read partner accounts
        cccs_reader_role.grant_assume_role(sso_lambda.role)
        sso_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["sts:AssumeRole"], resources=[cccs_reader_role.role_arn]
            )
        )
        # Allow Grafana role to read lambda's CWLs
        self.cbs_grafana_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "logs:GetLogGroupFields",
                    "logs:StartQuery",
                    "logs:StopQuery",
                    "logs:GetLogEvents",
                ],
                resources=[
                    f"arn:aws:logs:*:{self.account}:log-group:/aws/lambda/{sso_lambda.function_name}:log-stream:*",
                    f"arn:aws:logs:*:{self.account}:log-group:/aws/lambda/{sso_lambda.function_name}",
                ],
            )
        )
        return sso_lambda

    def create_iam_lambda(self, cccs_reader_role: iam.Role) -> lambda_.Function:
        function_name = "IAMMetadataLambda"
        iam_lambda: lambda_.Function = lambda_.Function(
            self,
            function_name,
            function_name=self._create_resource_name(function_name),
            handler="app.lambda_handler",
            runtime=lambda_.Runtime.PYTHON_3_11,
            code=lambda_.Code.from_asset(LAMBDAS_PATH + "/iam_metadata/"),
            memory_size=256,
            timeout=cdk.Duration.seconds(30),
            environment={"CCCS_READER_ROLE_ARN": cccs_reader_role.role_arn},
            layers=[
                self.powertools_layer,
                self.core_layer,
                self.common_functions_layer,
            ],
        )
        # Allow lambda to assume the CCCS reader role to read partner accounts
        cccs_reader_role.grant_assume_role(iam_lambda.role)
        iam_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["sts:AssumeRole"], resources=[cccs_reader_role.role_arn]
            )
        )
        # Allow Grafana role to read lambda's CWLs
        self.cbs_grafana_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "logs:GetLogGroupFields",
                    "logs:StartQuery",
                    "logs:StopQuery",
                    "logs:GetLogEvents",
                ],
                resources=[
                    f"arn:aws:logs:*:{self.account}:log-group:/aws/lambda/{iam_lambda.function_name}:log-stream:*",
                    f"arn:aws:logs:*:{self.account}:log-group:/aws/lambda/{iam_lambda.function_name}",
                ],
            )
        )
        return iam_lambda

    def create_state_machine(self) -> None:
        partners_info = tuple(
            {
                constants.MGMT_ACCOUNT_ID: info[constants.MGMT_ACCOUNT_ID],
                constants.CBS_ID: info[constants.CBS_ID],
                constants.BUCKET_NAME: info[constants.BUCKET_NAME],
            }
            for info in self._partners.values()
            if info.get(constants.MGMT_ACCOUNT_ID) is not None
        )

        if not partners_info:
            # No partners configured to get metadata
            return

        # log_group = logs.LogGroup(self, "MetadataStateMachineLogGroup")

        sso_state_machine = sfn.StateMachine(
            self,
            "MetadataStateMachine",
            state_machine_name=self._create_resource_name("MetadataStateMachine"),
            comment="Runs Metadata Lambdas for each partner in parallel.",
            definition_body=sfn.DefinitionBody.from_chainable(
                sfn.Parallel(self, "MetadataParallel").branch(
                    *[
                        sfn_tasks.LambdaInvoke(
                            self,
                            f"SSOMetadataLambda-{partner_info[constants.CBS_ID]}",
                            lambda_function=self.sso_lambda,
                            payload=sfn.TaskInput.from_object(partner_info),
                        )
                        for partner_info in partners_info
                    ],
                    *[
                        sfn_tasks.LambdaInvoke(
                            self,
                            f"IAMMetadataLambda-{partner_info[constants.CBS_ID]}",
                            lambda_function=self.iam_lambda,
                            payload=sfn.TaskInput.from_object(partner_info),
                        )
                        for partner_info in partners_info
                    ],
                )
            ),
            # TODO: `logs:PutRetentionPolicy` being blocked by SCP
            # logs=sfn.LogOptions(destination=log_group, level=sfn.LogLevel.ALL),
        )

        # Grant state machine permission to invoke lambda
        self.sso_lambda.grant_invoke(sso_state_machine)

        # Schedule the orchestration using eventbridge
        rule = events.Rule(
            self,
            "DailyScheduleRule",
            schedule=events.Schedule.rate(cdk.Duration.hours(24)),
        )
        rule.add_target(eventbridge_targets.SfnStateMachine(sso_state_machine))

    def create_dlq_triage_lambda(self, cbs_dlq: sqs.Queue) -> None:
        """Creates DLQ Triage Lambda"""
        dlq_triage_lambda_stack = DlqTriageLambda(
            self,
            "DlqTriageLambda",
            config=self._config,
            layers=[self.powertools_layer, self.core_layer],
            cbs_dlq=cbs_dlq,
        )
        # Grant DLQ Triager consume permissions on DLQ
        cbs_dlq.grant_consume_messages(dlq_triage_lambda_stack.dlq_triager)

    def create_metric_filters(self) -> None:
        """Creates metric filters for Transport and SQS Router Lambdas"""
        transport_lambda_log_group = logs.LogGroup.from_log_group_name(
            self,
            "TransportLambdaLogGroup",
            f"/aws/lambda/{self._create_resource_name('TransportLambda')}",
        )
        sqs_router_lambda_log_group = logs.LogGroup.from_log_group_name(
            self,
            "SQSRouterLambdaLogGroup",
            f"/aws/lambda/{self._create_resource_name('SQSRouterLambda')}",
        )
        log_groups = {
            "TransportLambda": (transport_lambda_log_group, {"CbsId": "$.CbsSensorId"}),
            "SQSRouterLambda": (sqs_router_lambda_log_group, {"CbsId": "$.CbsId"}),
        }
        for function_name, log_group_tuple in log_groups.items():
            log_group, dimensions = log_group_tuple
            self._create_metric_filters(function_name, log_group, dimensions)

    def _create_metric_filters(
        self, function_name: str, log_group: logs.ILogGroup, dimensions: dict[str, str]
    ) -> None:
        """Helper function to create metric filters on the given log groups"""
        logs.MetricFilter(
            self,
            f"{function_name}CloudTrailWorkloadMetricFilter",
            filter_name=self._create_resource_name("CloudTrailWorkloadMetricFilter"),
            log_group=log_group,
            filter_pattern=logs.FilterPattern.all(
                logs.FilterPattern.string_value("$.Workload", "=", "cloudtrailLogs")
            ),
            metric_name="CloudTrailWorkloadCount",
            metric_namespace="CBS",
            dimensions=dimensions,
            unit=cloudwatch.Unit.COUNT,
        )
        logs.MetricFilter(
            self,
            f"{function_name}CoreWorkloadMetricFilter",
            filter_name=self._create_resource_name("CoreWorkloadMetricFilter"),
            log_group=log_group,
            filter_pattern=logs.FilterPattern.any(
                logs.FilterPattern.string_value("$.Workload", "=", "configLogs"),
                logs.FilterPattern.string_value("$.Workload", "=", "*vpcFlowLogs"),
            ),
            metric_name="CoreWorkloadCount",
            metric_namespace="CBS",
            dimensions=dimensions,
            unit=cloudwatch.Unit.COUNT,
        )
        logs.MetricFilter(
            self,
            f"{function_name}CloudWatchWorkloadMetricFilter",
            filter_name=self._create_resource_name("CloudWatchWorkloadMetricFilter"),
            log_group=log_group,
            filter_pattern=logs.FilterPattern.all(
                logs.FilterPattern.string_value("$.Workload", "=", "cloudwatchLogs")
            ),
            metric_name="CloudWatchWorkloadCount",
            metric_namespace="CBS",
            dimensions=dimensions,
            unit=cloudwatch.Unit.COUNT,
        )
        logs.MetricFilter(
            self,
            f"{function_name}MetadataWorkloadMetricFilter",
            filter_name=self._create_resource_name("MetadataWorkloadMetricFilter"),
            log_group=log_group,
            filter_pattern=logs.FilterPattern.all(
                logs.FilterPattern.string_value("$.Workload", "=", "*Metadata")
            ),
            metric_name="MetadataWorkloadCount",
            metric_namespace="CBS",
            dimensions=dimensions,
            unit=cloudwatch.Unit.COUNT,
        )

    def create_s3_output_custom_resource(self) -> None:
        """Writes partner information to inventory table and config bucket"""

        # BatchWriteItem API limits us to 25 map entries:
        # https://docs.aws.amazon.com/amazondynamodb/latest/APIReference/API_BatchWriteItem.html#API_BatchWriteItem_RequestParameters
        def divide_batch(batch: list, max_size: int):
            for i in range(0, len(batch), max_size):
                yield batch[i : i + max_size]

        batch = list(divide_batch(self.create_batch_update(), 25))
        for i, _batch in enumerate(batch):
            update_table_call = cr.AwsSdkCall(
                service="DynamoDB",
                action="batchWriteItem",
                physical_resource_id=cr.PhysicalResourceId.of(
                    self.inventory_table.table_name + f"_update{i}"
                ),
                parameters={
                    "RequestItems": {self.inventory_table.table_name: _batch},
                    "ReturnConsumedCapacity": "TOTAL",
                },
                assumed_role_arn=self.devops_role_arn,
            )

            cr.AwsCustomResource(
                self,
                f"InventoryTableUpdateResource{i}",
                on_update=update_table_call,
                on_create=update_table_call,
                policy=cr.AwsCustomResourcePolicy.from_statements(
                    statements=[
                        iam.PolicyStatement(
                            actions=["sts:AssumeRole"],
                            resources=[self.devops_role_arn],
                        )
                    ]
                ),
            )

        for partner_account_id, partner_data in self._partners.items():
            put_partner_config_call = cr.AwsSdkCall(
                service="S3",
                action="putObject",
                physical_resource_id=cr.PhysicalResourceId.of(
                    partner_data[constants.CBS_ID] + "_config"
                ),
                parameters={
                    "Bucket": self.partner_config_bucket.bucket_name,
                    "Key": f"{partner_account_id}/cbs_config.json",
                    "Body": dumps(
                        dict(
                            destination_account_id=self.account,
                            destination_bucket_name=partner_data[constants.BUCKET_NAME],
                            destination_bucket_key_arn=partner_data[constants.KMS_ARN],
                        )
                    ),
                },
            )
            cr.AwsCustomResource(
                self,
                partner_data[constants.CBS_ID] + "Config",
                on_update=put_partner_config_call,
                on_create=put_partner_config_call,
                policy=cr.AwsCustomResourcePolicy.from_sdk_calls(
                    resources=[
                        self.partner_config_bucket.arn_for_objects(
                            f"{partner_account_id}/*"
                        )
                    ]
                ),
            )

            if mgmt_account_id := partner_data.get(constants.MGMT_ACCOUNT_ID):
                put_partner_tfbackend_call = cr.AwsSdkCall(
                    service="S3",
                    action="putObject",
                    physical_resource_id=cr.PhysicalResourceId.of(
                        partner_data[constants.CBS_ID] + "_tfbackend"
                    ),
                    parameters={
                        "Bucket": self.partner_config_bucket.bucket_name,
                        "Key": f"{partner_account_id}/cbs.s3.tfbackend.json",
                        "Body": dumps(
                            dict(
                                bucket=self.terraform_backend_bucket.bucket_name,
                                key=f"{mgmt_account_id}/cbs",
                                region=self.region,
                            )
                        ),
                    },
                )
                cr.AwsCustomResource(
                    self,
                    partner_data[constants.CBS_ID] + "TFBackend",
                    on_update=put_partner_tfbackend_call,
                    on_create=put_partner_tfbackend_call,
                    policy=cr.AwsCustomResourcePolicy.from_sdk_calls(
                        resources=[
                            self.partner_config_bucket.arn_for_objects(
                                f"{partner_account_id}/*"
                            )
                        ]
                    ),
                )

    def create_batch_update(self) -> list[dict]:
        """Creates DynamoDB Batch Write Request"""
        dynamodb_serializer = TypeSerializer()
        return [
            {
                "PutRequest": {
                    "Item": {
                        constants.ACCOUNT_ID: dynamodb_serializer.serialize(account_id),
                        constants.CBS_ID: dynamodb_serializer.serialize(
                            partner_data[constants.CBS_ID]
                        ),
                        **{
                            k: dynamodb_serializer.serialize(v)
                            for k, v in partner_data.items()
                            if k not in {constants.ACCOUNT_ID, constants.CBS_ID}
                        },
                    }
                }
            }
            for account_id, partner_data in self._partners.items()
        ]
