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

from dataclasses import asdict, dataclass, field, replace
from importlib import import_module
from logging import getLogger
from os import environ
from pathlib import Path
from sys import modules
from types import ModuleType

from boto3 import Session
from core.enums import EnvironmentVariableKeys
from core.metadata import MetadataObject
from core.metadata.config import MetadataCollectorConfig
from core.utils.paginate import paginate
from yaml import safe_load

from scooper.core.config import ScooperConfig
from scooper.core.lambda_layer import METADATA_SOURCES
from scooper.core.utils.logger import get_logger

# Tasks aren't retried, so their first receive is also their last
_RECEIVE_COUNT = 1

# Stand in for what core.metadata.task imports from its collector container, minus the logger's CloudWatch metrics
_logging_config = ModuleType("metadata_sources.logging_config")
_logging_config.get_logger = getLogger
modules[_logging_config.__name__] = _logging_config
environ[EnvironmentVariableKeys.SQS_MAX_RECEIVE_COUNT] = str(_RECEIVE_COUNT)

from core.metadata.task import MetadataTask

_logger = get_logger()

# Object keys (relative to an account and region's metadata prefix) and their metadata objects
type MetadataObjects = list[tuple[str, MetadataObject]]


@dataclass(frozen=True, kw_only=True)
class _MetadataTask(MetadataTask):
    """`MetadataTask` that collects with the given session, instead of assuming the reader role in its account."""

    session: Session = field(repr=False)

    def get_session(self, collector_name: str) -> Session:
        return self.session


def _get_enabled_regions(session: Session) -> set[str]:
    """Get the regions enabled in the session's account, or every EC2 region if they can't be listed."""
    account_client = session.client("account")

    try:
        regions = paginate(
            client=account_client,
            operation="list_regions",
            array="Regions",
            RegionOptStatusContains=["ENABLED", "ENABLED_BY_DEFAULT"],
        )
    except account_client.exceptions.AccessDeniedException:
        return set(session.get_available_regions("ec2"))

    return {region["RegionName"] for region in regions}


def _get_regional_session(session: Session, region: str) -> Session:
    """Get a copy of `session` that targets `region`."""
    credentials = session.get_credentials().get_frozen_credentials()

    return Session(
        aws_access_key_id=credentials.access_key,
        aws_secret_access_key=credentials.secret_key,
        aws_session_token=credentials.token,
        region_name=region,
    )


def collect_metadata(scooper_config: ScooperConfig) -> MetadataObjects:
    """Collect metadata from the layer's metadata sources."""
    is_org_level = scooper_config.is_org_level()
    account_sessions = (
        scooper_config.all_account_sessions
        if is_org_level
        else {scooper_config.account_id: Session()}
    )
    metadata_objects = []

    for source in METADATA_SOURCES:
        collector = f"metadata_sources.{source}"
        collector_module = import_module(collector)
        service_to_collector = collector_module.service_to_collector
        config = MetadataCollectorConfig(
            **safe_load(
                Path(collector_module.__file__).with_name("config.yaml").read_bytes()
            )
        )

        if config.management_account_only:
            if not is_org_level:
                continue
            sessions = {
                scooper_config.account_id: account_sessions[scooper_config.account_id]
            }
        else:
            sessions = account_sessions

        for account_id, session in sessions.items():
            if config.region:
                regions = {config.region}
            else:
                supported_regions = {
                    region
                    for service in service_to_collector
                    for region in session.get_available_regions(service)
                }
                regions = _get_enabled_regions(session) & supported_regions

            for region in sorted(regions):
                metadata_task = _MetadataTask(
                    **asdict(replace(config, region=region)),
                    organization_id=scooper_config.org_id if is_org_level else None,
                    account_id=account_id,
                    collector=collector,
                    cbs_id=scooper_config.identifier,
                    bucket_name=None,  # Set when publishing, once the bucket is deployed
                    session=_get_regional_session(session, region),
                )

                # A dry run returns the metadata object instead of putting it, which for single-service sources is keyed by the source
                if isinstance(
                    metadata_object := metadata_task.run(
                        receive_count=_RECEIVE_COUNT, dry_run=True
                    ),
                    MetadataObject,
                ):
                    metadata_objects.append((f"{source}.json", metadata_object))

    return metadata_objects


def publish_metadata(metadata_objects: MetadataObjects, bucket_name: str) -> None:
    """Put metadata objects in `bucket_name`."""
    _logger.info(
        "Publishing %d metadata objects to '%s'...", len(metadata_objects), bucket_name
    )

    for key, metadata_object in metadata_objects:
        metadata_task = replace(metadata_object.metadata_task, bucket_name=bucket_name)
        replace(metadata_object, metadata_task=metadata_task).put(key)
