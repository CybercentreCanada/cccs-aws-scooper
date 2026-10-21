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

from os import getenv
from pathlib import Path
from subprocess import run

from aws_cdk import App, Environment
from boto3 import client

from scooper.cdk.stacks.scooper import Scooper
from scooper.core.cli.callbacks import S3LifecycleRule
from scooper.core.config import IAMRA, OutputConfig, ScooperConfig
from scooper.core.constants import SCOOPER
from scooper.core.utils.io import write_dict_to_file, write_dict_to_s3
from scooper.core.utils.logger import get_logger
from scooper.log_sources.report import LoggingReport
from scooper.metadata_sources import MetadataObjects, publish_metadata

_logger = get_logger()


def deploy(
    logging_reports: dict[str, LoggingReport],
    metadata_objects: MetadataObjects,
    destroy: bool,
    lifecycle_rules: list[S3LifecycleRule],
    scooper_config: ScooperConfig,
) -> None:
    """Deploy or destroy the Scooper infrastructure using AWS CDK."""
    app = App()
    stack_name = SCOOPER

    Scooper(
        app,
        stack_name,
        scooper_config=scooper_config,
        logging_reports=list(logging_reports.values()),
        env=Environment(
            account=getenv("CDK_DEFAULT_ACCOUNT"), region=getenv("CDK_DEFAULT_REGION")
        ),
        termination_protection=True,
        lifecycle_rules=lifecycle_rules,
        tags={"Owner": SCOOPER},
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

    _logger.info("Deploying %s stack...", stack_name)

    if run(["cdk", "deploy", "--app", app.synth().directory]).returncode:
        _logger.critical("%s deploy failed or was cancelled!", stack_name)
        raise SystemExit

    _logger.info("Reading %s outputs...", stack_name)
    # Read outputs from CloudFormation rather than a local file that could be stale or tampered with
    stack = client("cloudformation").describe_stacks(StackName=stack_name)["Stacks"][0]
    outputs = {
        output["OutputKey"]: output["OutputValue"] for output in stack["Outputs"]
    }
    bucket_name = outputs["BucketName"]

    if scooper_config.deployment_config.standalone:
        iamra = IAMRA(
            reader_role_arn=outputs["ReaderRoleArn"],
            trust_anchor_arn=outputs["TrustAnchorArn"],
            profile_arn=outputs["ProfileArn"],
            certificate_path=str(scooper_config.leaf_certificate.certificate_path),
            private_key_path=str(scooper_config.leaf_certificate.private_key_path),
        )
        output_config = OutputConfig(
            identifier=scooper_config.identifier,
            account_id=scooper_config.account_id,
            region=outputs["Region"],
            bucket_name=bucket_name,
            queue_url=outputs["QueueUrl"],
            scooper_custom_query_role_name=outputs["ScooperCustomQueryRoleName"],
            iamra=iamra,
        )
        output_config.model_dump_yaml()

    object_key_prefixes = [
        logging_report.service for logging_report in logging_reports.values()
    ]
    write_dict_to_file(
        obj={"bucket_name": bucket_name, "object_key_prefixes": object_key_prefixes},
        path=Path("out/logging.json"),
    )

    if scooper_config.is_org_level():
        _logger.info("Publishing %s metadata...", stack_name)
        for name, logging_report in logging_reports.items():
            write_dict_to_s3(
                logging_report.details,
                bucket_name,
                f"scooper/{name}.json",
            )
        publish_metadata(metadata_objects, bucket_name)
