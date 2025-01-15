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
from json import load
from os import getenv
from pathlib import Path
from string import Template
from subprocess import run

from aws_cdk import App, Environment
from click import group

from scooper.cdk.scooper.scooper_stack import Scooper
from scooper.core.cli import options
from scooper.core.cli.callbacks import S3LifecycleRule
from scooper.core.config import ScooperConfig
from scooper.core.constants import ORG, SCOOPER
from scooper.core.utils.io import date_range_input, write_dict_to_file, write_dict_to_s3
from scooper.core.utils.logger import get_logger
from scooper.incident_response.cloudtrail import write_cloudtrail_scoop_to_s3
from scooper.sources import custom, native
from scooper.sources.custom.lambda_layer import LambdaLayer
from scooper.sources.report import LoggingReport

LambdaLayer.import_layer(
    "arn:aws:lambda:ca-central-1:519133912246:layer:CBSCommonLayer:21", "cbs_common"
)
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
def main(
    cloudtrail_scoop: bool,
    configure_logging: bool,
    destroy: bool,
    level: str,
    lifecycle_rules: list[S3LifecycleRule],
    role_name: str,
) -> None:
    scooper_config = ScooperConfig(level, role_name)

    cloudtrail = native.CloudTrail(level)
    cloudwatch = native.CloudWatch(level, scooper_config)
    config = native.Config(level)
    iam = custom.IAMMetadata(
        level,
        organizational_account_access_role_template=Template(
            f"arn:aws:iam::$account:role/{role_name}"
        ),
    )

    reports = {
        "cloudtrail": cloudtrail.report,
        "cloudwatch": cloudwatch.report,
        "config": config.report,
        "iam_metadata": iam.get_report(),
    }

    if level == ORG:
        reports["organization_metadata"] = OrganizationMetadata().get_report()
        reports["sso_metadata"] = SSOMetadata().get_report()

    for title, report in reports.items():
        write_dict_to_file(
            asdict(report) if is_dataclass(report) else report,
            Path(f"out/{title}.json"),
        )

    if configure_logging or destroy:
        _configure_logging(
            scooper_config=scooper_config,
            reports=reports,
            destroy=destroy,
            lifecycle_rules=lifecycle_rules,
        )

    if cloudtrail_scoop:
        _logger.info("Starting CloudTrail Scoop...")
        start_time, end_time = date_range_input()
        bucket_name = input(
            "Enter name of bucket you want to dump historical logs to: "
        ).strip()
        write_cloudtrail_scoop_to_s3(start_time, end_time, bucket_name)


def _configure_logging(
    scooper_config: ScooperConfig,
    reports: dict[str, LoggingReport],
    destroy: bool,
    lifecycle_rules: list[S3LifecycleRule],
) -> None:
    app = App()
    stack_name = SCOOPER

    Scooper(
        app,
        stack_name,
        scooper_config=scooper_config,
        logging_reports=[
            report for report in reports.values() if isinstance(report, LoggingReport)
        ],
        env=Environment(
            account=getenv("CDK_DEFAULT_ACCOUNT"), region=getenv("CDK_DEFAULT_REGION")
        ),
        termination_protection=True,
        lifecycle_rules=lifecycle_rules,
    )

    if destroy:
        run(
            [
                "aws",
                "cloudformation",
                "update-termination-protection",
                "--stack-name",
                stack_name,
                "--no-enable-termination-protection",
            ]
        )
        run(
            [
                "cdk",
                "destroy",
                "--app",
                app.synth().directory,
            ]
        )
        return

    stack_outputs = Path("out/stack_outputs.json")
    _logger.info("Deploying %s stack...", stack_name)
    run(
        [
            "cdk",
            "deploy",
            "--app",
            app.synth().directory,
            f"--outputs-file={stack_outputs}",
        ]
    )

    with stack_outputs.open("r") as f:
        outputs = load(f)

    if outputs:
        _logger.info("Reading %s outputs...", stack_name)
        bucket_name = outputs[stack_name]["BucketName"]
    else:
        _logger.critical("%s deploy failed!", stack_name)
        raise SystemExit

    object_key_prefixes = [
        report.service
        for report in reports.values()
        if isinstance(report, LoggingReport) and Scooper.check_logging(report)
    ]
    write_dict_to_file(
        obj={"bucket_name": bucket_name, "object_key_prefixes": object_key_prefixes},
        path=Path("out/logging.json"),
    )

    if scooper_config.level == ORG:
        _logger.info("Publishing %s metadata...", stack_name)
        for name, report in reports.items():
            if isinstance(report, LoggingReport):
                write_dict_to_s3(
                    report.details,
                    bucket_name,
                    f"scooper/{name}.json",
                )
            else:
                write_dict_to_s3(
                    report,
                    bucket_name,
                    f"scooper/{name}.json",
                )


if __name__ == "__main__":
    main()
