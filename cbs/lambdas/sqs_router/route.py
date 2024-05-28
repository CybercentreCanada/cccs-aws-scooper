from json import dumps
from os import environ
from typing import Any

import common_functions as cf
from aws_lambda_powertools import Logger
from boto3 import client
from core import constants
from core.utils.dynamodb import read_partner_inventory_table
from core.utils.sts import assume_role


class SQSRouter:
    def __init__(self) -> None:
        # Get environment variables
        self.sqs_queue_url = environ["CBS_SQS_URL"]
        self.version = environ["VERSION"]
        # Setup logger
        self.logger = Logger(
            service=environ["AWS_LAMBDA_FUNCTION_NAME"],
            datefmt="%Y-%m-%dT%H:%M:%S.%f",
            use_datetime_directive=True,
            utc=True,
        )
        # Read partners from inventory table
        partners = read_partner_inventory_table(
            table_name=environ["INVENTORY_TABLE_NAME"],
            session=assume_role(environ["CBS_DEVOPS_ROLE_ARN"]),
        )
        self.partner_bucket_names = {
            partner[constants.CBS_ID]: partner.get(constants.BUCKET_NAME)
            for partner in partners.values()
        }
        # Setup clients
        self.s3_client = client("s3")
        self.sqs_client = client("sqs")

    def route(self, message: dict[str, Any]) -> None:
        """Route a 1.0 partner's SQS message to 2.0 SQS if they haven't onboarded yet."""
        cbs_id: str = message["metadata"]["Cbs-Identifier"]
        object_key: str = message["metadata"]["File"]
        workload: str = message["metadata"]["Workload"]

        if (agent_version := message["metadata"]["Release"]).endswith("/src"):
            agent_version = "<1.8.2"

        self.logger.append_keys(
            CbsId=cbs_id, Workload=workload, AgentVersion=agent_version
        )

        if not cf.is_supported_workload(object_key):
            self.logger.warning("'%s' is an unsupported workload", workload)
            return

        if cf.is_bucket_empty(self.partner_bucket_names.get(cbs_id), self.s3_client):
            self.sqs_client.send_message(
                QueueUrl=self.sqs_queue_url, MessageBody=dumps(message)
            )
            self.logger.info(
                "'%s' message forwarded from %s's sensor (%s) to '%s' SQS",
                workload,
                cbs_id,
                agent_version,
                self.version,
            )
