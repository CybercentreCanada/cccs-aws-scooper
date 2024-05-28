from json import dumps, loads
from os import getenv
from re import compile, match

from alarm_priorities import ALARM_PRIORITIES
from aws_lambda_powertools.utilities.data_classes import SNSEvent
from boto3 import client
from boto3.dynamodb.types import TypeSerializer
from botocore.client import BaseClient
from core import constants

PATTERN = compile(r"^CBS-(\w*)-(.*)-(dev|stage|prod)-.*$")


def is_alarm_suppressed(
    ddb_client: BaseClient, cbs_id: str, table_name: str, alarm_name: str
) -> bool:
    serializer = TypeSerializer()

    suppression_entry = ddb_client.get_item(
        TableName=table_name,
        Key={
            constants.CBS_ID: serializer.serialize(cbs_id),
            constants.ALARM_TYPE: serializer.serialize(alarm_name),
        },
    )

    return "Item" in suppression_entry


class AlarmFormatter:
    def __init__(self) -> None:
        self._logger = None
        self.ddb_client = client("dynamodb")
        self.sns_client = client("sns")
        self.cloudwatch_alarms_topic_arn = getenv("CLOUDWATCH_ALARMS_TOPIC")
        self.alarm_suppression_table_name = getenv("ALARM_SUPPRESSION_TABLE_NAME")

    def format(self, event: SNSEvent) -> None:
        sns_message = loads(event.sns_message)

        alarm_name_full = sns_message["AlarmName"]
        alarm_name = alarm_name_full.split("-")[1]

        cbs_id = match(PATTERN, alarm_name_full).group(2)
        priority = None

        if not is_alarm_suppressed(
            self.ddb_client, cbs_id, self.alarm_suppression_table_name, alarm_name
        ):
            for alarm_names, priority_level in ALARM_PRIORITIES.items():
                alarm_names = dict(alarm_names)
                if alarm_name in alarm_names:
                    priority = priority_level
                    description, playbook = alarm_names[alarm_name]
                    message_attributes = {
                        "Priority": {"DataType": "String", "StringValue": priority},
                        "Playbook": {"DataType": "String", "StringValue": playbook},
                    }

            if priority is None:
                description = "Unknown Error!"

            self.sns_client.publish(
                TopicArn=self.cloudwatch_alarms_topic_arn,
                Subject=f"AWS - {cbs_id} - {description}",
                Message=dumps(sns_message),
                MessageAttributes=message_attributes,
            )
