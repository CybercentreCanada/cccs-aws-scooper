from aws_lambda_powertools.utilities.data_classes import EventBridgeEvent, event_source
from aws_lambda_powertools.utilities.typing import LambdaContext
from exceptions import TransportError
from transport import Transport

transport = Transport()


@event_source(data_class=EventBridgeEvent)
def lambda_handler(event: EventBridgeEvent, context: LambdaContext) -> None:
    """Transport Lambda Handler for EventBridge events."""
    try:
        transport.process_s3_event(event, context)
    except TransportError as e:
        if e.object_key and e.workload:
            transport.logger.warning(
                "'%s' with workload type '%s' failed to process: '%s'",
                e.object_key,
                e.workload,
                e,
            )
        elif e.object_key and not e.workload:
            transport.logger.warning(
                "'%s' is unsupported: '%s'",
                e.object_key,
                e,
            )
        else:
            raise
