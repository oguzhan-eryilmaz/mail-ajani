import pytest

from mail_ajani import db, telegram, tur


@pytest.fixture(autouse=True)
def no_real_retry_sleep(monkeypatch):
    monkeypatch.setattr(tur, "sleep", lambda seconds: None)
    monkeypatch.setattr(telegram, "sleep", lambda seconds: None)


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    yield c
    c.close()
