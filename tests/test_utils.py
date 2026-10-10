import datetime
from unittest.mock import patch

from comdirect_mcp import utils


def _at(hour, minute, second, microsecond):
    class FixedDatetime(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 10, hour, minute, second, microsecond)

    return patch.object(utils.datetime, "datetime", FixedDatetime)


def test_request_id_is_nine_digits_hhmmsssss():
    # API docs 1.2.2: 9-digit number, e.g. a timestamp HHmmssSSS
    utils._last_request_id = -1
    with _at(14, 1, 13, 250_000):
        assert utils.request_id() == "140113250"


def test_request_ids_are_unique_within_the_same_millisecond():
    utils._last_request_id = -1
    with _at(14, 1, 13, 250_000):
        ids = [utils.request_id() for _ in range(3)]
    assert ids == ["140113250", "140113251", "140113252"]


def test_request_id_restarts_after_midnight():
    utils._last_request_id = -1
    with _at(23, 59, 59, 999_000):
        assert utils.request_id() == "235959999"
    with _at(0, 0, 0, 5_000):
        assert utils.request_id() == "000000005"
