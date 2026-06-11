import pytest
from event.main import app as _app


@pytest.fixture
def app():
    return _app
