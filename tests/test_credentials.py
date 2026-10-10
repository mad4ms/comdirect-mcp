import keyring
import pytest
from keyring.errors import NoKeyringError

from comdirect_mcp import cli
from comdirect_mcp.credentials import CREDENTIAL_VARS, KEYRING_SERVICE, MissingCredentialsError, load_credentials


@pytest.fixture
def clean(monkeypatch, tmp_path):
    for name in CREDENTIAL_VARS.values():
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("COMDIRECT_ENV_FILE", raising=False)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_precedence_environment_keyring_dotenv(clean, monkeypatch, memory_keyring):
    monkeypatch.setenv("COMDIRECT_CLIENT_ID", "from-env")
    keyring.set_password(KEYRING_SERVICE, "COMDIRECT_CLIENT_ID", "from-keyring")
    keyring.set_password(KEYRING_SERVICE, "COMDIRECT_CLIENT_SECRET", "from-keyring")
    (clean / "secrets.env").write_text(
        "COMDIRECT_CLIENT_SECRET=from-dotenv\nCOMDIRECT_USERNAME=from-dotenv\nCOMDIRECT_PASSWORD=from-dotenv\n"
    )
    monkeypatch.setenv("COMDIRECT_ENV_FILE", str(clean / "secrets.env"))

    assert load_credentials() == {
        "client_id": "from-env",
        "client_secret": "from-keyring",
        "username": "from-dotenv",
        "password": "from-dotenv",
    }


def test_missing_credentials_are_listed(clean):
    keyring.set_password(KEYRING_SERVICE, "COMDIRECT_CLIENT_ID", "x")

    with pytest.raises(MissingCredentialsError) as error:
        load_credentials()

    assert error.value.missing == ["COMDIRECT_CLIENT_SECRET", "COMDIRECT_USERNAME", "COMDIRECT_PASSWORD"]


def test_no_keychain_falls_back_to_dotenv(clean, monkeypatch):
    monkeypatch.setattr(keyring, "get_password", lambda *args: (_ for _ in ()).throw(NoKeyringError("none")))
    (clean / "secrets.env").write_text("".join(f"{name}=v\n" for name in CREDENTIAL_VARS.values()))
    monkeypatch.setenv("COMDIRECT_ENV_FILE", str(clean / "secrets.env"))

    assert set(load_credentials().values()) == {"v"}


def test_configure_stores_and_keeps_values(clean, monkeypatch, memory_keyring):
    answers = iter(["User_A1", "secret", "12345678", "pin"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    monkeypatch.setattr(cli, "getpass", lambda prompt: next(answers))

    assert cli.configure() == 0
    assert keyring.get_password(KEYRING_SERVICE, "COMDIRECT_PASSWORD") == "pin"

    # Enter keeps the stored values
    monkeypatch.setattr("builtins.input", lambda prompt: "")
    monkeypatch.setattr(cli, "getpass", lambda prompt: "")
    assert cli.configure() == 0
    assert load_credentials()["client_id"] == "User_A1"


def test_configure_delete(clean, memory_keyring):
    keyring.set_password(KEYRING_SERVICE, "COMDIRECT_PASSWORD", "pin")

    assert cli.configure(delete=True) == 0
    assert memory_keyring.entries == {}


def test_configure_without_keychain(monkeypatch):
    monkeypatch.setattr(keyring, "get_keyring", lambda: (_ for _ in ()).throw(NoKeyringError("none")))
    assert cli.configure() == 1


def test_cli_without_command_runs_server(monkeypatch):
    called = []
    monkeypatch.setattr("comdirect_mcp.server.main", lambda: called.append(True))
    cli.main([])
    assert called == [True]


def test_cli_version(capsys):
    with pytest.raises(SystemExit):
        cli.main(["--version"])
    assert capsys.readouterr().out.startswith("comdirect-mcp ")


def test_dotenv_in_working_directory_is_not_read_implicitly(clean):
    (clean / ".env").write_text("".join(f"{name}=v\n" for name in CREDENTIAL_VARS.values()))

    with pytest.raises(MissingCredentialsError):
        load_credentials()
