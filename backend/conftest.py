"""Root conftest — sets environment for all tests."""

import os

os.environ.setdefault("AGENTFORGE_TESTING", "1")
