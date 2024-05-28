from datetime import date, timedelta

from cbs.core.utils.datetime import is_expired

DATE_FORMAT = "%Y-%m-%d"


def test_is_expired():
    yesterday = str(date.today() - timedelta(days=1))

    assert is_expired(yesterday, DATE_FORMAT)


def test_is_not_expired():
    tomorrow = str(date.today() + timedelta(days=1))

    assert not is_expired(tomorrow, DATE_FORMAT)
