import pytest
from auth.main import app as _app


@pytest.fixture
def app():
    return _app
