from datetime import datetime, timedelta, timezone
from json import dumps
from os import environ

import common_functions as cf
from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.data_classes import EventBridgeEvent
from aws_lambda_powertools.utilities.typing import LambdaContext
from boto3 import client
from boto3.dynamodb.types import TypeSerializer
from cbs_event import CBSEvent
from core import constants
from core.utils.dynamodb import read_partner_inventory_table
from core.utils.sts import assume_role
from exceptions import TransportError


class Transport:
    def __init__(self) -> None:
        # Get environment variables
        self.agent_version = environ["VERSION"]
        self.sqs_url = environ["CBS_SQS_URL"]
        self.dlq_url = environ["CBS_DLQ_URL"]
        # Setup logger
        self.logger = Logger(
            service=environ["AWS_LAMBDA_FUNCTION_NAME"],
            datefmt="%Y-%m-%dT%H:%M:%S.%f",
            use_datetime_directive=True,
            utc=True,
        )
        self.logger.append_keys(Version=self.agent_version)
        # Read partners from inventory table
        self.partners = read_partner_inventory_table(
            table_name=environ["INVENTORY_TABLE_NAME"],
            session=assume_role(environ["CBS_DEVOPS_ROLE_ARN"]),
        )
        # Setup SQS client
        self.sqs_client = client("sqs")

    def process_s3_event(self, event: EventBridgeEvent, context: LambdaContext) -> None:
        """Process CBS S3 event."""
        try:
            self.cbs_event = CBSEvent(
                event=event, cccs_account_id=event.account, partners=self.partners
            )
        except (KeyError, TypeError) as e:
            raise TransportError("Event is not an accepted type") from e

        # Check that workload is supported
        if not cf.is_supported_workload(self.cbs_event.object_key):
            raise TransportError("Workload is unsupported", self.cbs_event.object_key)

        # Check that workload could be resolved
        if self.cbs_event.workload is None:
            self.handle_unknown_workload()

        # Check if first event from newly deployed partner
        if not self.partners[self.cbs_event.partner_account_id][constants.DEPLOYED]:
            self.first_partner_event()

        # Send object info to SQS
        self.sqs_client.send_message(
            QueueUrl=self.sqs_url, MessageBody=self.create_message()
        )

        log_details = {
            "CbsSensorId": self.cbs_event.cbs_id,
            "Workload": self.cbs_event.workload,
            "Accelerator": (
                self.cbs_event.accelerator.upper()
                if self.cbs_event.accelerator
                else None
            ),
            "OrgId": self.cbs_event.org_id,
            "ObjectKey": self.cbs_event.object_key,
            "BucketName": self.cbs_event.object_bucket,
            "Size": self.cbs_event.object_size,
            "AWSRequestId": context.aws_request_id,
            "MemoryLimit": context.memory_limit_in_mb,
        }

        self.logger.info(
            "Log object '%s' in bucket '%s' sent to SQS",
            self.cbs_event.object_key,
            self.cbs_event.object_bucket,
            **log_details,
        )

        # Check if accelerator has changed
        if self.cbs_event.metadata_update_needed:
            self.update_partner_accelerator_values()

    def handle_unknown_workload(self) -> None:
        """Send unknown workload to DLQ for triaging."""
        self.logger.warning(
            "Sending unsupported workload '%s' from %s to DLQ",
            self.cbs_event.object_key,
            self.cbs_event.cbs_id,
        )
        self.sqs_client.send_message(
            QueueUrl=self.dlq_url,
            MessageBody=dumps(
                {
                    "cbs_id": self.cbs_event.cbs_id,
                    "accelerator": self.cbs_event.accelerator,
                    "object_key": self.cbs_event.object_key,
                }
            ),
        )
        raise TransportError(
            "Unsupported workload sent to DLQ", self.cbs_event.object_key
        )

    def first_partner_event(self) -> None:
        """Handle everything needed when we receive a partner's first replication event."""
        self.partners[self.cbs_event.partner_account_id][constants.DEPLOYED] = True
        if not cf.get_partner_inventory_table_item(constants.DEPLOYED, self.cbs_event):
            cf.update_partner_inventory_table(constants.DEPLOYED, True, self.cbs_event)
            self.logger.info(
                "'%s' has deployed 2.0. Triggering CI/CD pipeline to enable their CloudWatch Alarms...",
                self.cbs_event.cbs_id,
            )
            cf.trigger_codepipeline(
                name=environ["CICD_PIPELINE_NAME"],
                client_request_token=f"Deploying{self.cbs_event.cbs_id}CloudWatchAlarms",
                codepipeline_client=cf.assume_role(
                    role_arn=environ["CBS_DEVOPS_ROLE_ARN"],
                    role_session_name="AssumeDevOpsRole",
                ).client("codepipeline"),
            )
            self.create_alarm_suppression_record(
                environ["CBS_ALARM_SUPPRESSION_TABLE_NAME"], self.cbs_event.cbs_id
            )

    def update_partner_accelerator_values(self) -> None:
        """Update partner inventory with new accelerator value."""
        self.logger.info(
            "Accelerator has changed for '%s'. Updating inventory table...",
            self.cbs_event.cbs_id,
        )
        self.partners[self.cbs_event.partner_account_id][
            constants.ACCELERATOR
        ] = self.cbs_event.accelerator
        cf.update_partner_inventory_table(
            constants.ACCELERATOR, self.cbs_event.accelerator, self.cbs_event
        )

    def create_metadata(self) -> dict[str, str]:
        """Create metadata for SQS message."""
        metadata = {
            "Cbs-Identifier": self.cbs_event.cbs_id,
            "Workload": self.cbs_event.workload,
            "File": self.cbs_event.object_key,
            "Bucket": self.cbs_event.object_bucket,
            "ReaderArn": environ["CBS_READER_ROLE_ARN"],
            "Release": self.agent_version,
        }
        if self.cbs_event.workload == "cloudwatch.vpcFlowLogs":
            metadata["CbsCustomFields"] = self.cbs_event.vpc_flow_log_fields
        return metadata

    def create_message(self) -> str:
        """Build SQS message to include metadata and raw event."""
        return dumps(
            {
                "metadata": self.create_metadata(),
                "event": self.cbs_event.event.raw_event,
            }
        )

    def create_alarm_suppression_record(self, table_name: str, cbs_id: str) -> None:
        """Add records to alarm suppression table."""
        ddb_client = client("dynamodb")
        serializer = TypeSerializer()

        current_date = datetime.now(timezone.utc)
        replication_expiry = current_date + timedelta(days=2)
        metadata_expiry = current_date + timedelta(days=1)

        ddb_client.put_item(
            TableName=table_name,
            Item={
                constants.CBS_ID: serializer.serialize(cbs_id),
                constants.ALARM_TYPE: serializer.serialize("ReplicationAlarm"),
                constants.SUPPRESSION_EXPIRY: serializer.serialize(
                    replication_expiry.isoformat()
                ),
            },
        )
        ddb_client.put_item(
            TableName=table_name,
            Item={
                constants.CBS_ID: serializer.serialize(cbs_id),
                constants.ALARM_TYPE: serializer.serialize("MetadataWorkloadAlarm"),
                constants.SUPPRESSION_EXPIRY: serializer.serialize(
                    metadata_expiry.isoformat()
                ),
            },
        )
