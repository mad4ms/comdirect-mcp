import base64
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from mcp.client import Client
from mcp.types import ElicitResult

from comdirect_mcp import server as mcp_server
from comdirect_mcp.auth import TanChallenge
from comdirect_mcp.domain.models import Account, AccountHolder, Transaction
from comdirect_mcp.exceptions import AuthenticationError

CREDENTIALS = {
    "COMDIRECT_CLIENT_ID": "cid",
    "COMDIRECT_CLIENT_SECRET": "csec",
    "COMDIRECT_USERNAME": "user",
    "COMDIRECT_PASSWORD": "pwd",
}

PUSH_CHALLENGE = TanChallenge(id="ch_1", typ="P_TAN_PUSH", session_id="sess_1", primary_token="tok")


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def comdirect(monkeypatch):
    """A fresh server state with a mocked ComdirectClient."""
    for key, value in CREDENTIALS.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(mcp_server, "_state", mcp_server._ServerState())
    with patch.object(mcp_server, "ComdirectClient") as client_cls:
        client = client_cls.return_value
        client.is_logged_in = False
        client.start_login.return_value = PUSH_CHALLENGE

        def complete_login(challenge, tan=""):
            client.is_logged_in = True

        client.complete_login.side_effect = complete_login
        client.logout.side_effect = lambda: setattr(client, "is_logged_in", False)
        yield client


def approve(approved=True):
    async def callback(context, params):
        return ElicitResult(action="accept", content={"approved": approved})

    return callback


async def decline(context, params):
    return ElicitResult(action="decline")


@pytest.mark.anyio
@pytest.mark.parametrize("mode", ["auto", "legacy"])
async def test_login_with_push_tan_elicitation(comdirect, mode):
    async with Client(mcp_server.mcp, mode=mode, elicitation_callback=approve()) as client:
        result = await client.call_tool("login", {})

    assert not result.is_error, result.content
    assert result.structured_content == {"status": "logged_in"}
    # The push TAN is triggered once, even if the call is retried for input_required.
    comdirect.start_login.assert_called_once_with(tan_type="P_TAN_PUSH")
    comdirect.complete_login.assert_called_once_with(PUSH_CHALLENGE)


@pytest.mark.anyio
async def test_login_declined(comdirect):
    async with Client(mcp_server.mcp, elicitation_callback=decline) as client:
        result = await client.call_tool("login", {})

    assert result.is_error
    comdirect.complete_login.assert_not_called()
    assert mcp_server._state._pending is None


@pytest.mark.anyio
async def test_login_not_approved_in_form(comdirect):
    async with Client(mcp_server.mcp, elicitation_callback=approve(False)) as client:
        result = await client.call_tool("login", {})

    assert result.is_error
    comdirect.complete_login.assert_not_called()


@pytest.mark.anyio
async def test_login_without_elicitation_waits_for_push(comdirect, monkeypatch):
    monkeypatch.setattr(mcp_server, "PUSH_TAN_FALLBACK_WAIT", 0)
    async with Client(mcp_server.mcp) as client:
        result = await client.call_tool("login", {})

    assert not result.is_error, result.content
    comdirect.complete_login.assert_called_once_with(PUSH_CHALLENGE)


@pytest.mark.anyio
async def test_login_rejects_non_push_tan(comdirect):
    comdirect.start_login.return_value = TanChallenge(id="ch_2", typ="M_TAN", session_id="sess_1")
    async with Client(mcp_server.mcp, elicitation_callback=approve()) as client:
        result = await client.call_tool("login", {})

    assert result.is_error
    assert "photoTAN push" in result.content[0].text


@pytest.mark.anyio
async def test_tools_require_login(comdirect):
    async with Client(mcp_server.mcp) as client:
        result = await client.call_tool("list_accounts", {})

    assert result.is_error
    assert "login" in result.content[0].text
    comdirect.list_accounts.assert_not_called()


@pytest.mark.anyio
async def test_list_accounts_structured(comdirect):
    comdirect.is_logged_in = True
    mcp_server._state._client = comdirect
    comdirect.list_accounts.return_value = [
        Account(id="acc_1", currency="EUR", balance=Decimal("100.50"), available=None)
    ]

    async with Client(mcp_server.mcp) as client:
        result = await client.call_tool("list_accounts", {})

    assert not result.is_error, result.content
    assert result.structured_content["accounts"][0]["id"] == "acc_1"
    assert result.structured_content["accounts"][0]["balance"] == "100.50"


@pytest.mark.anyio
async def test_auth_error_is_tool_error_with_login_hint(comdirect):
    comdirect.is_logged_in = True
    mcp_server._state._client = comdirect
    comdirect.list_depots.side_effect = AuthenticationError("Session expired and token refresh failed.")

    async with Client(mcp_server.mcp) as client:
        result = await client.call_tool("list_depots", {})

    assert result.is_error
    assert "`login`" in result.content[0].text


def _tx(i):
    return Transaction(
        account_id="acc_1",
        booking_date=date(2026, 1, i),
        amount=Decimal("-1.00"),
        currency="EUR",
        purpose=f"tx {i}",
        type="DEBIT",
        creditor=AccountHolder(holder_name="Shop", iban="DE89370400440532013000", bic=None),
    )


@pytest.mark.anyio
@pytest.mark.parametrize("available, limit, truncated", [(3, 3, False), (4, 3, True), (2, 3, False)])
async def test_list_transactions_limit_and_masking(comdirect, available, limit, truncated):
    comdirect.is_logged_in = True
    mcp_server._state._client = comdirect
    comdirect.iter_all_transactions.side_effect = lambda **kwargs: iter([_tx(i) for i in range(1, available + 1)])

    async with Client(mcp_server.mcp) as client:
        result = await client.call_tool(
            "list_transactions",
            {"account_id": "acc_1", "min_booking_date": "2026-01-01", "limit": limit},
        )

    assert not result.is_error, result.content
    data = result.structured_content
    assert data["count"] == min(available, limit)
    assert data["truncated"] is truncated
    assert data["transactions"][0]["creditor"]["iban"] == "DE**...3000"
    assert comdirect.iter_all_transactions.call_args.kwargs["min_booking_date"] == "2026-01-01"


@pytest.mark.anyio
async def test_list_transactions_rejects_invalid_date(comdirect):
    comdirect.is_logged_in = True
    mcp_server._state._client = comdirect

    async with Client(mcp_server.mcp) as client:
        result = await client.call_tool("list_transactions", {"account_id": "acc_1", "min_booking_date": "01.01.2026"})

    assert result.is_error
    comdirect.iter_all_transactions.assert_not_called()


@pytest.mark.anyio
async def test_download_document_returns_embedded_resource(comdirect):
    comdirect.is_logged_in = True
    mcp_server._state._client = comdirect
    comdirect.download_document.return_value = b"%PDF-1.7"

    async with Client(mcp_server.mcp) as client:
        result = await client.call_tool("download_document", {"document_id": "doc_1", "mime_type": "application/pdf"})

    assert not result.is_error, result.content
    resource = result.content[0].resource
    assert resource.mime_type == "application/pdf"
    assert base64.b64decode(resource.blob) == b"%PDF-1.7"


@pytest.mark.anyio
async def test_logout(comdirect):
    comdirect.is_logged_in = True
    mcp_server._state._client = comdirect

    async with Client(mcp_server.mcp) as client:
        result = await client.call_tool("logout", {})

    assert result.structured_content == {"status": "logged_out"}
    comdirect.logout.assert_called_once()


def test_missing_credentials_error_explains_how_to_configure(monkeypatch, tmp_path):
    for key in CREDENTIALS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.chdir(tmp_path)  # no .env
    with pytest.raises(mcp_server.ToolError, match="COMDIRECT_PASSWORD.*comdirect-mcp configure"):
        mcp_server._load_credentials()


def test_main_runs_stdio():
    with patch.object(mcp_server.mcp, "run", MagicMock()) as run:
        mcp_server.main()
    run.assert_called_once_with()


@pytest.mark.anyio
async def test_depot_positions_output_matches_schema_with_real_aggregated_shape(comdirect):
    # Live API: `aggregated` nests the depot and has no top-level depotId; the client validates the output schema.
    from comdirect_mcp.domain.mappers import map_depot_balance

    comdirect.is_logged_in = True
    mcp_server._state._client = comdirect
    aggregated = {"depot": {"depotId": "dep_1"}, "currentValue": {"value": "10.00", "unit": "EUR"}}
    comdirect.get_depot_positions.return_value = (map_depot_balance(aggregated, "dep_1"), [])

    async with Client(mcp_server.mcp) as client:
        result = await client.call_tool("get_depot_positions", {"depot_id": "dep_1"})

    assert not result.is_error, result.content
    assert result.structured_content["balance"]["depot_id"] == "dep_1"
    assert result.structured_content["balance"]["purchase_value"] is None


@pytest.mark.anyio
async def test_unconfirmed_challenges_stop_before_comdirect_locks_the_access(comdirect):
    # comdirect locks the online access after 5 challenges without a confirmed TAN.
    async with Client(mcp_server.mcp, elicitation_callback=decline) as client:
        for _ in range(mcp_server.MAX_UNCONFIRMED_CHALLENGES):
            assert (await client.call_tool("login", {})).is_error
        result = await client.call_tool("login", {})

    assert result.is_error
    assert "locks the online banking access" in result.content[0].text
    assert comdirect.start_login.call_count == mcp_server.MAX_UNCONFIRMED_CHALLENGES


@pytest.mark.anyio
async def test_confirmed_login_resets_the_challenge_counter(comdirect):
    async with Client(mcp_server.mcp, elicitation_callback=decline) as client:
        await client.call_tool("login", {})
    async with Client(mcp_server.mcp, elicitation_callback=approve()) as client:
        assert not (await client.call_tool("login", {})).is_error

    assert mcp_server._state._unconfirmed_challenges == 0


@pytest.mark.anyio
async def test_server_shutdown_revokes_the_session(comdirect):
    async with Client(mcp_server.mcp, elicitation_callback=approve()) as client:
        await client.call_tool("login", {})
        comdirect.logout.assert_not_called()

    comdirect.logout.assert_called_once()


@pytest.mark.anyio
async def test_download_document_is_not_annotated_read_only(comdirect):
    # comdirect marks an unread document as read when it is downloaded (API docs 9.1.2).
    async with Client(mcp_server.mcp) as client:
        tools = {tool.name: tool for tool in (await client.list_tools()).tools}

    assert tools["download_document"].annotations.read_only_hint is False
    assert tools["download_document"].annotations.destructive_hint is False
    assert tools["list_documents"].annotations.read_only_hint is True
