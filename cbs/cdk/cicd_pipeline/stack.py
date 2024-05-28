from functools import partial

import aws_cdk as cdk
import aws_cdk.aws_codebuild as codebuild
import aws_cdk.aws_dynamodb as dynamodb
import aws_cdk.aws_iam as iam
import aws_cdk.aws_s3 as s3
import aws_cdk.pipelines as pipelines
from boto3 import Session
from constructs import Construct

from cbs.cdk import helpers
from cbs.cdk.cicd_pipeline.deploy import Deploy
from cbs.cdk.config import CBSConfig
from cbs.cdk.iamra.stack import IAMRolesAnywhereStack
from cbs.core import constants
from cbs.core.types import Partner
from cbs.core.utils.dynamodb import read_partner_inventory_table


class CicdPipelineStack(cdk.Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        config: CBSConfig,
        branch: str,
        deploy_to_env: cdk.Environment,
        **kwargs,
    ) -> None:
        """Registers GitHub webhook to given branch, lints and tests changes,
        then deploys CbsAwsStack to given environment

        Args:
            scope (Construct): CDK app
            construct_id (str): Stack name
            config (CBSConfig): Environment specific configuration parameters
            branch (str): GitHub branch to subscribe to for changes
            deploy_to_env (cdk.Environment): Account to deploy the CbsAwsStack to
        """
        super().__init__(scope, construct_id, **kwargs)

        self._construct_id = construct_id
        self._config = config
        self._branch = branch
        self._sensor_env = deploy_to_env
        self._create_resource_name = partial(
            helpers.create_resource_name, scope=self, environment=config.Environment
        )
        self._table_name = self._create_resource_name(constants.INVENTORY_TABLE_NAME)

        self.partners = self._get_partners()
        self._create_devops_role()
        self.inventory_table = helpers.create_inventory_table(
            scope=self,
            table_name=self._table_name,
            database_management_account=self._sensor_env.account,
            agent_account=config.AgentAccount,
        )
        pipeline = self.create_pipeline(self.inventory_table)
        self.inventory_table.grant_read_write_data(self.devops_role)
        self.devops_role.add_to_policy(
            iam.PolicyStatement(
                actions=["codepipeline:StartPipelineExecution"],
                resources=[pipeline.pipeline.pipeline_arn],
            )
        )

    def _get_partners(self) -> dict[str, Partner]:
        try:
            partners = read_partner_inventory_table(self._table_name, Session())
        except Exception:
            if self._config.Environment == "test":
                partners = {
                    "111111111111": {
                        "cbs-id": "testpartner1",
                        "accelerator": "asea",
                    },
                    "222222222222": {
                        "cbs-id": "testpartner2",
                        "accelerator": "lza",
                    },
                }
            else:
                raise

        return partners

    def _create_devops_role(self) -> None:
        self.devops_role: iam.Role = iam.Role(
            self,
            "DevOpsRole",
            role_name=self._create_resource_name("DevOpsRole"),
            assumed_by=iam.AccountPrincipal(self.account),
        )
        self.devops_role.assume_role_policy.add_statements(
            iam.PolicyStatement(
                principals=[iam.ServicePrincipal("rolesanywhere.amazonaws.com")],
                actions=["sts:AssumeRole", "sts:TagSession", "sts:SetSourceIdentity"],
                conditions={
                    "StringEquals": {
                        "aws:PrincipalTag/x509Subject/CN": "CBS",
                    },
                },
            )
        )
        IAMRolesAnywhereStack(
            self, "IAMRA-DevOps", config=self._config, role=self.devops_role
        )

    def create_pipeline(
        self, inventory_table: dynamodb.Table
    ) -> pipelines.CodePipeline:
        """Creates CI/CD pipeline for CBS stack in given environment"""
        cdk_dir = "cbs/cdk"

        if self._config.UsePAT:
            pat = cdk.SecretValue.secrets_manager(
                "github-token", json_field="github-token"
            )

            source = pipelines.CodePipelineSource.git_hub(
                repo_string="CybercentreCanada/cbs-aws-2",
                branch=self._branch,
                authentication=pat,
            )
        else:
            source_bucket = s3.Bucket(
                self,
                "S3SourceBucket",
                bucket_name=cdk.PhysicalName.GENERATE_IF_NEEDED,
                access_control=s3.BucketAccessControl.PRIVATE,
                encryption=s3.BucketEncryption.S3_MANAGED,
                enforce_ssl=True,
                versioned=True,
                removal_policy=cdk.RemovalPolicy.DESTROY,
                block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
                auto_delete_objects=True,
                lifecycle_rules=[
                    s3.LifecycleRule(
                        enabled=True,
                        expiration=cdk.Duration.days(14),
                        noncurrent_versions_to_retain=1,
                    )
                ],
            )
            source = pipelines.CodePipelineSource.s3(
                bucket=source_bucket, object_key="cbs.zip"
            )

        artifact_bucket = s3.Bucket(
            self,
            "ArtifactBucket",
            versioned=True,
            removal_policy=cdk.RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            enforce_ssl=True,
        )

        # Allow devops role to publish artifacts to bucket
        artifact_bucket.grant_write(self.devops_role)
        artifact_bucket.add_to_resource_policy(
            iam.PolicyStatement(
                principals=[
                    iam.AccountPrincipal(self.account),
                    self.devops_role,
                ],
                actions=["s3:PutObject*"],
                resources=[
                    artifact_bucket.bucket_arn,
                    artifact_bucket.arn_for_objects("*"),
                ],
            )
        )

        # Allow partner log archive accounts to download artifacts
        artifact_bucket.add_to_resource_policy(
            iam.PolicyStatement(
                principals=[iam.AccountPrincipal(partner) for partner in self.partners],
                actions=["s3:GetObject"],
                resources=[
                    artifact_bucket.bucket_arn,
                    artifact_bucket.arn_for_objects("*"),
                ],
            )
        )
        # Allow partner management accounts to download artifacts
        for partner in self.partners.values():
            if mgmt_account_id := partner.get(constants.MGMT_ACCOUNT_ID):
                artifact_bucket.add_to_resource_policy(
                    iam.PolicyStatement(
                        principals=[iam.AccountPrincipal(mgmt_account_id)],
                        actions=["s3:GetObject"],
                        resources=[
                            artifact_bucket.bucket_arn,
                            artifact_bucket.arn_for_objects("*"),
                        ],
                    )
                )

        partner_config_bucket = s3.Bucket(
            self,
            "PartnerConfigBucket",
            bucket_name=cdk.PhysicalName.GENERATE_IF_NEEDED,
            versioned=True,
            removal_policy=cdk.RemovalPolicy.RETAIN,
            enforce_ssl=True,
        )

        partner_config_bucket.add_to_resource_policy(
            iam.PolicyStatement(
                principals=[iam.AccountPrincipal(self._sensor_env.account)],
                actions=["s3:PutObject*"],
                resources=[partner_config_bucket.arn_for_objects("*")],
            )
        )

        for partner in self.partners:
            partner_config_bucket.add_to_resource_policy(
                iam.PolicyStatement(
                    principals=[iam.AccountPrincipal(partner)],
                    actions=["s3:GetObject", "s3:PutObject*"],
                    resources=[partner_config_bucket.arn_for_objects(f"{partner}/*")],
                )
            )

        tf_state_bucket = s3.Bucket(
            self,
            "TerraformStateBucket",
            bucket_name=cdk.PhysicalName.GENERATE_IF_NEEDED,
            versioned=True,
            removal_policy=cdk.RemovalPolicy.RETAIN,
            enforce_ssl=True,
        )
        # https://developer.hashicorp.com/terraform/language/settings/backends/s3#permissions-required
        tf_state_bucket.add_to_resource_policy(
            iam.PolicyStatement(
                principals=[self.devops_role],
                actions=["s3:ListBucket"],
                resources=[tf_state_bucket.bucket_arn],
            )
        )
        tf_state_bucket.add_to_resource_policy(
            iam.PolicyStatement(
                principals=[self.devops_role],
                actions=["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
                resources=[tf_state_bucket.arn_for_objects("*")],
            )
        )
        for partner in self.partners.values():
            if mgmt_account_id := partner.get(constants.MGMT_ACCOUNT_ID):
                tf_state_bucket.add_to_resource_policy(
                    iam.PolicyStatement(
                        principals=[iam.AccountPrincipal(mgmt_account_id)],
                        actions=["s3:ListBucket"],
                        resources=[tf_state_bucket.bucket_arn],
                    )
                )
                tf_state_bucket.add_to_resource_policy(
                    iam.PolicyStatement(
                        principals=[iam.AccountPrincipal(mgmt_account_id)],
                        actions=["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
                        resources=[
                            tf_state_bucket.arn_for_objects(f"{mgmt_account_id}/*")
                        ],
                    )
                )

        # AWS SAM Permissions needed to manage CBS Common Lambda Layer:
        # https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/sam-permissions-cloudformation.html
        self.devops_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "cloudformation:CreateChangeSet",
                    "cloudformation:CreateStack",
                    "cloudformation:DeleteStack",
                    "cloudformation:DescribeChangeSet",
                    "cloudformation:DescribeStackEvents",
                    "cloudformation:DescribeStacks",
                    "cloudformation:ExecuteChangeSet",
                    "cloudformation:GetTemplateSummary",
                    "cloudformation:ListStackResources",
                    "cloudformation:UpdateStack",
                ],
                resources=[
                    f"arn:aws:cloudformation:{self.region}:{self.account}:stack/cbs-common"
                ],
            )
        )
        self.devops_role.add_to_policy(
            iam.PolicyStatement(
                actions=["s3:CreateBucket", "s3:GetObject", "s3:PutObject"],
                resources=["arn:aws:s3:::*/*"],
            )
        )
        self.devops_role.add_to_policy(
            iam.PolicyStatement(
                actions=["lambda:*Layer*"],
                resources=[f"arn:aws:lambda:{self.region}:{self.account}:layer:*"],
            )
        )

        pipeline = pipelines.CodePipeline(
            self,
            self._construct_id,
            pipeline_name=self._construct_id,
            synth_code_build_defaults=pipelines.CodeBuildOptions(
                build_environment=codebuild.BuildEnvironment(
                    build_image=codebuild.LinuxBuildImage.STANDARD_7_0
                ),
                role_policy=[
                    iam.PolicyStatement(
                        actions=[
                            "dynamodb:BatchGetItem",
                            "dynamodb:DescribeTable",
                            "dynamodb:GetItem",
                            "dynamodb:GetRecords",
                            "dynamodb:GetShardIterator",
                            "dynamodb:Query",
                            "dynamodb:Scan",
                        ],
                        resources=[inventory_table.table_arn],
                    ),
                    iam.PolicyStatement(
                        actions=["ssm:GetParameter", "ssm:PutParameter"],
                        resources=[
                            f"arn:aws:ssm:{self.region}:{self.account}:parameter/cbs_config"
                        ],
                    ),
                    iam.PolicyStatement(
                        actions=["sts:AssumeRole"],
                        resources=[
                            f"arn:aws:iam::{self._config.AgentAccount}:role/cdk-hnb659fds-lookup-role-{self._config.AgentAccount}-{self.region}"
                        ],
                    ),
                    iam.PolicyStatement(
                        actions=["s3:GetObject"],
                        resources=[partner_config_bucket.arn_for_objects("*")],
                    ),
                ],
            ),
            docker_enabled_for_synth=True,
            synth=pipelines.ShellStep(
                "Synth",
                input=source,
                install_commands=[
                    f"cd {cdk_dir}",
                    "npm install -g aws-cdk",
                    "python -m pip install -r ../requirements.txt",
                ],
                commands=[f"cdk synth -c config={self._config.Environment}"],
                primary_output_directory=f"{cdk_dir}/cdk.out",
            ),
            cross_account_keys=True,
            enable_key_rotation=True,
        )

        pipeline.add_wave(
            "RunTests",
            pre=[
                pipelines.CodeBuildStep(
                    "Testing",
                    build_environment=codebuild.BuildEnvironment(
                        build_image=codebuild.LinuxBuildImage.STANDARD_7_0,
                        privileged=True,
                    ),
                    install_commands=["python -m pip install -r requirements-dev.txt"],
                    commands=[
                        "python -m pytest --cov . --cov-report html --cov-config .coveragerc"
                    ],
                )
            ],
        )

        # Allow sensor account to assume devops role for writing to inventory table
        self.devops_role.assume_role_policy.add_statements(
            iam.PolicyStatement(
                actions=["sts:AssumeRole"],
                principals=[iam.AccountPrincipal(self._sensor_env.account)],
            )
        )

        if not self._config.OnlyAgent:
            pipeline.add_stage(
                Deploy(
                    self,
                    f"DeployTo{self._config.Environment.capitalize()}",
                    env=self._sensor_env,
                    config=self._config,
                    partners=self.partners,
                    inventory_table=self.inventory_table,
                    partner_config_bucket=partner_config_bucket,
                    terraform_backend_bucket=tf_state_bucket,
                    devops_role=self.devops_role,
                )
            )

        pipeline.build_pipeline()
        return pipeline
