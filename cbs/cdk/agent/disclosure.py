from functools import partial

import aws_cdk as cdk
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from constructs import Construct

from cbs.cdk.config import CBSConfig
from cbs.cdk.helpers import create_resource_name
from cbs.lambdas import PATH as LAMBDAS_PATH


class CBSDisclosure(cdk.NestedStack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        config: CBSConfig,
        devops_role_arn: str,
        lambda_layers: list[lambda_.ILayerVersion],
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        _create_resource_name = partial(
            create_resource_name, scope=self, environment=config.Environment
        )

        self.cbs_disclosure_lambda = lambda_.Function(
            self,
            "CBSDisclosureLambda",
            function_name=_create_resource_name("DisclosureLambda"),
            handler="app.lambda_handler",
            runtime=lambda_.Runtime.PYTHON_3_11,
            code=lambda_.Code.from_asset(LAMBDAS_PATH + "/cbs_disclosure/"),
            environment={
                "CBS_DEVOPS_ROLE_ARN": devops_role_arn,
                "CICD_PIPELINE_NAME": _create_resource_name("CICD"),
            },
            memory_size=256,
            layers=lambda_layers,
        )
        self.cbs_disclosure_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["sts:AssumeRole"],
                resources=[devops_role_arn],
            )
        )

        self.scheduler_role = iam.Role(
            self,
            "SchedulerRole",
            role_name=_create_resource_name("SchedulerRole"),
            assumed_by=iam.ServicePrincipal("scheduler.amazonaws.com"),
        )
        self.scheduler_role.add_to_principal_policy(
            iam.PolicyStatement(
                actions=["lambda:InvokeFunction"],
                resources=[self.cbs_disclosure_lambda.function_arn],
            )
        )
