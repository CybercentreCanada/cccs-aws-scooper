from typing import Callable

from aws_cdk.assertions import Match, Template

from cbs.core import constants


def test_creates_dynamodb_table(
    cicd_stack_template: Template, _create_resource_name: Callable
):
    cicd_stack_template.has_resource_properties(
        "AWS::DynamoDB::Table",
        Match.exact(
            {
                "KeySchema": [
                    {"AttributeName": constants.ACCOUNT_ID, "KeyType": "HASH"},
                    {"AttributeName": constants.CBS_ID, "KeyType": "RANGE"},
                ],
                "AttributeDefinitions": [
                    {"AttributeName": constants.ACCOUNT_ID, "AttributeType": "S"},
                    {"AttributeName": constants.CBS_ID, "AttributeType": "S"},
                ],
                "BillingMode": "PAY_PER_REQUEST",
                "PointInTimeRecoverySpecification": {
                    "PointInTimeRecoveryEnabled": True
                },
                "SSESpecification": {"SSEEnabled": True},
                "TableName": _create_resource_name(constants.INVENTORY_TABLE_NAME),
                "DeletionProtectionEnabled": True,
            }
        ),
    )


def test_creates_dynamodb_role_policy(cicd_stack_template: Template):
    cicd_stack_template.has_resource_properties(
        "AWS::IAM::Policy",
        {
            "PolicyDocument": Match.exact(
                {
                    "Statement": [
                        {
                            "Action": [
                                "dynamodb:BatchWriteItem",
                                "dynamodb:PutItem",
                                "dynamodb:UpdateItem",
                                "dynamodb:DeleteItem",
                                "dynamodb:DescribeTable",
                            ],
                            "Effect": "Allow",
                            "Resource": [
                                {
                                    "Fn::GetAtt": [
                                        Match.string_like_regexp(
                                            r"^CBSInventoryTable[\w]*"
                                        ),
                                        "Arn",
                                    ]
                                },
                                {"Ref": "AWS::NoValue"},
                            ],
                        }
                    ],
                    "Version": "2012-10-17",
                }
            ),
            "PolicyName": Match.string_like_regexp(r"^DevopsDBRoleDefaultPolicy[\w]*"),
            "Roles": [{"Ref": Match.string_like_regexp(r"^DevopsDBRole[\w]*")}],
        },
    )
