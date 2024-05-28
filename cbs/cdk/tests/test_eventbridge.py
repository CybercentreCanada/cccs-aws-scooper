from aws_cdk.assertions import Match, Template


def test_creates_eventbridge(
    cbs_stack_template: Template, mock_partners: dict[str, dict[str, str]]
):
    cbs_stack_template.has_resource_properties(
        "AWS::Events::Rule",
        {
            "Description": Match.any_value(),
            "EventPattern": Match.exact(
                {
                    "detail-type": ["AWS API Call via CloudTrail"],
                    "source": ["aws.s3"],
                    "detail": {
                        "userIdentity": {
                            "principalId": [{"suffix": ":s3-replication"}],
                            "accountId": (
                                [partner for partner in mock_partners]
                                if mock_partners
                                else ["111111111111"]
                            ),
                        },
                        "eventName": ["PutObject"],
                        "additionalEventData": {
                            "bytesTransferredIn": [{"numeric": [">", 0]}]
                        },
                    },
                }
            ),
            "Name": Match.any_value(),
            "State": Match.exact("ENABLED"),
            "Targets": [
                {
                    "Arn": {
                        "Fn::GetAtt": [
                            Match.string_like_regexp(r"^TransportLambda[\w]*"),
                            "Arn",
                        ]
                    },
                    "DeadLetterConfig": {
                        "Arn": {
                            "Fn::GetAtt": [
                                Match.string_like_regexp(r"^DLQ[\w]*"),
                                "Arn",
                            ]
                        }
                    },
                    "Id": Match.any_value(),
                    "RetryPolicy": {"MaximumRetryAttempts": Match.any_value()},
                }
            ],
        },
    )
