import pytest
from auth.db import Base, getReaderSession, getWriterSession
from auth.main import app as _app


@pytest.fixture
def serviceBase():
    return Base


@pytest.fixture
def sessionDeps():
    return (getReaderSession, getWriterSession)


@pytest.fixture
def app():
    return _app
