from datetime import date

import aws_cdk as cdk
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from constructs import Construct

from cbs.cdk.agent.stack import AgentStack
from cbs.cdk.config import CBSConfig
from cbs.cdk.helpers import create_resource_name
from cbs.core.types import Partner


class Deploy(cdk.Stage):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        config: CBSConfig,
        partners: dict[str, Partner],
        inventory_table: dynamodb.Table,
        partner_config_bucket: s3.Bucket,
        terraform_backend_bucket: s3.Bucket,
        devops_role: iam.Role,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        AgentStack(
            self,
            "AgentStack",
            stack_name=create_resource_name(
                resource_name="Agent", environment=config.Environment
            ),
            config=config,
            partners=partners,
            inventory_table=inventory_table,
            partner_config_bucket=partner_config_bucket,
            terraform_backend_bucket=terraform_backend_bucket,
            devops_role=devops_role,
            tags={
                "Owner": "ADS4C",
                "Team": "ADS4C",
                "LastUpdated": str(date.today()),
                "AgentVersion": scope.tags.tag_values()["AgentVersion"],
                "Environment": config.Environment.capitalize(),
            },
            termination_protection=config.Environment == "prod",
        )
