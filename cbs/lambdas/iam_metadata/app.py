from json import dumps
from os import getenv

from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.typing import LambdaContext
from common_functions import DateTimeEncoder, write_to_s3
from core import constants
from iam_metadata import IAMMetadata

logger = Logger(service=getenv("AWS_LAMBDA_FUNCTION_NAME"))


def lambda_handler(partner: dict[str, str], _: LambdaContext):
    cbs_id = partner[constants.CBS_ID]
    try:
        iam_metadata = IAMMetadata(partner[constants.MGMT_ACCOUNT_ID])
        write_to_s3(
            dumps(
                iam_metadata.report,
                cls=DateTimeEncoder,
                indent=2,
            ).encode(),
            partner[constants.BUCKET_NAME],
            f"{cbs_id}/{constants.CBS_METADATA_OBJECT_KEY}/iam.json",
        )
        logger.info("Successfully read IAM metadata for '%s'!", cbs_id)
    except Exception:
        logger.error("Issues getting IAM metadata from '%s'!", cbs_id, exc_info=1)
