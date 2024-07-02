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

from inspect import getmodule, stack
from logging import INFO, WARNING, Logger, basicConfig, getLogger
from os import environ
from typing import Union

MESSAGE_FORMAT = "%(asctime)s %(name)s %(levelname)s: %(message)s"
DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"

PROJECT_NAME = environ.get("PROJECT_NAME", "logger")

is_configured = False
root_logger = getLogger()


def get_callers_name() -> str:
    """Get the name of the module calling the `get_logger` function."""
    current_stack = stack()[
        2
    ]  # Get caller's stack frame, [_get_callers_name, get_logger, caller, ...]
    module_name = getmodule(current_stack[0]).__name__

    if (
        module_name == "__main__"
    ):  # Call main process after the project instead of `__main__`
        return PROJECT_NAME
    return module_name


def get_logger() -> Logger:
    """Get logger named after the calling module."""
    name = get_callers_name()

    return getLogger(name)


def configure_logging() -> None:
    """Configure the logging setting."""
    try:
        log_level = environ.get("LOG_LEVEL", "INFO").upper()
        basicConfig(format=MESSAGE_FORMAT, datefmt=DATE_FORMAT, level=log_level)

    except ValueError:  # ValueError: Unknown level
        basicConfig(
            format=MESSAGE_FORMAT, datefmt=DATE_FORMAT, level=INFO
        )  # Fallback config


def change_log_level(logger: Union[Logger, str], level: int = WARNING) -> None:
    """Set the log level for the logger."""
    if isinstance(logger, str):  # Get the logger if the name is passed
        logger = getLogger(logger)

    logger.setLevel(level)


if not is_configured:
    configure_logging()
    is_configured = True
