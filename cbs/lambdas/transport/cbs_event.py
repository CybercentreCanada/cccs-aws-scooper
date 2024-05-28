from functools import cached_property
from json import loads
from os import environ
from re import search
from urllib.parse import unquote

import common_functions as cf
from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.data_classes import EventBridgeEvent
from core import constants
from core.types import Partner
from exceptions import TransportError
from vpc_config import VPCConfig

logger = Logger(service=__name__)


class CBSEvent:
    def __init__(
        self,
        event: EventBridgeEvent,
        cccs_account_id: str,
        partners: dict[str, Partner],
    ) -> None:
        self.event = event
        self.cccs_account_id = cccs_account_id
        self.partners = partners

        self.metadata_update_needed = False

    @cached_property
    def object_bucket(self) -> str:
        """Get the name of the bucket that the event originated."""
        try:
            return self.event.detail["requestParameters"]["bucketName"]
        except KeyError:
            return self.event.detail["bucket"]["name"]

    @cached_property
    def object_key(self) -> str:
        """Get the event's object key."""
        try:
            return unquote(self.event.detail["requestParameters"]["key"])
        except KeyError:
            return unquote(self.event.detail["object"]["key"])

    @cached_property
    def partner_account_id(self) -> str:
        """Get the log archive account ID of the partner."""
        try:
            return self.event.detail["userIdentity"]["accountId"]
        except KeyError:
            for account_id, details in self.partners.items():
                if self.object_key.startswith(details[constants.CBS_ID]):
                    return account_id

    @cached_property
    def cbs_id(self) -> str:
        """Get the partner's CBS ID."""
        try:
            return self.partners[self.partner_account_id][constants.CBS_ID]
        except KeyError as e:
            raise TransportError(
                f"Failed to resolve CBS ID for account '{self.partner_account_id}'"
            ) from e

    @property
    def org_id(self) -> str | None:
        """Get the partner's organization ID."""
        try:
            return self.partners[self.partner_account_id][constants.ORG_ID]
        except KeyError:
            # Try matching object key to org CloudTrail event that contains org ID
            if match := search(r"(o-[a-z0-9]{10,32})/", self.object_key):
                org_id = match.group(1)
                logger.info("Updating %s's org ID to '%s'", self.cbs_id, org_id)
                self.partners[self.partner_account_id][constants.ORG_ID] = org_id
                cf.update_partner_inventory_table(constants.ORG_ID, org_id, self)
                return org_id

    @cached_property
    def workload(self) -> str | None:
        """Infer the object's workload based on a match within the log type regex map."""
        match self.accelerator:
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
            case _:
                raise TransportError(
                    f"Couldn't find accelerator being used by '{self.cbs_id}'"
                )

        for log_type_regex in log_type_regex_to_workload_map:
            if search(log_type_regex, self.object_key.lower()):
                return log_type_regex_to_workload_map[log_type_regex]

    @cached_property
    def object_size(self) -> float:
        """Get the size of the event's object."""
        try:
            return self.event.detail["additionalEventData"]["bytesTransferredIn"]
        except KeyError:
            return self.event.detail["object"]["size"]

    @cached_property
    def accelerator(self) -> str | None:
        """Get the partner's accelerator."""
        error_message = "Couldn't find partner with account ID"
        if self.object_key == "metadata.json":
            logger.info("Reading new metadata file...")

            # Assume reader role
            cbs_reader_role_session = cf.assume_role(
                role_arn=environ["CBS_READER_ROLE_ARN"],
                role_session_name=f"{environ['AWS_LAMBDA_FUNCTION_NAME']}-ReadAcceleratorMetadata",
            )
            cbs_reader_role_s3_client = cbs_reader_role_session.client("s3")
            # Read metadata file
            metadata = loads(
                cf.read_from_s3(
                    bucket_name=self.object_bucket,
                    object_key=self.object_key,
                    s3_client=cbs_reader_role_s3_client,
                )
            )

            logger.info("Successfully read new metadata file!")

            if "lastSuccessfulExecution" in metadata:
                new_accelerator = "lza"
            elif "latestSuccessfulExecution" in metadata:
                new_accelerator = "asea"
            else:
                raise TransportError(f"Unknown accelerator metadata: '{metadata}'")

            logger.info("Accelerator detected: '%s'", new_accelerator.upper())

            vpc_config = VPCConfig(self.cbs_id, new_accelerator, self.object_bucket)
            vpc_flow_log_fields = vpc_config.get_config(cbs_reader_role_s3_client)

            # If the fields have been altered, reflect that change in our environment
            if (
                vpc_flow_log_fields != self.vpc_flow_log_fields
            ) and vpc_flow_log_fields is not None:
                vpc_config.update_config(vpc_flow_log_fields, self)

            try:
                if new_accelerator != (
                    old_accelerator := self.partners[self.partner_account_id][
                        constants.ACCELERATOR
                    ]
                ):
                    logger.info(
                        "Accelerator has changed from '%s' to '%s'!",
                        old_accelerator.upper(),
                        new_accelerator.upper(),
                    )
                    self.metadata_update_needed = True
                else:
                    logger.info("Accelerator remains unchanged")
            except KeyError as e:
                raise TransportError(
                    f"{error_message} '{self.partner_account_id}'"
                ) from e
            return new_accelerator
        else:
            try:
                return self.partners[self.partner_account_id][constants.ACCELERATOR]
            except KeyError as e:
                raise TransportError(
                    f"{error_message} '{self.partner_account_id}'"
                ) from e

    @property
    def vpc_flow_log_fields(self) -> str:
        """Get the partner's VPC flow logs custom fields."""
        try:
            vpc_custom_fields = self.partners[self.partner_account_id][
                constants.VPC_CUSTOM_FIELDS
            ]
        except KeyError:
            vpc_config = VPCConfig(self.cbs_id, self.accelerator, self.object_bucket)
            vpc_custom_fields = vpc_config.get_config()
            vpc_config.update_config(vpc_custom_fields, self)

        return vpc_custom_fields
