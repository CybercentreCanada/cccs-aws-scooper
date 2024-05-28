from aws_cdk.assertions import Match, Template

GET_ATT = "Fn::GetAtt"


def test_creates_sqs(cbs_stack_template: Template):
    cbs_stack_template.has_resource_properties(
        "AWS::SQS::Queue",
        {
            "KmsDataKeyReusePeriodSeconds": 43200,
            "KmsMasterKeyId": {
                GET_ATT: [Match.string_like_regexp(r"^SQSKey[\w]*"), "Arn"]
            },
            "RedrivePolicy": {
                "deadLetterTargetArn": {
                    GET_ATT: [Match.string_like_regexp(r"^DLQ[\w]*"), "Arn"]
                },
                "maxReceiveCount": 1,
            },
        },
    )
