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

from json import dumps as json_dumps

from aws_cdk import NestedStack
from aws_cdk import aws_cloudformation as cf
from aws_cdk import aws_iam as iam
from constructs import Construct
from yaml import safe_load as yaml_load

from scooper.cdk.custom_constructs.role import Role
from scooper.cdk.stacks.custom_queries import POLICY_PATH, STACKSETS_TEMPLATE_PATH
from scooper.core.config import ScooperConfig


class CustomQueries(NestedStack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        scooper_config: ScooperConfig,
        scooper_reader_role: Role,
        **_,
    ) -> None:
        super().__init__(scope, construct_id)

        with POLICY_PATH.open() as f:
            policy = yaml_load(f)

        with STACKSETS_TEMPLATE_PATH.open() as f:
            template_body = yaml_load(f)

        document = iam.PolicyDocument(
            statements=[
                iam.PolicyStatement(
                    sid=statement["Sid"],
                    effect=iam.Effect.ALLOW
                    if statement["Effect"] == "Allow"
                    else iam.Effect.DENY,
                    actions=statement["Action"]
                    if isinstance(statement["Action"], list)
                    else [statement["Action"]],
                    resources=statement["Resource"]
                    if isinstance(statement["Resource"], list)
                    else [statement["Resource"]],
                )
                for statement in policy["PolicyDocument"]["Statement"]
            ],
            minimize=True,
        )
        custom_queries_policy = iam.Policy(
            self,
            "CustomQueriesPolicy",
            policy_name=policy["PolicyName"],
            document=document,
        )
        # Overwrite the policy document with its JSON-ified CDK construct to take advantage of CDK's minimization of policy statements
        policy["PolicyDocument"] = document.to_json()

        role_properties = template_body["Resources"]["ScooperCustomQueryRole"][
            "Properties"
        ]
        role_properties["Policies"] = [policy]
        role_properties["AssumeRolePolicyDocument"]["Statement"][0]["Principal"][
            "AWS"
        ] = scooper_reader_role.role_arn

        self.role_name: str = role_properties["RoleName"]
        custom_query_role = iam.Role(
            self,
            "ScooperCustomQueryRole",
            role_name=self.role_name,
            description=role_properties["Description"],
            assumed_by=scooper_reader_role,
        )
        custom_queries_policy.attach_to_role(custom_query_role)
        custom_query_role.add_to_policy(
            iam.PolicyStatement(
                sid="ScooperCustomQueryRolePivot",
                actions=[
                    "organizations:ListAccounts"
                ],  # For pivoting to member account roles
                resources=["*"],
            )
        )

        cf.CfnStackSet(
            self,
            "ScooperStackSet",
            stack_set_name="ScooperCustomQueryRoles",
            description="Deploys a Scooper custom query role in all member accounts.",
            permission_model="SERVICE_MANAGED",
            capabilities=["CAPABILITY_NAMED_IAM"],
            auto_deployment=cf.CfnStackSet.AutoDeploymentProperty(
                enabled=True,
                retain_stacks_on_account_removal=False,
            ),
            managed_execution={"Active": True},
            operation_preferences=cf.CfnStackSet.OperationPreferencesProperty(
                failure_tolerance_count=1,
                max_concurrent_percentage=100,
            ),
            template_body=json_dumps(template_body),
            stack_instances_group=[
                cf.CfnStackSet.StackInstancesProperty(
                    deployment_targets=cf.CfnStackSet.DeploymentTargetsProperty(
                        organizational_unit_ids=[scooper_config.root_id]
                    ),
                    regions=[self.region],
                )
            ],
        )
