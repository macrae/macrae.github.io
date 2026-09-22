import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


@pytest.fixture(scope="session")
def repo():
    return ROOT


@pytest.fixture(scope="session")
def corpus():
    from sitegen import content
    return content.load(include_unpublished=True)
