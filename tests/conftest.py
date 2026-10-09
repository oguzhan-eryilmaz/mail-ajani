import pytest

from mail_ajani import db, telegram, tur


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("MAIL_AJANI_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MAIL_AJANI_LOGS", str(tmp_path / "logs"))


@pytest.fixture(autouse=True)
def no_real_retry_sleep(monkeypatch):
    monkeypatch.setattr(tur, "sleep", lambda seconds: None)
    monkeypatch.setattr(telegram, "sleep", lambda seconds: None)


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    yield c
    c.close()
