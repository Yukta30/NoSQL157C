import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, ROOT)  # so tests can `import backend`


@pytest.fixture(scope="session")
def seed_dir():
    return os.path.join(ROOT, "data", "seed")
