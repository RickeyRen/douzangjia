from __future__ import annotations

from base64 import urlsafe_b64encode

import pytest


@pytest.fixture
def master_key() -> str:
    return urlsafe_b64encode(b"a" * 32).decode("ascii")

