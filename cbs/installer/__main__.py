#!/usr/bin/env python3
from importlib.resources import files
from json import dumps, loads

from boto3 import Session
from botocore.exceptions import ClientError
from click import command, option
from core.cbs_config import RemoteConfig

from .install import cbs_install
from .uninstall import cbs_uninstall
from .utils.logging import LOG_FILE_NAME, LOGGER
from .utils.sts import assume_super_admin_role, get_account_id_by_name, is_mgmt_account


@command()
@option("--install/--uninstall", required=True)
def main(install: bool):
    if is_mgmt_account():
        # Assume super admin role in Log Archive Account
        LOGGER.debug("Running from Management Account")
        global_reader = True
        log_archive_account_id = get_account_id_by_name("Log Archive")
        session = assume_super_admin_role(log_archive_account_id, "CBS-Install")
        s3_client = session.client("s3")
        kwargs = dict(log_archive_account_id=log_archive_account_id)
    else:
        # We can assume we're in the Log Archive Account otherwise
        LOGGER.debug("Running from Log Archive Account")
        LOGGER.warning(
            "Cannot manage global reader roles from outside Management Account"
        )
        global_reader = False
        session = Session()
        s3_client = session.client("s3")
        kwargs = dict()

    # Load in partner's remote config
    remote_config = RemoteConfig.from_file(
        __package__,
        "remote_config.json",
        s3_client=s3_client,
        **kwargs,
    )

    try:
        # Get partner's replication configuration state
        state = loads(
            s3_client.get_object(
                Bucket=remote_config.config_bucket_name,
                Key=f"{remote_config.log_archive_account_id}/cbs_state.json",
            )["Body"].read()
        )
    except ClientError:
        LOGGER.debug("First install/uninstall - initializing empty state")
        state = {}

    tf_path = str(files(__package__).joinpath("terraform"))

    if global_reader:
        s3_client.download_file(
            Bucket=remote_config.config_bucket_name,
            Key=f"{remote_config.log_archive_account_id}/cbs.s3.tfbackend.json",
            Filename=tf_path + "/cbs.s3.tfbackend.json",
        )

    if install:
        state_change = cbs_install(
            session, s3_client, state, remote_config, tf_path, global_reader
        )
    else:
        state_change = cbs_uninstall(
            session, s3_client, state, remote_config, tf_path, global_reader
        )

    if state_change:
        s3_client.put_object(
            Bucket=remote_config.config_bucket_name,
            Key=f"{remote_config.log_archive_account_id}/cbs_state.json",
            Body=dumps(state, indent=2).encode(),
        )

    s3_client.upload_file(
        Filename=LOG_FILE_NAME,
        Bucket=remote_config.config_bucket_name,
        Key=f"{remote_config.log_archive_account_id}/{LOG_FILE_NAME}",
    )


if __name__ == "__main__":
    main()
