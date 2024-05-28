from typing import Callable

from aws_cdk.assertions import Match, Template


def test_creates_sqs_router_lambda(
    cbs_stack_template: Template, _create_resource_name: Callable
):
    cbs_stack_template.has_resource_properties(
        "AWS::Lambda::Function",
        {
            "Role": Match.object_like(
                {
                    "Fn::GetAtt": [
                        Match.string_like_regexp(r"^SQSRouterLambdaServiceRole[\w]*"),
                        "Arn",
                    ]
                }
            ),
            "FunctionName": _create_resource_name("SQSRouterLambda"),
            "Handler": "app.lambda_handler",
            "MemorySize": 256,
            "Runtime": "python3.11",
            "Timeout": 3,
        },
    )


def test_creates_sqs_event_source(cbs_stack_template: Template):
    cbs_stack_template.has_resource_properties(
        "AWS::Lambda::EventSourceMapping",
        {
            "FunctionName": {"Ref": Match.string_like_regexp(r"^SQSRouterLambda[\w]*")},
            "EventSourceArn": Match.string_like_regexp(
                r"^arn:aws:sqs:ca-central-1:[\d]{12}:CbsSQS$"
            ),
        },
    )
