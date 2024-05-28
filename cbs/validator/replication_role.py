from boto3 import client


class ReplicationRole:
    def __init__(
        self,
        role_arn: str,
        source_bucket_name: str,
        destination_bucket_arn: str,
        destination_bucket_key_arn: str,
    ) -> None:
        self.role_arn = role_arn
        self.role_name = self.role_arn.split("/")[-1]
        self._attached_policies = None
        self._source_bucket_arn = f"arn:aws:s3:::{source_bucket_name}"
        self._destination_bucket_arn = destination_bucket_arn
        self._destination_bucket_key_arn = destination_bucket_key_arn

        self._iam_client = client("iam")
        self._s3_client = client("s3")
        self._kms_client = client("kms")

    @property
    def attached_policies(self) -> dict:
        if self._attached_policies is None:
            self._attached_policies = self._iam_client.list_attached_role_policies(
                RoleName=self.role_name
            )["AttachedPolicies"]
        return self._attached_policies

    def _get_policy(self, policy_arn: str) -> dict:
        policy_info = self._iam_client.get_policy(PolicyArn=policy_arn)["Policy"]
        policy_version = self._iam_client.get_policy_version(
            PolicyArn=policy_arn, VersionId=policy_info["DefaultVersionId"]
        )["PolicyVersion"]
        return policy_version["Document"]

    def _get_bucket_key_arn(self, bucket_arn: str) -> tuple[str, str]:
        bucket_name = bucket_arn.split(":")[-1]
        sse_config = self._s3_client.get_bucket_encryption(Bucket=bucket_name)[
            "ServerSideEncryptionConfiguration"
        ]
        for rule in sse_config["Rules"]:
            if rule["ApplyServerSideEncryptionByDefault"]["SSEAlgorithm"] != "aws:kms":
                key_arn = self._kms_client.describe_key(KeyId="alias/aws/s3")[
                    "KeyMetadata"
                ]["Arn"]
                alias_arn = self._kms_client.list_aliases(KeyId=key_arn)["Aliases"][0][
                    "AliasArn"
                ]
                return key_arn, alias_arn
            else:
                key_arn = rule["ApplyServerSideEncryptionByDefault"]["KMSMasterKeyID"]
                return key_arn, ""

    def is_valid_policy(self, policy_arn: str) -> bool:
        statement_check_count = 0
        policy = self._get_policy(policy_arn)
        for statement in policy["Statement"]:
            try:
                if "s3:ReplicateObject" in statement["Action"]:
                    actual_destination_bucket_arns = statement["Resource"]
                    expected_destination_bucket_arn = (
                        f"{self._destination_bucket_arn}/*"
                    )
                    assert (
                        expected_destination_bucket_arn
                        in actual_destination_bucket_arns
                    ), (
                        "The wrong destination bucket is specified in your replication rule's role policy.\n\n"
                        f"Found '{actual_destination_bucket_arns}', but expected '{expected_destination_bucket_arn}'"
                    )
                    statement_check_count += 1
                elif "kms:Decrypt" in statement["Action"]:
                    actual_source_bucket_arns = statement["Condition"]["StringLike"][
                        "kms:EncryptionContext:aws:s3:arn"
                    ]
                    expected_source_bucket_arn = f"{self._source_bucket_arn}/*"
                    actual_source_bucket_key_arns = statement["Resource"]
                    (
                        expected_source_bucket_key_arn,
                        expected_source_bucket_key_alias,
                    ) = self._get_bucket_key_arn(self._source_bucket_arn)
                    assert expected_source_bucket_arn in actual_source_bucket_arns and (
                        expected_source_bucket_key_arn in actual_source_bucket_key_arns
                        or any(
                            key_arn == expected_source_bucket_key_alias
                            for key_arn in actual_source_bucket_key_arns
                        )
                    ), (
                        "The wrong source bucket or source bucket key is specified in your replication rule's role policy.\n\n"
                        f"Found '{actual_source_bucket_arns}', but expected '{expected_source_bucket_arn}'\n\n"
                        f"Found '{actual_source_bucket_key_arns}', but expected '{expected_source_bucket_key_arn}' or '{expected_source_bucket_key_alias}'"
                    )
                    statement_check_count += 1
                elif "kms:Encrypt" in statement["Action"]:
                    actual_destination_bucket_arns = statement["Condition"][
                        "StringLike"
                    ]["kms:EncryptionContext:aws:s3:arn"]
                    expected_destination_bucket_arn = (
                        f"{self._destination_bucket_arn}/*"
                    )
                    actual_destination_bucket_key_arns = statement["Resource"]
                    assert (
                        expected_destination_bucket_arn
                        in actual_destination_bucket_arns
                        and self._destination_bucket_key_arn
                        in actual_destination_bucket_key_arns
                    ), (
                        "The wrong destination bucket or destination bucket key is specified in your replication rule's role policy.\n\n"
                        f"Found '{actual_destination_bucket_arns}', but expected '{expected_destination_bucket_arn}'\n\n"
                        f"Found '{actual_destination_bucket_key_arns}', but expected '{self._destination_bucket_key_arn}'"
                    )
                    statement_check_count += 1
            except KeyError:
                return False

        return statement_check_count == 3
