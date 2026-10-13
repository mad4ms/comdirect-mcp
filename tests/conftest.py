import keyring
import pytest
from keyring.backend import KeyringBackend
from keyring.errors import PasswordDeleteError


class MemoryKeyring(KeyringBackend):
    """In-memory keychain so that no test ever touches the real OS keychain."""

    priority = 1  # type: ignore[assignment]

    def __init__(self):
        super().__init__()
        self.entries: dict[tuple[str, str], str] = {}

    def get_password(self, service, username):
        return self.entries.get((service, username))

    def set_password(self, service, username, password):
        self.entries[(service, username)] = password

    def delete_password(self, service, username):
        if self.entries.pop((service, username), None) is None:
            raise PasswordDeleteError(username)


@pytest.fixture(autouse=True)
def memory_keyring():
    previous = keyring.get_keyring()
    backend = MemoryKeyring()
    keyring.set_keyring(backend)
    yield backend
    keyring.set_keyring(previous)


@pytest.fixture(autouse=True)
def categories_file(tmp_path, monkeypatch):
    """Points the category rules to a temporary file (not created), never to the user's real config."""
    path = tmp_path / "categories.toml"
    monkeypatch.setenv("COMDIRECT_MCP_CATEGORIES", str(path))
    return path
