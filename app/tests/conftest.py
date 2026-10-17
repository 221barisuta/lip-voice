import pytest

from lipvoice.paths import Paths
from lipvoice.settings import Settings
from lipvoice.storage.store import Store


@pytest.fixture
def paths(tmp_path):
    return Paths(tmp_path, "test").ensure()


@pytest.fixture
def settings():
    return Settings()


@pytest.fixture
def store(paths, settings):
    s = Store(paths, lambda: settings)
    yield s
    s.close()
