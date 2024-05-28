from aws_cdk.assertions import Match, Template


def test_creates_s3_bucket(
    cbs_stack_template: Template, mock_partners: dict[str, dict[str, str]]
):
    if mock_partners:
        cbs_stack_template.has_resource_properties(
            "AWS::S3::Bucket",
            {
                "BucketEncryption": {
                    "ServerSideEncryptionConfiguration": Match.exact(
                        [
                            {
                                "BucketKeyEnabled": True,
                                "ServerSideEncryptionByDefault": {
                                    "KMSMasterKeyID": {
                                        "Fn::GetAtt": [Match.any_value(), "Arn"]
                                    },
                                    "SSEAlgorithm": "aws:kms",
                                },
                            }
                        ]
                    )
                },
                "MetricsConfigurations": [{"Id": "RequestMetrics"}],
                "OwnershipControls": {
                    "Rules": Match.exact([{"ObjectOwnership": "BucketOwnerEnforced"}])
                },
                "PublicAccessBlockConfiguration": Match.exact(
                    {
                        "BlockPublicAcls": True,
                        "BlockPublicPolicy": True,
                        "IgnorePublicAcls": True,
                        "RestrictPublicBuckets": True,
                    }
                ),
                "Tags": Match.exact(
                    [{"Key": "aws-cdk:auto-delete-objects", "Value": "true"}]
                ),
                "VersioningConfiguration": Match.exact({"Status": "Enabled"}),
            },
        )
