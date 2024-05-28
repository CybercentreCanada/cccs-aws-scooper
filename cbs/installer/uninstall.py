from os import environ

from boto3 import Session
from botocore.client import BaseClient
from core.cbs_config import RemoteConfig

from .core.constants import CBS, CONTROL_TOWER_BUCKET_NAME_PREFIX
from .replication_rule.config import ReplicationConfiguration
from .replication_rule.control_tower_config import ControlTowerCMK
from .replication_rule.policies import CONTROL_TOWER_CMK_POLICY_PATH
from .utils.io import run_cmd
from .utils.logging import LOGGER


def uninstall_replication_rules(
    session: Session,
    s3_client: BaseClient,
    state: dict,
    remote_config: RemoteConfig,
    is_management_account: bool,
) -> bool:
    """Uninstall CBS replication rules"""
    LOGGER.info("Uninstalling CBS Replication Rules...")
    LOGGER.debug("Pre-uninstall state: %s", state)
    state_change = False

    for bucket in state:
        LOGGER.info("Uninstalling CBS on '%s'...", bucket)
        try:
            if bucket.startswith(CONTROL_TOWER_BUCKET_NAME_PREFIX):
                if is_management_account:
                    management_account_session = Session()
                    control_tower_cmk = ControlTowerCMK(management_account_session)
                    control_tower_cmk.remove_from_policy(
                        CONTROL_TOWER_CMK_POLICY_PATH,
                        log_archive_account_id=remote_config.log_archive_account_id,
                    )
                else:
                    LOGGER.warning(
                        "Skipping CBS uninstall on bucket '%s' - cannot manage Control Tower CMK from outside Management Account!",
                        bucket,
                    )
                    continue
            replication_config = ReplicationConfiguration(
                bucket, remote_config.config, session, s3_client
            )
            replication_config.remove_cbs_config()
            for rule in state[bucket]["Rules"]:
                if rule["ID"] == CBS:
                    state[bucket]["Rules"].remove(rule)
                    state_change = True
            if "Policies" in state[bucket]:
                state[bucket]["Policies"] = {
                    policy_name: policy
                    for policy_name, policy in (
                        (k, v) for k, v in state[bucket]["Policies"].items()
                    )
                    if not policy_name.startswith(CBS)
                }
            LOGGER.info("\u26C5 Successfully uninstalled CBS on '%s' \u26C5", bucket)
        except Exception as e:
            LOGGER.error("\u26C8 Failed to uninstall CBS on '%s' \u26C8: %s", bucket, e)

    return state_change


def uninstall_global_reader_roles(remote_config: RemoteConfig, tf_path: str) -> None:
    """Uninstall CBS global reader roles"""
    LOGGER.info("Uninstalling CBS Global Reader Roles...")
    run_cmd(
        f"terraform -chdir={tf_path} init -backend-config={tf_path + '/cbs.s3.tfbackend.json'}"
    )
    environ["TF_VAR_cccs_role_arn"] = remote_config.kwargs["cccs_role_arn"]
    run_cmd(f"terraform -chdir={tf_path} destroy -auto-approve")
    LOGGER.info("Successfully uninstalled CBS Global Reader Roles!")


def cbs_uninstall(
    session: Session,
    s3_client: BaseClient,
    state: dict,
    remote_config: RemoteConfig,
    tf_path: str,
    uninstall_global_readers: bool,
) -> bool:
    """Full CBS uninstall"""
    LOGGER.info("\u26C5 Uninstalling CBS... \u26C5")
    state_change = uninstall_replication_rules(
        session, s3_client, state, remote_config, uninstall_global_readers
    )

    if uninstall_global_readers:
        uninstall_global_reader_roles(remote_config, tf_path)

    return state_change
