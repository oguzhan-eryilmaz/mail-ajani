import pytest

from mail_ajani import db


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    yield c
    c.close()
