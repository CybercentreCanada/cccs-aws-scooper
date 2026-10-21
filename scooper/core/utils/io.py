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

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from json import JSONEncoder, dump, dumps
from pathlib import Path
from typing import Any

from boto3 import client
from core.utils.paginate import paginate

from scooper.core.utils.logger import get_logger

S3_CLIENT = client("s3")
_logger = get_logger()


class ScooperEncoder(JSONEncoder):
    def default(self, obj) -> Any:
        if isinstance(obj, datetime):
            return obj.isoformat()
        elif isinstance(obj, set):
            return list(obj)
        return JSONEncoder.default(self, obj)


def write_dict_to_s3(obj: dict, bucket_name: str, object_key: str) -> None:
    obj_as_json = dumps(obj, cls=ScooperEncoder, indent=2).encode()
    S3_CLIENT.put_object(Body=obj_as_json, Bucket=bucket_name, Key=object_key)

    _logger.info("Object written to s3://%s/%s", bucket_name, object_key)


def write_dict_to_file(obj: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w") as out:
        dump(obj, out, cls=ScooperEncoder, indent=2)

    _logger.info("Object written to %s", path)


def _input(message: str, *_, **__) -> Callable:
    """Function wrapper to handle common user input needs."""

    def inner(func: Callable) -> Any:
        _logger.debug(message)
        while True:
            user_input = input(message).strip()
            if (result := func(user_input)) is not None:
                return result
            _logger.error("Invalid input: %s", user_input)

    return inner


def boolean_prompt(prompt: str) -> bool:
    """CLI input for y/n question."""

    @_input(f"{prompt} (y/n): ")
    def inner(user_input: str) -> bool | None:
        if user_input in {"y", "n"}:
            _logger.debug("User entered: %s", user_input)
            return user_input == "y"

    return inner


def account_input(limit: int) -> int:
    """CLI input for account selection."""

    @_input("Enter number associated with the account you want: ")
    def inner(user_input: str) -> int | None:
        if user_input.isnumeric() and 0 < int(user_input) <= limit:
            _logger.debug("Account selected: %s", user_input)
            return int(user_input)

    return inner


def account_selection() -> str:
    accounts_alphabetical = sorted(
        paginate(
            client=client("organizations"),
            operation="list_accounts",
            array="Accounts",
        ),
        key=lambda account: account["Name"],
    )
    accounts_indexed = {
        index: (account["Name"], account["Id"])
        for index, account in enumerate(accounts_alphabetical, start=1)
    }

    _logger.info("Accounts:")
    for index, account_name_and_id in accounts_indexed.items():
        account_name, account_id = account_name_and_id
        _logger.info("[%s]: %s (%s)", index, account_name, account_id)

    account_selection = account_input(limit=len(accounts_indexed))

    return accounts_indexed[account_selection][1]


def display_buckets() -> dict[int, str]:
    """Display all buckets and return enumerated dictionary of bucket names."""
    buckets_alphabetical = sorted(
        client("s3").list_buckets()["Buckets"], key=lambda bucket: bucket["Name"]
    )
    buckets_indexed = {
        index: bucket["Name"]
        for index, bucket in enumerate(buckets_alphabetical, start=1)
    }

    _logger.info("Buckets:")
    for index, bucket_name in buckets_indexed.items():
        _logger.info("[%s]: %s", index, bucket_name)

    return buckets_indexed


def bucket_input(limit: int) -> list[int]:
    """CLI input for S3 buckets selection."""

    @_input(
        "Enter comma-separated list of bucket numbers you want to integrate with standalone (or 'all' for all buckets or press Enter to skip): "
    )
    def inner(user_input: str) -> list[int] | None:
        if user_input.lower() == "all":
            _logger.debug("All buckets selected")
            return list(range(1, limit + 1))

        bucket_indices = [index.strip() for index in user_input.split(",") if index]

        if not bucket_indices:
            _logger.debug("Skipping supplementary bucket selection")
            return bucket_indices

        if selected_bucket_indices := [
            int(index)
            for index in bucket_indices
            if index.isnumeric() and 0 < int(index) <= limit
        ]:
            _logger.debug("Buckets selected: %s", selected_bucket_indices)
            return selected_bucket_indices

    return inner


def date_range_input() -> tuple[datetime, datetime]:
    """CLI input for date range."""

    def _validate_date(date_string: str) -> datetime | None:
        try:
            date = datetime.strptime(date_string, "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=UTC
            )
            if date < (datetime.now(tz=UTC) - timedelta(days=90)):
                _logger.error("Date must be within last 90 days")
                return None
            _logger.debug("Date entered: %s", date.date())
            return date
        except ValueError:
            return None

    @_input("Enter start date (UTC date in the form of YYYY-MM-DD hh:mm:ss): ")
    def _start_date(user_input: str) -> datetime:
        return _validate_date(user_input)

    @_input("Enter end date (UTC date in the form of YYYY-MM-DD hh:mm:ss): ")
    def _end_date(user_input: str) -> datetime:
        return _validate_date(user_input)

    return _start_date, _end_date
