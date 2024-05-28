from datetime import datetime, timezone
from os import getenv
from re import search

from aws_lambda_powertools import Logger, Metrics
from aws_lambda_powertools.metrics import MetricUnit
from aws_lambda_powertools.utilities.data_classes.sqs_event import SQSRecord
from boto3 import client
from boto3.dynamodb.types import TypeDeserializer, TypeSerializer
from core import constants
from dateutil.parser import parse
from sanitize import ObjectKeySanitizer

metrics = Metrics(service=getenv("AWS_LAMBDA_FUNCTION_NAME"), namespace="CBS")


class DLQTriage:
    def __init__(self) -> None:
        self._logger = None
        self.object_key_sanitizer = ObjectKeySanitizer()
        self.dynamodb_client = client("dynamodb")
        self.sns_client = client("sns")
        self._unknown_workloads_table_name = None
        self._unknown_workloads_topic_arn = None

    @property
    def logger(self) -> Logger:
        if self._logger is None:
            self._logger = Logger(
                service=getenv("AWS_LAMBDA_FUNCTION_NAME"),
                datefmt="%Y-%m-%dT%H:%M:%S.%f",
                use_datetime_directive=True,
                utc=True,
            )
        return self._logger

    @property
    def unknown_workloads_table_name(self) -> str | None:
        if self._unknown_workloads_table_name is None:
            self._unknown_workloads_table_name = getenv("UNKNOWN_WORKLOADS_TABLE_NAME")
        return self._unknown_workloads_table_name

    @property
    def unknown_workloads_topic_arn(self) -> str | None:
        if self._unknown_workloads_topic_arn is None:
            self._unknown_workloads_topic_arn = getenv("UNKNOWN_WORKLOADS_TOPIC_ARN")
        return self._unknown_workloads_topic_arn

    @metrics.log_metrics
    def triage(self, record: SQSRecord) -> None:
        try:
            body = record.json_body
            cbs_id = body["cbs_id"]
            accelerator = body["accelerator"]
            object_key = body["object_key"]
        except KeyError as e:
            self.logger.error("Malformed SQS message: %s", str(e))
            return

        if (sanitized_object_key := self.object_key_sanitizer(object_key)) == "":
            return

        if not self.is_known_workload(accelerator, object_key):
            metrics.add_metric(name="UnknownWorkload", unit=MetricUnit.Count, value=1)

            first_received = datetime.now(timezone.utc)
            dynamodb_serializer = TypeSerializer()

            response = self.dynamodb_client.get_item(
                TableName=self.unknown_workloads_table_name,
                Key={
                    "object_key": dynamodb_serializer.serialize(sanitized_object_key),
                },
            )

            hit_count = 1

            if "Item" in response:
                dynamodb_deserializer = TypeDeserializer()
                hit_count = (
                    dynamodb_deserializer.deserialize(response["Item"]["hit_count"]) + 1
                )
                previous_first_received = parse(
                    dynamodb_deserializer.deserialize(
                        response["Item"]["first_received"]
                    ),
                ).astimezone(timezone.utc)
                first_received = min(first_received, previous_first_received)
            else:
                notification = {
                    "timestamp": str(first_received),
                    "cbs_id": cbs_id,
                    "accelerator": accelerator,
                    "object_key": object_key,
                }
                self.sns_client.publish(
                    TopicArn=self.unknown_workloads_topic_arn,
                    Subject="New Unknown Workload Detected",
                    Message=str(notification),
                )

            self.dynamodb_client.update_item(
                TableName=self.unknown_workloads_table_name,
                Key={"object_key": dynamodb_serializer.serialize(sanitized_object_key)},
                UpdateExpression="set first_received = :first_received, hit_count = :hit_count",
                ExpressionAttributeValues={
                    ":first_received": dynamodb_serializer.serialize(
                        str(first_received)
                    ),
                    ":hit_count": dynamodb_serializer.serialize(hit_count),
                },
            )

    def is_known_workload(self, accelerator: str, object_key: str) -> bool:
        match accelerator:
            case "asea":
                log_type_regex_to_workload_map = (
                    constants.ASEA_LOG_TYPE_REGEX_TO_WORKLOAD_MAP
                )
            case "lza":
                log_type_regex_to_workload_map = (
                    constants.LZA_LOG_TYPE_REGEX_TO_WORKLOAD_MAP
                )
            case None:
                log_type_regex_to_workload_map = (
                    constants.LOG_TYPE_REGEX_TO_WORKLOAD_MAP
                )

        for log_type_regex in log_type_regex_to_workload_map:
            if search(log_type_regex, object_key.lower()):
                self.logger.warning(
                    "Known workload found '%s'",
                    log_type_regex_to_workload_map[log_type_regex],
                )
                return True

        return False
