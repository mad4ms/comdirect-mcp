"""Subprocess fixture: real stdio server, synthetic auth and mocked HTTP transport only."""

import os
import socket
from unittest.mock import patch

import keyring
import requests
import urllib3
from conftest import MemoryKeyring
from test_http_roundtrip import FakeComdirect

from comdirect_mcp.auth import TanChallenge


class FakeAuthenticator:
    def __init__(self, **kwargs):
        pass

    def start(self, tan_type=None):
        return TanChallenge("challenge", "P_TAN_PUSH", "session", primary_token="primary")

    def complete(self, challenge, tan):
        return "session", {"access_token": "token", "refresh_token": "refresh", "expires_in": 599}

    def revoke(self, token):
        pass

    def refresh(self, token):
        return {"access_token": "new-token", "refresh_token": "new-refresh", "expires_in": 599}


if __name__ == "__main__":
    keyring.set_keyring(MemoryKeyring())
    for name in ("COMDIRECT_CLIENT_ID", "COMDIRECT_CLIENT_SECRET", "COMDIRECT_USERNAME", "COMDIRECT_PASSWORD"):
        os.environ[name] = "synthetic"
    os.environ.pop("COMDIRECT_ENV_FILE", None)
    with (
        patch("comdirect_mcp.client.Authenticator", FakeAuthenticator),
        patch.object(urllib3.PoolManager, "request", side_effect=FakeComdirect()),
        patch.object(requests.Session, "request", side_effect=RuntimeError("Network forbidden in tests")),
        patch.object(socket, "create_connection", side_effect=RuntimeError("Network forbidden in tests")),
    ):
        from comdirect_mcp.cli import main

        main()
