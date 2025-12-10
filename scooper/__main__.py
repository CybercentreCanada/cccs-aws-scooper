"""
The resources contained herein are © His Majesty in Right of Canada as Represented by the Minister of National Defence.

FOR OFFICIAL USE All Rights Reserved. All intellectual property rights subsisting in the resources contained herein are,
and remain the property of the Government of Canada. No part of the resources contained herein may be reproduced or disseminated
(including by transmission, publication, modification, storage, or otherwise), in any form or any means, without the written
permission of the Communications Security Establishment (CSE), except in accordance with the provisions of the Copyright Act, such
as fair dealing for the purpose of research, private study, education, parody or satire. Applications for such permission shall be
made to CSE.

The resources contained herein are provided “as is”, without warranty or representation of any kind by CSE, whether express or
implied, including but not limited to the warranties of merchantability, fitness for a particular purpose and noninfringement.
In no event shall CSE be liable for any loss, liability, damage or cost that may be suffered or incurred at any time arising
from the provision of the resources contained herein including, but not limited to, loss of data or interruption of business.

CSE is under no obligation to provide support to recipients of the resources contained herein.

This licence is governed by the laws of the province of Ontario and the applicable laws of Canada. Legal proceedings related to
this licence may only be brought in the courts of Ontario or the Federal Court of Canada.

Notwithstanding the foregoing, third party components included herein are subject to the ownership and licensing provisions
noted in the files associated with those components.
"""

from dataclasses import asdict, is_dataclass
from pathlib import Path

from boto3 import Session, client
from botocore.config import Config as BotoConfig
from click import group

from scooper.configure_logging import deploy
from scooper.core.cli import options
from scooper.core.cli.callbacks import S3LifecycleRule
from scooper.core.config import DeploymentConfig, ScooperConfig
from scooper.core.lambda_layer import CBS_COMMON_LAMBDA_LAYER_VERSION_ARN, LambdaLayer
from scooper.core.utils.io import date_range_input, write_dict_to_file
from scooper.core.utils.logger import get_logger
from scooper.core.utils.s3 import is_bucket_writable
from scooper.incident_response.cloudtrail import write_cloudtrail_scoop_to_s3
from scooper.log_sources.cloudtrail import CloudTrail
from scooper.log_sources.cloudwatch import CloudWatch
from scooper.log_sources.config import Config

LambdaLayer.import_layer(CBS_COMMON_LAMBDA_LAYER_VERSION_ARN, "cbs_common")

from cbs_common.aws.iam_metadata import IAMMetadata
from cbs_common.aws.organization_metadata import OrganizationMetadata
from cbs_common.aws.sso_metadata import SSOMetadata

_logger = get_logger()


@group(invoke_without_command=True)
@options.cloudtrail_scoop
@options.configure_logging
@options.destroy
@options.level
@options.lifecycle_rules
@options.role_name
@options.standalone
def main(
    cloudtrail_scoop: bool,
    configure_logging: bool,
    destroy: bool,
    level: str,
    lifecycle_rules: list[S3LifecycleRule],
    role_name: str,
    standalone: bool,
) -> None:
    """Main entry point for the Scooper CLI."""
    deployment_config = DeploymentConfig(
        level=level,
        cross_account_role_name=role_name,
        lifecycle_rules=lifecycle_rules,
        standalone=standalone,
    )

    if (scooper_config := ScooperConfig.from_ssm()) is None:
        # No existing config in SSM, create a new one
        scooper_config = ScooperConfig(deployment_config)
    else:
        # Update existing config with any CLI arguments provided
        scooper_config.deployment_config = deployment_config

    # Confirm that the deployment level and account are correct
    scooper_config.confirm_account()
    # Keep SSM up to date with any changes made via CLI arguments
    scooper_config.write_to_ssm()

    cloudtrail = CloudTrail(scooper_config)
    cloudwatch = CloudWatch(scooper_config)
    config = Config(scooper_config)
    iam_credential_reports = (
        [
            IAMMetadata(account_id, session.client("iam")).get_report()
            for account_id, session in scooper_config.all_account_sessions.items()
        ]
        if scooper_config.is_org_level()
        else IAMMetadata(scooper_config.account_id, client("iam")).get_report()
    )

    logging_reports = {
        "cloudtrail": cloudtrail.report,
        "cloudwatch": cloudwatch.report,
        "config": config.report,
        "iam_metadata": iam_credential_reports,
    }

    if scooper_config.is_org_level():
        logging_reports["organization_metadata"] = OrganizationMetadata().get_report()
        logging_reports["sso_metadata"] = SSOMetadata().get_report()

    for service, logging_report in logging_reports.items():
        write_dict_to_file(
            obj=(
                asdict(logging_report)
                if is_dataclass(logging_report)
                else logging_report
            ),
            path=Path(f"out/{service}.json"),
        )

    if configure_logging or destroy:
        deploy(
            logging_reports=logging_reports,
            destroy=destroy,
            lifecycle_rules=lifecycle_rules,
            scooper_config=scooper_config,
        )

    if cloudtrail_scoop:
        _logger.info("Starting CloudTrail Scoop...")
        start_time, end_time = date_range_input()
        bucket_name = input(
            "Enter name of bucket you want to dump historical logs to: "
        ).strip()

        if is_bucket_writable(bucket_name):
            session = Session()
            config = BotoConfig(retries={"mode": "adaptive", "max_attempts": 16})
            for region in session.get_available_regions("cloudtrail"):
                write_cloudtrail_scoop_to_s3(
                    start_time=start_time,
                    end_time=end_time,
                    account_id=scooper_config.account_id,
                    region=region,
                    bucket_name=bucket_name,
                    cloudtrail_client=session.client(
                        "cloudtrail", region_name=region, config=config
                    ),
                )
        else:
            raise SystemExit(f"Can't write to '{bucket_name}'")


if __name__ == "__main__":
    main()
