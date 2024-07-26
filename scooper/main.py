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
from subprocess import run

import aws_cdk as cdk
import click

from scooper.cdk.scooper.scooper_stack import Scooper
from scooper.config import ScooperConfig
from scooper.incident_response.cloudtrail import write_cloudtrail_scoop_to_s3
from scooper.sources import custom, native
from scooper.sources.custom.lambda_layer import LambdaLayer
from scooper.sources.report import LoggingEnumerationReport, LoggingReport
from scooper.utils.cli import S3LifecycleRule, lifecycle_tokenizer
from scooper.utils.io import date_range_input, write_dict_to_file, write_dict_to_s3
from scooper.utils.logger import get_logger

LambdaLayer().import_layer(
    "arn:aws:lambda:ca-central-1:519133912246:layer:CBSCommonLayer:4", "cbs_common"
)
from cbs_common.aws.sso_metadata import SSOMetadata

_logger = get_logger()

level = click.option(
    "--level",
    "--l",
    help="Which level of enumeration to perform",
    type=click.Choice(["account", "org"]),
    default="account",
)
region = click.option(
    "--region",
    "--r",
    help="Which region to enumerate",
    default="ca-central-1",
)
role_name = click.option(
    "--role-name",
    help="Name of role with organization account access",
    default="OrganizationAccountAccessRole",
)
cloudtrail_scoop = click.option(
    "--cloudtrail-scoop",
    is_flag=True,
    show_default=True,
    default=False,
    help="Whether to perform historical CloudTrail data collection",
    required=False,
)
destroy = click.option(
    "--destroy",
    is_flag=True,
    show_default=True,
    default=False,
    help="Destroy CloudFormation Resources created by Scooper",
    required=False,
)
lifecycle_rules = click.option(
    "--lifecycle-rules",
    help="Specify comma-separated S3 storage class(es) and duration(s) in days of lifecycle protection for Scooper S3 bucket",
    type=str,
    required=False,
    callback=lifecycle_tokenizer,
)


@click.group(invoke_without_command=True)
@level
@region
@role_name
@cloudtrail_scoop
@click.pass_context
def main(
    ctx: click.core.Context,
    level: str,
    region: str,
    role_name: str,
    cloudtrail_scoop: bool,
) -> None:
    scooper_config = ScooperConfig(level, region)
    ctx.obj = dict()
    ctx.obj["scooper_config"] = scooper_config

    cloudtrail = native.CloudTrail(level)
    cloudwatch = native.CloudWatch(level, role_name, scooper_config)
    config = native.Config(level)

    reports = {
        "cloudtrail": cloudtrail.report,
        "cloudwatch": cloudwatch.report,
        "config": config.report,
    }

    if level == "org":
        organization_metadata = custom.OrganizationMetadata(level)
        sso_metadata = SSOMetadata()
        reports["organization_metadata"] = organization_metadata.report
        reports["sso_metadata"] = sso_metadata.get_report()

    for title, report in reports.items():
        write_dict_to_file(
            asdict(report) if is_dataclass(report) else report,
            Path(f"scooper/out/{title}.json"),
        )

    ctx.obj["reports"] = reports

    if cloudtrail_scoop:
        _logger.info("Starting CloudTrail Scoop...")
        start_time, end_time = date_range_input()
        bucket_name = input(
            "Enter name of bucket you want to dump historical logs to: "
        ).strip()
        write_cloudtrail_scoop_to_s3(start_time, end_time, bucket_name)


@main.command()
@destroy
@lifecycle_rules
@click.pass_context
def configure_logging(
    ctx: click.core.Context,
    destroy: bool,
    lifecycle_rules: list[S3LifecycleRule],
) -> None:
    app = cdk.App()
    stack_name = "Scooper"
    Scooper(
        app,
        stack_name,
        scooper_config=ctx.obj["scooper_config"],
        logging_enumeration_report=LoggingEnumerationReport(
            [
                report
                for report in ctx.obj["reports"].values()
                if isinstance(report, LoggingReport)
            ]
        ),
        env=cdk.Environment(
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

    stack_outputs = Path("scooper/out/stack_outputs.json")
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
        exit(1)

    if ctx.obj["scooper_config"].global_config.level == "org":
        _logger.info("Publishing %s metadata...", stack_name)
        for name, report in ctx.obj["reports"].items():
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
