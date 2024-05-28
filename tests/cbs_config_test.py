from boto3 import client
from moto import mock_aws
from pytest import fixture, mark

from cbs.core.cbs_config import RemoteConfig


@fixture
def s3():
    with mock_aws():
        yield client("s3")


@fixture(autouse=True)
def remote_config_bucket(s3):
    bucket_name = "test"
    s3.create_bucket(Bucket=bucket_name)
    s3.upload_file("tests/cbs_config.json", bucket_name, "123456789012/cbs_config.json")


@mark.filterwarnings("ignore::DeprecationWarning")
def test_remote_config():
    remote_config = RemoteConfig.from_file(__package__, "remote_config.json")

    assert isinstance(remote_config, RemoteConfig)
