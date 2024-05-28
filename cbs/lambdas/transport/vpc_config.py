import json
from json.decoder import JSONDecodeError
from os import environ
from typing import TYPE_CHECKING

import common_functions as cf
import yaml
from aws_lambda_powertools import Logger
from botocore.client import BaseClient
from botocore.exceptions import ClientError
from core import constants
from yaml.constructor import ConstructorError
from yaml.scanner import ScannerError

if TYPE_CHECKING:
    from cbs_event import CBSEvent

logger = Logger(service=__name__)


class VPCConfig:
    def __init__(self, cbs_id: str, accelerator: str, bucket_name: str) -> None:
        self.cbs_id = cbs_id
        self.accelerator = accelerator
        self.bucket_name = bucket_name

    def get_config(self, s3_client: BaseClient = None) -> str | None:
        """Get a partner's VPC flow log config from their accelerator metadata."""
        if s3_client is None:
            cbs_reader_role_session = cf.assume_role(
                role_arn=environ["CBS_READER_ROLE_ARN"],
                role_session_name=f"{environ['AWS_LAMBDA_FUNCTION_NAME']}-ReadAcceleratorVPCConfig",
            )
            s3_client = cbs_reader_role_session.client("s3")

        # Set default fields
        vpc_flow_log_fields = ",".join(constants.DEFAULT_VPC_FLOW_LOG_FIELDS)

        try:
            logger.info("Getting %s's VPC flow log field entries", self.cbs_id)
            if self.accelerator == "lza":
                metadata = yaml.safe_load(
                    cf.read_from_s3(
                        bucket_name=self.bucket_name,
                        object_key="config/network-config.yaml",
                        s3_client=s3_client,
                    )
                )
                vpc_flow_log_fields = ",".join(metadata["vpcFlowLogs"]["customFields"])
            elif self.accelerator == "asea":
                metadata = json.loads(
                    cf.read_from_s3(
                        bucket_name=self.bucket_name,
                        object_key="config/config.json",
                        s3_client=s3_client,
                    )
                )
                vpc_flow_log_fields = ",".join(
                    metadata["global-options"]["vpc-flow-logs"]["custom-fields"]
                )
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                logger.warning(
                    "%s is missing their %s config",
                    self.cbs_id,
                    self.accelerator.upper(),
                )
            else:
                raise
        except (ConstructorError, ScannerError, JSONDecodeError) as e:
            logger.error(
                "%s's %s config is malformed: %s",
                self.cbs_id,
                self.accelerator.upper(),
                e,
            )
        except KeyError as e:
            logger.error(
                "%s's VPC flow logs custom fields are missing from their %s config: %s",
                self.cbs_id,
                self.accelerator.upper(),
                e,
            )

        return vpc_flow_log_fields

    def update_config(self, vpc_flow_log_fields: str, cbs_event: "CBSEvent") -> None:
        """Update a partner's VPC flow log config entries in partner inventory table and environment variable."""
        logger.info("Updating %s's VPC flow log field entries", self.cbs_id)
        cbs_event.partners[cbs_event.partner_account_id][
            constants.VPC_CUSTOM_FIELDS
        ] = vpc_flow_log_fields
        cf.update_partner_inventory_table(
            constants.VPC_CUSTOM_FIELDS, vpc_flow_log_fields, cbs_event
        )
