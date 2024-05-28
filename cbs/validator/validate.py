from boto3 import client
from botocore.exceptions import ClientError
from colors import color

from .replication_role import ReplicationRole
from .replication_rule import ReplicationConfiguration, ReplicationRule


def print_replication_rule_diff(
    actual_replication_rules: list[ReplicationRule],
    expected_replication_rule: ReplicationRule,
) -> None:
    for actual_replication_rule in actual_replication_rules:
        if expected_replication_rule != actual_replication_rule:
            print(
                color(
                    f"\nFor replication rule '{actual_replication_rule.ID}':",
                    fg="blue",
                    style="bold+underline",
                )
            )
            for diff in expected_replication_rule - actual_replication_rule:
                expected_value = expected_replication_rule.get_value(diff[0])
                actual_value = actual_replication_rule.get_value(diff[0])
                if expected_value != actual_value:
                    print(
                        color(
                            f"Expected '{diff[0]}' to be '{expected_value}' but got '{actual_value}'",
                            fg="cyan",
                        ),
                        end="\n\n",
                    )


def check_replication_role_policy(
    replication_role: ReplicationRole, bucket_name: str
) -> bool:
    replication_role_policies_evaluation = {}
    replication_role_configured = False
    # Check if there's at least one valid policy attached to replication role
    for policy in replication_role.attached_policies:
        try:
            assert replication_role.is_valid_policy(
                policy["PolicyArn"]
            ), "Replication rule's role policy differs from what is expected."
            replication_role_policies_evaluation[policy["PolicyArn"]] = {"valid": True}
        except AssertionError as e:
            replication_role_policies_evaluation[policy["PolicyArn"]] = {
                "valid": False,
                "reason": e,
            }
    for policy_evaluation in replication_role_policies_evaluation.values():
        if policy_evaluation["valid"]:
            replication_role_configured = True
            break
    if not replication_role_configured:
        print(
            color(
                f"Bucket '{bucket_name}' does not have the expected replication role policy:\n",
                fg="red",
                style="bold",
            )
        )
        for (
            policy_arn,
            policy_evaluation,
        ) in replication_role_policies_evaluation.items():
            if not policy_evaluation["valid"]:
                print(color(f"{policy_arn}: {policy_evaluation['reason']}", fg="cyan"))
    return replication_role_configured


def cbs_validate(expected_replication_rule: ReplicationRule):
    s3_client = client("s3")

    buckets = s3_client.list_buckets()["Buckets"]
    replication_rule_configured = False

    for bucket in buckets:
        bucket_name = bucket["Name"]
        try:
            # Get current replication configuration
            response = s3_client.get_bucket_replication(Bucket=bucket_name)
            actual_replication_config = ReplicationConfiguration(
                **response["ReplicationConfiguration"]
            )
        except ClientError:
            # Catch ReplicationConfigurationNotFoundError and continue to next bucket
            print(
                color(
                    f"Bucket '{bucket_name}' does not have any replication rules configured",
                    fg="yellow",
                    style="bold",
                )
            )
            continue

        try:
            # If there isn't at least one replication rule that is configured as we expect, raise AssertionError
            assert any(
                expected_replication_rule == rule
                for rule in actual_replication_config.Rules
            ), "Replication rule configuration differs from what is expected."
            # If we make it here then there's at least one valid replication rule
            replication_rule_configured = True
        except AssertionError as e:
            print(
                color(
                    f"\nBucket '{bucket_name}' does not have the expected replication rule configured: {e}",
                    fg="red",
                    style="bold",
                )
            )
            print_replication_rule_diff(
                actual_replication_config.Rules, expected_replication_rule
            )

        replication_role = ReplicationRole(
            role_arn=actual_replication_config.Role,
            source_bucket_name=bucket_name,
            destination_bucket_arn=expected_replication_rule.replication_destination.Bucket,
            destination_bucket_key_arn=expected_replication_rule.replication_destination.EncryptionConfiguration[
                "ReplicaKmsKeyID"
            ],
        )
        replication_role_configured = check_replication_role_policy(
            replication_role, bucket_name
        )

        if replication_rule_configured and replication_role_configured:
            print(
                color(
                    f"Bucket '{bucket_name}' replication is configured correctly!",
                    fg="green",
                    style="bold",
                )
            )
