from pytest import raises

from cbs.installer.utils import io

ACCOUNTS = {
    1: ("Test Account 1", "111111111111"),
    2: ("Test Account 2", "222222222222"),
    3: ("Test Account 3", "333333333333"),
}


def test_account_input(monkeypatch):
    choice = 1

    monkeypatch.setattr("builtins.input", lambda _: str(choice))
    account_index = io.account_input(ACCOUNTS[choice], len(ACCOUNTS))

    assert account_index == choice
    assert ACCOUNTS[account_index] == ACCOUNTS[choice]


def test_account_input_out_of_range(monkeypatch):
    choice = 0

    monkeypatch.setattr("builtins.input", lambda _: str(choice))

    with raises(KeyError):
        io.account_input(ACCOUNTS[choice], len(ACCOUNTS))
