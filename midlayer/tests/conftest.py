import pytest

from tests.fakes import FakeDao, FakeQueue


@pytest.fixture
def dao():
    return FakeDao()


@pytest.fixture
def queue():
    return FakeQueue()
