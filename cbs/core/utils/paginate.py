from logging import Logger

from botocore.client import BaseClient


def paginate(client: BaseClient, command: str, array: str, logger: Logger, **kwargs):
    """Paginate given boto3 command."""
    elements = []
    paginator = client.get_paginator(command)

    try:
        for page in paginator.paginate(**kwargs):
            elements.extend(page.get(array, []))
    except Exception:
        logger.exception("Pagination failed")

    return elements
