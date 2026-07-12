import os

import pytest

from gmail_codex_bridge.secrets import protect, unprotect


@pytest.mark.skipif(os.name != "nt", reason="Windows DPAPI")
def test_dpapi_round_trip():
    secret = b'{"refresh_token":"private"}'
    encrypted = protect(secret)
    assert encrypted != secret
    assert unprotect(encrypted) == secret
