from datetime import datetime, timezone
from json import load
from pathlib import Path
from subprocess import CompletedProcess, run
from typing import Callable, Union

from colors import color

from .logging import LOGGER


def _input(message: str, *_, fg: str = "yellow", style: str = "bold", **__):
    """Function wrapper to handle common user input needs."""

    def inner(func: Callable):
        LOGGER.debug(message)
        while True:
            user_input = input(color(message, fg=fg, style=style)).strip()
            if (result := func(user_input)) is not None:
                return result
            LOGGER.error("Invalid input: %s", user_input)

    return inner


def boolean_prompt(prompt: str) -> bool:
    """CLI input for y/n question."""

    @_input(f"{prompt} (y/n): ")
    def inner(user_input: str) -> bool:
        if user_input in {"y", "n"}:
            LOGGER.debug("User entered: %s", user_input)
            return user_input == "y"

    return inner


def account_input(account_name: str, limit: int) -> int:
    """CLI input for account selection."""

    @_input(f"Enter number associated with your {account_name} account: ")
    def inner(user_input: str) -> int:
        if user_input.isnumeric() and 0 < int(user_input) <= limit:
            LOGGER.debug("Account selected: %s", user_input)
            return int(user_input)

    return inner


def bucket_input(limit: int) -> list[int]:
    """CLI input for S3 buckets selection."""

    @_input(
        "Enter comma-separated list of bucket numbers you want to install CBS on (or press Enter to skip): "
    )
    def inner(user_input: str) -> list[str]:
        input_list = [i.strip() for i in user_input.split(",") if i]
        if not input_list:
            LOGGER.debug("Skipping replication rule installation")
            return input_list
        if bucket_selection := [
            int(i) for i in input_list if i.isnumeric() and 0 < int(i) <= limit
        ]:
            LOGGER.debug("Buckets selected: %s", bucket_selection)
            return bucket_selection

    return inner


def date_range_input() -> tuple[datetime]:
    """CLI input for S3 batch replication"""

    def _validate_date(date_string: str) -> Union[datetime, None]:
        try:
            date = datetime.strptime(date_string, "%Y-%m-%d").astimezone(timezone.utc)
            LOGGER.debug("Date entered: %s", date.date())
            return date
        except ValueError:
            return None

    @_input("Enter start date (UTC date in the form of YYYY-MM-DD): ")
    def _start_date(user_input: str) -> Union[datetime, None]:
        return _validate_date(user_input)

    @_input("Enter end date (UTC date in the form of YYYY-MM-DD): ")
    def _end_date(user_input: str) -> Union[datetime, None]:
        return _validate_date(user_input)

    return _start_date, _end_date


def run_cmd(cmd: str) -> CompletedProcess:
    """Run command."""
    return run(cmd.split(" "))


def load_json_file(path: Path) -> dict:
    """Load a json file as a dict object."""
    with path.open() as json:
        return load(json)
