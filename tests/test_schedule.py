from datetime import datetime, timedelta

from mail_ajani import schedule
from mail_ajani.config import TZ


def d(h, m=0, day=19):
    return datetime(2026, 9, day, h, m, tzinfo=TZ)


def test_latest_slot():
    assert schedule.latest_slot(d(13, 5)) == d(12)
    assert schedule.latest_slot(d(3)) == d(0)
    assert schedule.latest_slot(d(0)) == d(0)
    assert schedule.latest_slot(d(23, 59)) == d(18)


def test_should_run():
    assert schedule.should_run(d(13), None)
    assert not schedule.should_run(d(13), d(12, 1))
    assert schedule.should_run(d(12, 30), d(11, 59))
    # Mac was asleep through 18:00 and wakes at 22:00
    assert schedule.should_run(d(22), d(12))


def test_fetch_since():
    assert schedule.fetch_since(d(12), None) == d(12) - timedelta(hours=24)
    assert schedule.fetch_since(d(12), d(6)) == d(5)


def test_is_quiet():
    assert schedule.is_quiet(d(0))
    assert schedule.is_quiet(d(7, 59))
    assert not schedule.is_quiet(d(8))
    assert not schedule.is_quiet(d(18))
