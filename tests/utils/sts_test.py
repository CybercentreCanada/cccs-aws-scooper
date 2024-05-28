# from boto3 import Session
# from moto import mock_aws

# TODO: Figure out why botocore.exceptions.NoCredentialsError: Unable to locate credentials is being raised
# @mock_aws
# def test_assume_role():
#     from cbs.core.utils.sts import assume_role

#     assert isinstance(assume_role("arn:aws:iam::111111111111:role/test"), Session)
