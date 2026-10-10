"""
Credential lookup for the MCP server.

Each credential is taken from the first source that has it:

1. environment variable (e.g. set by the MCP client config)
2. OS keychain (macOS Keychain, Windows Credential Manager, Secret Service), see `comdirect-mcp configure`
3. `.env` file in the working directory
"""

import os

import keyring
from dotenv import dotenv_values, find_dotenv
from keyring.errors import KeyringError

KEYRING_SERVICE = "comdirect-mcp"

# ComdirectClient credential key -> environment variable / keychain entry name
CREDENTIAL_VARS = {
    "client_id": "COMDIRECT_CLIENT_ID",
    "client_secret": "COMDIRECT_CLIENT_SECRET",
    "username": "COMDIRECT_USERNAME",
    "password": "COMDIRECT_PASSWORD",
}


class MissingCredentialsError(Exception):
    def __init__(self, missing: list[str]):
        self.missing = missing
        super().__init__(f"Missing credentials: {', '.join(missing)}")


def keyring_get(name: str) -> str | None:
    """Reads one entry from the OS keychain; None if absent or no keychain is available."""
    try:
        return keyring.get_password(KEYRING_SERVICE, name)
    except KeyringError:
        return None


def load_credentials() -> dict[str, str]:
    """Returns the ComdirectClient credentials or raises MissingCredentialsError."""
    dotenv: dict[str, str | None] | None = None
    credentials: dict[str, str] = {}
    missing: list[str] = []

    for key, name in CREDENTIAL_VARS.items():
        value = os.environ.get(name) or keyring_get(name)
        if not value:
            if dotenv is None:
                path = find_dotenv(usecwd=True)
                dotenv = dotenv_values(path) if path else {}
            value = dotenv.get(name)
        if value:
            credentials[key] = value
        else:
            missing.append(name)

    if missing:
        raise MissingCredentialsError(missing)
    return credentials
