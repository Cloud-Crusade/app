import pytest
from payment.main import app as _app


@pytest.fixture
def app():
    return _app
