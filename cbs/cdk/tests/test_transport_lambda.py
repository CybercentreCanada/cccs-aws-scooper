from typing import Callable

from aws_cdk.assertions import Match, Template


def test_creates_transport_lambda(
    cbs_stack_template: Template, _create_resource_name: Callable
):
    cbs_stack_template.has_resource_properties(
        "AWS::Lambda::Function",
        {
            "Role": Match.object_like(
                {
                    "Fn::GetAtt": [
                        Match.string_like_regexp(r"^TransportLambdaServiceRole[\w]*"),
                        "Arn",
                    ]
                }
            ),
            "DeadLetterConfig": Match.object_like(
                {
                    "TargetArn": {
                        "Fn::GetAtt": [Match.string_like_regexp(r"^DLQ[\w]*"), "Arn"]
                    }
                }
            ),
            "FunctionName": _create_resource_name("TransportLambda"),
            "Handler": "app.lambda_handler",
            "MemorySize": 256,
            "Runtime": "python3.11",
            "Timeout": 4,
        },
    )


def test_eventbridge_lambda_invocation(cbs_stack_template: Template):
    cbs_stack_template.has_resource_properties(
        "AWS::Lambda::Permission",
        {
            "Action": Match.exact("lambda:InvokeFunction"),
            "FunctionName": {
                "Fn::GetAtt": [
                    Match.string_like_regexp(r"^TransportLambda[\w]*"),
                    "Arn",
                ]
            },
            "Principal": Match.exact("events.amazonaws.com"),
            "SourceArn": {
                "Fn::GetAtt": [
                    Match.string_like_regexp(
                        r"^S3ReplicationEventsToTransportLambda[\w]*"
                    ),
                    "Arn",
                ]
            },
        },
    )
