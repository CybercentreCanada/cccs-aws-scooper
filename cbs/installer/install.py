from os import environ

from boto3 import Session
from botocore.client import BaseClient
from core.cbs_config import RemoteConfig

from .batch_replication.job import S3BatchOperationsJob
from .core.constants import CONTROL_TOWER_BUCKET_NAME_PREFIX
from .replication_rule.config import ReplicationConfiguration
from .replication_rule.control_tower_config import (
    ControlTowerCMK,
    ControlTowerReplicationConfiguration,
)
from .replication_rule.policies import CONTROL_TOWER_CMK_POLICY_PATH
from .utils.install import enable_service_access, install_terraform
from .utils.io import boolean_prompt, bucket_input, date_range_input, run_cmd
from .utils.logging import LOGGER


def install_replication_rules(
    session: Session,
    s3_client: BaseClient,
    state: dict,
    remote_config: RemoteConfig,
    is_management_account: bool,
) -> bool:
    """Install CBS replication rules."""
    LOGGER.info("Installing CBS Replication Rules...")
    LOGGER.debug("Pre-install state: %s", state)
    state_change = False

    buckets = {
        i: bucket["Name"]
        for i, bucket in enumerate(s3_client.list_buckets()["Buckets"], start=1)
    }
    LOGGER.info("Buckets:")
    for i, bucket in buckets.items():
        LOGGER.info("[%s]: %s", i, bucket)

    bucket_selection = bucket_input(limit=len(buckets))

    for i in bucket_selection:
        bucket_name = buckets[i]
        batch_replication_eligible = False
        LOGGER.info("Installing CBS on '%s'...", bucket_name)
        try:
            if bucket_name.startswith(CONTROL_TOWER_BUCKET_NAME_PREFIX):
                if is_management_account:
                    management_account_session = Session()
                    control_tower_cmk = ControlTowerCMK(management_account_session)
                else:
                    LOGGER.warning(
                        "Skipping CBS install on bucket '%s' - cannot manage Control Tower CMK from outside Management Account!",
                        bucket_name,
                    )
                    continue
                if control_tower_cmk.arn is not None:
                    replication_config = ControlTowerReplicationConfiguration(
                        control_tower_cmk.arn,
                        bucket_name,
                        remote_config.config,
                        session,
                        s3_client,
                    )
                    # Allow replication role to decrypt using CMK
                    control_tower_cmk.add_to_policy(
                        CONTROL_TOWER_CMK_POLICY_PATH,
                        log_archive_account_id=remote_config.log_archive_account_id,
                    )
                else:
                    LOGGER.warning(
                        "Skipping CBS install on bucket '%s' - couldn't find Control Tower's CMK!",
                        bucket_name,
                    )
                    continue
            else:
                replication_config = ReplicationConfiguration(
                    bucket_name, remote_config.config, session, s3_client
                )
            replication_config.set_cbs_config()
            state[bucket_name] = replication_config.get_config()
            state[bucket_name]["Policies"] = {
                policy["PolicyName"]: replication_config.role.get_policy(
                    policy["PolicyArn"]
                )
                for policy in replication_config.role.attached_policies
            }
            state_change = True
            LOGGER.info("\u26C5 Successfully installed CBS on '%s' \u26C5", bucket_name)
            batch_replication_eligible = True
        except ValueError as e:
            if "CBS replication rule already exists" in str(e):
                LOGGER.warning(e)
                batch_replication_eligible = True
            else:
                LOGGER.error(
                    "\u26C8 Failed to install CBS on '%s' \u26C8: %s", bucket_name, e
                )
        except Exception as e:
            LOGGER.error(
                "\u26C8 Failed to install CBS on '%s' \u26C8: %s", bucket_name, e
            )

        if batch_replication_eligible:
            if boolean_prompt(f"Configure batch replication for '{bucket_name}'?"):
                state_change = (
                    configure_batch_replication(session, state, bucket_name)
                    or state_change
                )

    return state_change


def configure_batch_replication(
    session: Session, state: dict, bucket_name: str
) -> bool:
    """Configure batch replication job."""
    state_change = False
    try:
        start_date, end_date = date_range_input()
        job = S3BatchOperationsJob(bucket_name, start_date, end_date, session)
        job.create_batch_operations_job()
        if bucket_name not in state:
            state[bucket_name] = {}
        state[bucket_name]["BatchReplication"] = {
            "start_date": str(start_date.date()),
            "end_date": str(end_date.date()),
            "role_arn": job.role.arn,
        }
        state_change = True
        LOGGER.info(
            "\u26C5 Successfully configured batch replication on '%s' \u26C5",
            bucket_name,
        )
    except Exception as e:
        LOGGER.error(
            "\u26C8 Failed to configure batch replication on '%s' \u26C8: %s",
            bucket_name,
            e,
        )

    return state_change


def install_global_reader_roles(remote_config: RemoteConfig, tf_path: str) -> None:
    """Install CBS global reader roles."""
    enable_service_access("member.org.stacksets.cloudformation.amazonaws.com")
    install_terraform()

    LOGGER.info("Installing CBS Global Reader Roles...")
    run_cmd(
        f"terraform -chdir={tf_path} init -backend-config={tf_path + '/cbs.s3.tfbackend.json'}"
    )
    environ["TF_VAR_cccs_role_arn"] = remote_config.kwargs["cccs_role_arn"]
    run_cmd(f"terraform -chdir={tf_path} apply -auto-approve")
    LOGGER.info("Successfully installed CBS Global Reader Roles!")


def cbs_install(
    session: Session,
    s3_client: BaseClient,
    state: dict,
    remote_config: RemoteConfig,
    tf_path: str,
    install_global_readers: bool,
) -> bool:
    """Full CBS install"""
    LOGGER.info("\u26C5 Installing CBS... \u26C5")
    state_change = install_replication_rules(
        session, s3_client, state, remote_config, install_global_readers
    )

    if install_global_readers:
        install_global_reader_roles(remote_config, tf_path)

    return state_change
