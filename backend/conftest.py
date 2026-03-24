"""Root conftest — sets environment for all tests."""

import os

os.environ.setdefault("FORGE_TESTING", "1")
