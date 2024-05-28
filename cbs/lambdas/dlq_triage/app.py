from aws_lambda_powertools.utilities.data_classes import SQSEvent, event_source
from aws_lambda_powertools.utilities.typing import LambdaContext
from triage import DLQTriage

dlq_triage = DLQTriage()


@event_source(data_class=SQSEvent)
def lambda_handler(event: SQSEvent, _: LambdaContext) -> None:
    for record in event.records:
        dlq_triage.triage(record)
