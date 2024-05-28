from boto3 import client
from moto import mock_aws
from pytest import fixture


@fixture
def organizations():
    with mock_aws():
        yield client("organizations")


@fixture(autouse=True)
def organization(organizations):
    organizations.create_organization(FeatureSet="ALL")


@fixture
def accounts(organizations):
    for i in range(10):
        organizations.create_account(
            AccountName=f"test-account-{i}", Email=f"test-email-{i}@test.com"
        )


def test_is_mgmt_account():
    from cbs.installer.utils.sts import is_mgmt_account

    assert is_mgmt_account()


def test_get_account(accounts, monkeypatch):
    from cbs.installer.utils.sts import get_account_id_by_name

    monkeypatch.setattr("builtins.input", lambda _: "3")

    assert isinstance(get_account_id_by_name("test-account-1"), str)


def test_assume_super_admin_role(organizations, accounts):
    from cbs.installer.utils.sts import assume_super_admin_role

    for account in organizations.list_accounts()["Accounts"]:
        sts_client = assume_super_admin_role(
            f"arn:aws:iam::{account['Id']}:role/test", "TestAssumeRole"
        ).client("sts")

        assert sts_client.get_caller_identity()["Account"] == account["Id"]
