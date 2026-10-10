"""Keeps pyproject.toml, server.json (MCP Registry) and README.md consistent."""

import json
import re
import tomllib
from pathlib import Path

from comdirect_mcp.credentials import CREDENTIAL_VARS

ROOT = Path(__file__).resolve().parent.parent
PROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
SERVER_JSON = json.loads((ROOT / "server.json").read_text())
README = (ROOT / "README.md").read_text()


def test_server_json_matches_project_version():
    assert SERVER_JSON["version"] == PROJECT["version"]
    for package in SERVER_JSON["packages"]:
        assert package["version"] == PROJECT["version"]


def test_server_json_description_fits_registry_limit():
    # The MCP Registry rejects descriptions longer than 100 characters (HTTP 422 on publish).
    assert len(SERVER_JSON["description"]) <= 100


def test_server_json_points_to_this_pypi_package():
    (package,) = SERVER_JSON["packages"]
    assert package["registryType"] == "pypi"
    assert package["identifier"] == PROJECT["name"]
    assert PROJECT["scripts"][PROJECT["name"]] == "comdirect_mcp.cli:main"


def test_readme_contains_registry_ownership_marker():
    # The MCP Registry verifies PyPI ownership via this marker in the package README.
    assert re.search(rf"mcp-name: {re.escape(SERVER_JSON['name'])}(\s|-->)", README)


def test_server_json_declares_all_credentials():
    declared = {var["name"] for var in SERVER_JSON["packages"][0]["environmentVariables"]}
    required = set(CREDENTIAL_VARS.values())
    assert required <= declared


def test_pinned_versions_in_docs_match_project_version():
    docs = [ROOT / "README.md", ROOT / "SECURITY.md", *sorted((ROOT / "docs").rglob("*.md"))]
    pins = {(path.name, pin) for path in docs for pin in re.findall(r"comdirect-mcp@([\w.]+)", path.read_text())}
    assert pins, "expected pinned install examples"
    assert {pin for _, pin in pins} == {PROJECT["version"]}, sorted(pins)
