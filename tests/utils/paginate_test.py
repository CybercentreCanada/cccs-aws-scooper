from logging import getLogger

from boto3 import client
from botocore.exceptions import OperationNotPageableError
from moto import mock_aws
from pytest import raises

from cbs.core.utils.paginate import paginate

_logger = getLogger(__name__)


@mock_aws
def test_paginate():
    assert isinstance(
        paginate(
            client=client("account"),
            command="list_regions",
            array="AccountId",
            logger=_logger,
        ),
        list,
    )


@mock_aws
def test_paginator_not_available():
    with raises(OperationNotPageableError):
        paginate(
            client=client("s3"),
            command="list_buckets",
            array="Buckets",
            logger=_logger,
        )
