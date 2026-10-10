"""
Command line entry point.

    comdirect-mcp                   run the MCP server over stdio (what MCP clients start)
    comdirect-mcp configure         store the credentials in the OS keychain
    comdirect-mcp configure --delete
"""

import argparse
import sys
from getpass import getpass

import keyring
from keyring.errors import KeyringError, PasswordDeleteError

from . import __version__
from .credentials import KEYRING_SERVICE, keyring_get

PROMPTS = [
    # (keychain entry, prompt, hide input)
    ("COMDIRECT_CLIENT_ID", "Client ID (Verwaltung > Entwicklerzugang)", False),
    ("COMDIRECT_CLIENT_SECRET", "Client Secret", True),
    ("COMDIRECT_USERNAME", "Zugangsnummer", False),
    ("COMDIRECT_PASSWORD", "PIN", True),
]


def configure(delete: bool = False) -> int:
    try:
        backend = keyring.get_keyring()
        if delete:
            for name, _, _ in PROMPTS:
                try:
                    keyring.delete_password(KEYRING_SERVICE, name)
                except PasswordDeleteError:
                    pass
            print(f"Removed the comdirect credentials from {backend.name}.")
            return 0

        print(f"Storing comdirect credentials in {backend.name}. Press Enter to keep a stored value.")
        for name, label, secret in PROMPTS:
            stored = keyring_get(name)
            prompt = f"{label}{' [stored]' if stored else ''}: "
            value = (getpass(prompt) if secret else input(prompt)).strip()
            if value:
                keyring.set_password(KEYRING_SERVICE, name, value)
            elif not stored:
                print(f"  {name} left empty; set it later or via environment variable.")
    except KeyringError as e:
        print(f"No usable OS keychain ({e}). Use environment variables or a .env file instead.", file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        print("\nAborted.", file=sys.stderr)
        return 1

    print("Done. Environment variables still take precedence over the keychain.")
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="comdirect-mcp",
        description="Read-only MCP server for the comdirect banking API. Without a command, runs the server (stdio).",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("serve", help="run the MCP server over stdio (default)")
    configure_parser = commands.add_parser("configure", help="store the credentials in the OS keychain")
    configure_parser.add_argument("--delete", action="store_true", help="remove the stored credentials")
    args = parser.parse_args(argv)

    if args.command == "configure":
        sys.exit(configure(delete=args.delete))

    from .server import main as serve

    serve()
