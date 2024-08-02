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

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from json import loads

from boto3 import Session, client

from scooper.utils.enum import paginate
from scooper.utils.io import write_dict_to_s3
from scooper.utils.logger import get_logger

NUM_WORKERS = 2  # We get throttled beyond this :(

_logger = get_logger()


@dataclass
class TimeRange:
    start: datetime
    end: datetime


def get_cloudtrail_events(start_time: datetime, end_time: datetime) -> list[dict]:
    """Get CloudTrail events between `start_time` and `end_time` in current account and region."""
    cloudtrail_client = client("cloudtrail")

    time_interval = (end_time - start_time) / NUM_WORKERS
    periods: list[TimeRange] = []
    period_start = start_time

    while period_start < end_time:
        period_end = min(period_start + time_interval, end_time)
        periods.append(TimeRange(start=period_start, end=period_end))
        period_start = period_end

    cloudtrail_scoops = []

    with ThreadPoolExecutor(max_workers=NUM_WORKERS) as executor:
        futures = []
        for period in periods:
            futures.append(
                executor.submit(
                    paginate,
                    cloudtrail_client,
                    "lookup_events",
                    "Events",
                    StartTime=period.start,
                    EndTime=period.end,
                )
            )
        for future in as_completed(futures):
            cloudtrail_scoops.extend(future.result())

    return cloudtrail_scoops


class CloudTrailDump:
    def __init__(self, data: list[dict]) -> None:
        self._data = data

    def __len__(self) -> int:
        return len(self._data)

    def partition(self) -> dict[datetime, list[dict]]:
        """Partition CloudTrail data by hour the events occurred."""
        partitions: dict[datetime, list[dict]] = {}

        for datum in self._data:
            event: dict = loads(datum["CloudTrailEvent"])
            event_time: datetime = datum["EventTime"]
            # Round time down to nearest hour
            event_time = event_time.replace(minute=0, second=0, microsecond=0)
            # Group events by hour
            if event_time in partitions:
                partitions[event_time].append(event)
            else:
                partitions[event_time] = [event]

        return partitions


def write_cloudtrail_scoop_to_s3(
    start_time: datetime, end_time: datetime, bucket_name: str
) -> None:
    """Write historical CloudTrail data to given `bucket_name`."""
    session = Session()
    s3_client = session.client("s3")
    sts_client = session.client("sts")
    account_id = sts_client.get_caller_identity()["Account"]
    region = session.region_name

    _logger.info(
        f"Getting CloudTrail data between '{start_time}' and '{end_time}' in account '{account_id}' and region '{region}'..."
    )
    data = get_cloudtrail_events(start_time, end_time)
    partitions = CloudTrailDump(data).partition()
    cloudtrail_prefix = f"scooper/CloudTrail/{account_id}/{region}"

    for datetime_, partition in partitions.items():
        write_dict_to_s3(
            obj=partition,
            bucket_name=bucket_name,
            object_key=f"{cloudtrail_prefix}/{datetime_.strftime('%Y/%m/%d')}/CloudTrail_{datetime_.isoformat()}.json",
            s3_client=s3_client,
        )
