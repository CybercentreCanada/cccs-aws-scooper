from alarm_formatter import AlarmFormatter
from aws_lambda_powertools.utilities.data_classes import SNSEvent, event_source
from aws_lambda_powertools.utilities.typing import LambdaContext


@event_source(data_class=SNSEvent)
def lambda_handler(event: SNSEvent, context: LambdaContext) -> None:
    cw_alarm_formatter = AlarmFormatter()
    cw_alarm_formatter.format(event)
