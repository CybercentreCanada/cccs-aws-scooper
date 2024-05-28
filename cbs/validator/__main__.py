#!/usr/bin/env python3
from dataclasses import replace

from core.cbs_config import RemoteConfig

from .replication_rule import EXPECTED_CONFIG, ReplicationConfiguration
from .validate import cbs_validate


def main():
    remote_config = RemoteConfig.from_file(__package__, "remote_config.json")

    expected_config = ReplicationConfiguration(**EXPECTED_CONFIG)
    expected_replication_rule = expected_config.Rules[0]
    replication_destination_replacement = {
        "Account": remote_config.config.destination_account_id,
        "Bucket": f"arn:aws:s3:::{remote_config.config.destination_bucket_name}",
        "EncryptionConfiguration": {
            "ReplicaKmsKeyID": remote_config.config.destination_bucket_key_arn
        },
    }
    # Plug command-line arguments into expected configuration
    expected_replication_rule.replication_destination = replace(
        expected_replication_rule.replication_destination,
        **replication_destination_replacement,
    )

    cbs_validate(expected_replication_rule)


if __name__ == "__main__":
    main()
