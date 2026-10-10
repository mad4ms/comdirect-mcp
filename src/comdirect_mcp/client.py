import json
import logging
import threading
import time
from collections.abc import Callable, Iterator
from typing import Any

from ._openapi import ApiClient, Configuration
from ._openapi.api.banking_api import BankingApi
from ._openapi.api.brokerage_api import BrokerageApi
from ._openapi.api.messages_api import MessagesApi
from .auth import Authenticator, TanChallenge
from .domain.mappers import (
    map_account,
    map_depot,
    map_depot_balance,
    map_depot_position,
    map_document,
    map_transaction,
)
from .domain.models import (
    Account,
    Depot,
    DepotBalance,
    DepotPosition,
    Document,
    Transaction,
)
from .exceptions import AuthenticationError
from .utils import request_id

logger = logging.getLogger(__name__)


class ComdirectApiClient(ApiClient):
    """
    Subclass of generated ApiClient to inject the Authorization and dynamic x-http-request-info headers.
    """

    def __init__(
        self,
        session_id_provider: Callable[[], str | None],
        *args,
        token_provider: Callable[[], str | None] | None = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self._session_id_provider = session_id_provider
        self._token_provider = token_provider or (lambda: self.configuration.access_token)

    def call_api(
        self,
        method,
        url,
        header_params=None,
        body=None,
        post_params=None,
        _request_timeout=None,
    ):
        if header_params is None:
            header_params = {}

        # 1. Inject Authorization header (the provider refreshes an expiring token first)
        if "Authorization" not in header_params:
            access_token = self._token_provider()
            if access_token:
                header_params["Authorization"] = f"Bearer {access_token}"

        # 2. Inject x-http-request-info header if session exists
        session_id = self._session_id_provider()
        if session_id:
            request_info = {
                "clientRequestId": {
                    "sessionId": session_id,
                    "requestId": request_id(),
                }
            }
            header_params["x-http-request-info"] = json.dumps(request_info)

        # 3. Ensure Content-Type is valid for Comdirect (sometimes they are picky)
        if "Content-Type" not in header_params:
            header_params["Content-Type"] = "application/json"

        return super().call_api(
            method,
            url,
            header_params=header_params,
            body=body,
            post_params=post_params,
            _request_timeout=_request_timeout,
        )


class ComdirectClient:
    # Refresh the access token this many seconds before it expires.
    TOKEN_REFRESH_MARGIN = 60

    def __init__(self, credentials, tan_handlers=None):
        self._auth = Authenticator(**credentials, **(tan_handlers or {}))
        self._session_id: str | None = None
        self._refresh_token: str | None = None
        self._token_expires_at: float | None = None
        self._token_lock = threading.Lock()

        # Initialize OpenAPI client with default configuration
        config = Configuration(host="https://api.comdirect.de/api")
        # Session id and token are provided lazily, so a refreshed token is picked up by every request.
        self._api_client = ComdirectApiClient(
            session_id_provider=lambda: self._session_id,
            token_provider=self._valid_access_token,
            configuration=config,
        )

        # Instantiate generated API classes once
        self._banking = BankingApi(self._api_client)
        self._brokerage = BrokerageApi(self._api_client)
        self._messages = MessagesApi(self._api_client)

    @property
    def is_logged_in(self) -> bool:
        return self._session_id is not None and self._api_client.configuration.access_token is not None

    def login(self):
        """Runs the full login flow, resolving the TAN through the configured callbacks."""
        session_id, tokens = self._auth.authenticate()
        self._set_session(session_id, tokens)

    def start_login(self, tan_type: str | None = None) -> TanChallenge:
        """
        First half of a two-step login: triggers the 2FA challenge (e.g. the push notification).

        `tan_type` requests a TAN method ("P_TAN_PUSH", "P_TAN", "M_TAN"); default is the account's preferred one.
        """
        return self._auth.start(tan_type)

    def complete_login(self, challenge: TanChallenge, tan: str = ""):
        """Second half of a two-step login. Pass an empty TAN for an approved push TAN."""
        session_id, tokens = self._auth.complete(challenge, tan)
        self._set_session(session_id, tokens)

    def refresh_token(self):
        """Refreshes the access token. Normally not needed: requests refresh an expiring token automatically."""
        with self._token_lock:
            self._refresh_locked()

    def _set_session(self, session_id: str, tokens: dict[str, Any]):
        with self._token_lock:
            self._session_id = session_id
            self._store_tokens(tokens)

    def _store_tokens(self, tokens: dict[str, Any]):
        self._api_client.configuration.access_token = tokens["access_token"]
        self._refresh_token = tokens.get("refresh_token")
        expires_in = tokens.get("expires_in")
        self._token_expires_at = time.monotonic() + float(expires_in) if expires_in is not None else None

    def _refresh_locked(self):
        if not self._refresh_token:
            raise AuthenticationError("Session expired and no refresh token available. Please log in again.")
        try:
            tokens = self._auth.refresh(self._refresh_token)
        except AuthenticationError as e:
            self._clear_session()
            raise AuthenticationError("Session expired and token refresh failed. Please log in again.") from e
        self._store_tokens(tokens)

    def _valid_access_token(self) -> str | None:
        with self._token_lock:
            if self._api_client.configuration.access_token is None:
                return None
            if (
                self._token_expires_at is not None
                and time.monotonic() >= self._token_expires_at - self.TOKEN_REFRESH_MARGIN
            ):
                logger.info("Access token about to expire, refreshing")
                self._refresh_locked()
            return self._api_client.configuration.access_token

    def _clear_session(self):
        self._session_id = None
        self._refresh_token = None
        self._token_expires_at = None
        self._api_client.configuration.access_token = None

    def list_accounts(self) -> list[Account]:
        """
        Returns a list of domain Account objects.
        """
        res = self._banking.banking_v2_get_account_balances(user="user")
        return [map_account(b) for b in res.values or []]

    def list_transactions(
        self,
        account_id: str,
        with_account: bool = False,
        paging_first: int = 0,
        transaction_state: str | None = None,
        transaction_direction: str | None = None,
        min_booking_date: str | None = None,
        max_booking_date: str | None = None,
    ) -> list[Transaction]:
        """
        Returns a list of domain Transaction objects.
        """
        return list(
            self.iter_all_transactions(
                account_id=account_id,
                with_account=with_account,
                paging_first=paging_first,
                transaction_state=transaction_state,
                transaction_direction=transaction_direction,
                min_booking_date=min_booking_date,
                max_booking_date=max_booking_date,
            )
        )

    def iter_all_transactions(
        self,
        account_id: str,
        with_account: bool = False,
        paging_first: int = 0,
        transaction_state: str | None = "BOOKED",
        transaction_direction: str | None = None,
        min_booking_date: str | None = None,
        max_booking_date: str | None = None,
    ) -> Iterator[Transaction]:
        """
        Iterates over all transactions for an account, handling pagination automatically.
        Note: The API only supports paging for 'BOOKED' transactions.
        """
        if transaction_state not in (None, "BOOKED"):
            res = self._get_account_transactions_page(
                account_id=account_id,
                with_account=with_account,
                paging_first=paging_first,
                transaction_state=transaction_state,
                transaction_direction=transaction_direction,
                min_booking_date=min_booking_date,
                max_booking_date=max_booking_date,
            )
            yield from [map_transaction(tx, account_id) for tx in res.values]
            return

        offset = paging_first or 0
        while True:
            res = self._get_account_transactions_page(
                account_id=account_id,
                with_account=with_account,
                paging_first=offset,
                transaction_state="BOOKED",
                transaction_direction=transaction_direction,
                min_booking_date=min_booking_date,
                max_booking_date=max_booking_date,
            )
            if not res.values:
                break
            yield from [map_transaction(tx, account_id) for tx in res.values]
            offset += len(res.values)

    def _get_account_transactions_page(
        self,
        account_id: str,
        with_account: bool,
        paging_first: int,
        transaction_state: str | None,
        transaction_direction: str | None,
        min_booking_date: str | None,
        max_booking_date: str | None,
    ):
        with_attr = "account" if with_account else None
        query_params: list[tuple[str, Any]] = []
        if transaction_state is not None:
            query_params.append(("transactionState", transaction_state))
        if transaction_direction is not None:
            query_params.append(("transactionDirection", transaction_direction))
        if paging_first is not None:
            query_params.append(("paging-first", paging_first))
        if with_attr:
            query_params.append(("with-attr", with_attr))
        if min_booking_date:
            query_params.append(("min-bookingDate", min_booking_date))
        if max_booking_date:
            query_params.append(("max-bookingDate", max_booking_date))
        # manual call because the generated banking client omits booking-date params.
        method, url, header_params, body, post_params = self._api_client.param_serialize(
            method="GET",
            resource_path="/banking/v1/accounts/{accountId}/transactions",
            path_params={"accountId": account_id},
            query_params=query_params,
            header_params={
                "Accept": self._api_client.select_header_accept(["application/json"]),
            },
            body=None,
            post_params=[],
            files=None,
            auth_settings=[],
            collection_formats={},
        )
        response_data = self._api_client.call_api(
            method,
            url,
            header_params=header_params,
            body=body,
            post_params=post_params,
        )
        response_data.read()
        return self._api_client.response_deserialize(
            response_data=response_data,
            response_types_map={
                "200": "ListResourceAccountTransaction",
                "404": None,
                "422": None,
                "500": None,
            },
        ).data

    def list_depots(self) -> list[Depot]:
        """
        Returns a list of Depot objects.
        """
        res = self._brokerage.brokerage_v3_get_depots(user_id="user")
        return [map_depot(d) for d in res.values or []]

    def get_depot_positions(self, depot_id: str) -> tuple[DepotBalance, list[DepotPosition]]:
        """
        Returns (DepotBalance, List[DepotPosition]).
        """
        # Instrument data (name, ISIN) is only returned when requested explicitly.
        res = self._brokerage.brokerage_v3_get_depot_positions(depot_id, with_attr="instrument")
        balance = map_depot_balance(res.aggregated, depot_id)
        positions = [map_depot_position(p) for p in res.values or []]
        return balance, positions

    def list_documents(self, paging_first=0, paging_count=1000) -> list[Document]:
        """
        Returns a list of Document objects.
        """
        res = self._messages.messages_v2_get_documents(
            user="user", paging_first=paging_first, paging_count=paging_count
        )
        return [map_document(d) for d in res.values or []]

    def download_document(self, document_id: str, mime_type: str) -> bytes:
        """
        Downloads a document.
        """
        # Pass Accept header via _headers argument; ApiResponse (http_info) exposes the raw bytes.
        response = self._messages.messages_v2_get_document_with_http_info(document_id, _headers={"Accept": mime_type})
        return response.raw_data

    def logout(self):
        """
        Revokes the session at comdirect (best effort) and clears it locally.

        comdirect rejects the refresh token right away, but the last access token stays valid until it expires.
        """
        with self._token_lock:
            access_token = self._api_client.configuration.access_token
            self._clear_session()
        if access_token:
            try:
                self._auth.revoke(access_token)
            except AuthenticationError as e:
                # Expired or already revoked tokens cannot be revoked; the session is gone either way.
                logger.info("Token revocation failed: %s", e)
