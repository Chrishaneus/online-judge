import pytest

from app import create_app
from app.config import Settings
from tests.fakes import FakeQueue, FakeStore, fake_repositories

ADMIN_TOKEN = "s3cret-admin-token-0123"


@pytest.fixture
def store():
    return FakeStore()


@pytest.fixture
def queue():
    return FakeQueue()


@pytest.fixture
def settings():
    return Settings(admin_token=ADMIN_TOKEN, rate_limit_per_min=600, rate_limit_burst=100)


@pytest.fixture
def app(settings, store, queue):
    app = create_app(settings, fake_repositories(store, queue))
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth():
    return {"Authorization": f"Bearer {ADMIN_TOKEN}"}
