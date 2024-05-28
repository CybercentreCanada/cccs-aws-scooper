from json import dumps
from os import getenv

from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.typing import LambdaContext
from common_functions import DateTimeEncoder, write_to_s3
from core import constants
from sso_metadata import SSOMetadata

logger = Logger(service=getenv("AWS_LAMBDA_FUNCTION_NAME"))


def lambda_handler(partner: dict[str, str], _: LambdaContext):
    cbs_id = partner[constants.CBS_ID]
    try:
        sso_metadata = SSOMetadata(partner[constants.MGMT_ACCOUNT_ID])
        write_to_s3(
            dumps(
                sso_metadata.report,
                cls=DateTimeEncoder,
                indent=2,
            ).encode(),
            partner[constants.BUCKET_NAME],
            f"{cbs_id}/{constants.CBS_METADATA_OBJECT_KEY}/sso.json",
        )
        logger.info("Successfully read SSO metadata for '%s'!", cbs_id)
    except Exception:
        logger.error("Issues getting SSO metadata from '%s'!", cbs_id, exc_info=1)
