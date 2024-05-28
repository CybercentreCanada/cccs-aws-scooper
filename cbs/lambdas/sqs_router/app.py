from json import loads
from typing import Any

from aws_lambda_powertools.utilities.data_classes import SQSEvent, event_source
from aws_lambda_powertools.utilities.typing import LambdaContext
from route import SQSRouter

router = SQSRouter()


@event_source(data_class=SQSEvent)
def lambda_handler(event: SQSEvent, _: LambdaContext) -> None:
    """SQS Router Lambda Handler for SQS events."""
    for record in event.records:
        message: dict[str, Any] = loads(record.body)
        router.route(message)
