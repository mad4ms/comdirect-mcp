import json
import logging
import re
import threading
import time
from collections.abc import Callable, Iterator
from datetime import date
from typing import Any

from ._openapi import ApiClient, Configuration
from ._openapi.api.banking_api import BankingApi
from ._openapi.api.brokerage_api import BrokerageApi
from ._openapi.api.messages_api import MessagesApi
from ._openapi.exceptions import ApiException
from .auth import Authenticator, TanChallenge
from .domain.mappers import (
    map_account,
    map_card,
    map_depot,
    map_depot_balance,
    map_depot_position,
    map_depot_transaction,
    map_dimensions,
    map_document,
    map_instrument,
    map_order,
    map_transaction,
    map_wealth_overview,
)
from .domain.models import (
    Account,
    Card,
    Depot,
    DepotBalance,
    DepotPosition,
    DepotTransaction,
    Document,
    Instrument,
    Order,
    OrderDimensions,
    Transaction,
    WealthOverview,
)
from .exceptions import AuthenticationError, DataError, TransactionFilterError
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

    def get_account_balance(self, account_id: str) -> Account:
        """Fetch the balance and static data of one account."""
        return map_account(self._get_json("/banking/v2/accounts/{accountId}/balances", [], {"accountId": account_id}))

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
        try:
            lower = date.fromisoformat(min_booking_date) if min_booking_date else None
            upper = date.fromisoformat(max_booking_date) if max_booking_date else None
        except ValueError as error:
            raise TransactionFilterError("Booking-date filters must be YYYY-MM-DD dates.") from error
        if lower and upper and lower > upper:
            raise TransactionFilterError("min_booking_date must be on or before max_booking_date.")
        if transaction_state == "NOTBOOKED" and (lower or upper):
            raise TransactionFilterError("Pending transactions have no booking date; omit booking-date filters.")
        directions = {
            "INCOMING": "CREDIT",
            "OUTGOING": "DEBIT",
            "CREDIT": "CREDIT",
            "DEBIT": "DEBIT",
            "CREDIT_AND_DEBIT": "CREDIT_AND_DEBIT",
        }
        if transaction_direction is not None and transaction_direction not in directions:
            raise TransactionFilterError("Use INCOMING or OUTGOING as transaction_direction.")
        api_direction = directions.get(transaction_direction) if transaction_direction else None

        def matching(values):
            for value in values or []:
                tx = map_transaction(value, account_id)
                if lower or upper:
                    if tx.booking_date is None:
                        raise TransactionFilterError("A transaction has no booking date; omit booking-date filters.")
                    if (lower and tx.booking_date < lower) or (upper and tx.booking_date > upper):
                        continue
                if api_direction in ("CREDIT", "DEBIT"):
                    if tx.amount is None:
                        raise TransactionFilterError("A transaction has no amount; omit the direction filter.")
                    if (api_direction == "CREDIT" and tx.amount <= 0) or (api_direction == "DEBIT" and tx.amount >= 0):
                        continue
                yield tx

        if transaction_state not in (None, "BOOKED"):
            res = self._get_account_transactions_page(
                account_id=account_id,
                with_account=with_account,
                paging_first=paging_first,
                transaction_state=transaction_state,
                transaction_direction=api_direction,
                min_booking_date=min_booking_date,
                max_booking_date=max_booking_date,
            )
            yield from matching(res.values)
            return

        offset = paging_first or 0
        while True:
            res = self._get_account_transactions_page(
                account_id=account_id,
                with_account=with_account,
                paging_first=offset,
                transaction_state="BOOKED",
                transaction_direction=api_direction,
                min_booking_date=min_booking_date,
                max_booking_date=max_booking_date,
            )
            if not res.values:
                break
            yield from matching(res.values)
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
        # Account date filters are applied locally; the bank can ignore unknown query parameters.
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

    def list_cards(self) -> list[Card]:
        """
        Returns the cards (e.g. Visa) with their balances, from the balance report of all products.

        The API offers card balances only, no card transactions.
        """
        report = self._get_json(
            "/reports/participants/user/v1/allbalances",
            [("productType", "CARD")],
        )
        products = report.get("values") or []
        return [map_card(p) for p in products if p.get("productType") == "CARD"]

    def _get_json(
        self, resource_path: str, query_params: list[tuple[str, Any]], path_params: dict[str, str] | None = None
    ) -> dict[str, Any]:
        """GET returning the decoded JSON, for responses the generated models do not describe correctly."""
        method, url, header_params, body, post_params = self._api_client.param_serialize(
            method="GET",
            resource_path=resource_path,
            path_params=path_params or {},
            query_params=query_params,
            header_params={"Accept": "application/json"},
            auth_settings=[],
        )
        response = self._api_client.call_api(
            method, url, header_params=header_params, body=body, post_params=post_params
        )
        response.read()
        if not 200 <= response.status < 300:
            raise ApiException(http_resp=response)
        return json.loads(response.data or b"{}")

    def get_wealth_overview(self) -> WealthOverview:
        """All product balances and the bank's EUR aggregates, without currency conversion or sign changes."""
        return map_wealth_overview(self._get_json("/reports/participants/user/v1/allbalances", []))

    def get_instrument(
        self, identifier: str, verbose: bool = False, include_order_dimensions: bool = False
    ) -> Instrument:
        """Resolve a WKN, ISIN or case-sensitive symbol; optionally request fund and derivative details."""
        attributes = ["fundDistribution", "derivativeData"] if verbose else []
        if include_order_dimensions:
            attributes.append("orderDimensions")
        query = [("with-attr", ",".join(attributes))] if attributes else []
        report = self._get_json("/brokerage/v1/instruments/{instrumentId}", query, {"instrumentId": identifier})
        values = report.get("values") or []
        if len(values) != 1:
            raise DataError("Instrument lookup did not return exactly one match. Use a WKN or ISIN.")
        return map_instrument(values[0])

    def get_order_dimensions(
        self, identifier: str, venue_id: str | None = None, side: str | None = None, order_type: str | None = None
    ) -> OrderDimensions:
        """Read tradability metadata; does not validate, create or change an order."""
        key = (
            "isin"
            if re.fullmatch(r"[A-Z]{2}[A-Z0-9]{10}", identifier)
            else "wkn"
            if re.fullmatch(r"[A-Z0-9]{6}", identifier)
            else "instrumentId"
        )
        query = [(key, identifier)]
        query.extend(
            (key, value) for key, value in (("venueId", venue_id), ("side", side), ("orderType", order_type)) if value
        )
        report = self._get_json("/brokerage/v3/orders/dimensions", query)
        values = report.get("values") or []
        if len(values) != 1:
            raise DataError("Order dimensions did not return exactly one match. Use a WKN or ISIN.")
        return map_dimensions(values[0])

    def list_orders(
        self,
        depot_id: str,
        status: str | None = None,
        side: str | None = None,
        order_type: str | None = None,
        venue_id: str | None = None,
    ) -> list[Order]:
        """Read the depot order book, following bank pages and applying filters locally as well."""
        filters = [
            (key, value)
            for key, value in (
                ("orderStatus", status),
                ("side", side),
                ("orderType", order_type),
                ("venueId", venue_id),
            )
            if value is not None
        ]
        rows: list[dict[str, Any]] = []
        first = 0
        matches = None
        seen: set[str] = set()
        seen_ids: set[str] = set()
        for _ in range(100):
            report = self._get_json(
                "/brokerage/depots/{depotId}/v3/orders",
                [("with-attr", "instrument"), *filters, ("paging-first", first), ("paging-count", 500)],
                {"depotId": depot_id},
            )
            page = report.get("values") or []
            paging = report.get("paging") or {}
            count = paging.get("matches")
            if matches is not None and count is not None and count != matches:
                raise DataError("Order count changed while paging. Narrow the filters and try again.")
            if count is not None:
                matches = count
            key = json.dumps(page, sort_keys=True)
            ids = {row["orderId"] for row in page if row.get("orderId")}
            if (paging.get("index") is not None and paging["index"] != first) or (
                first and (key in seen or ids & seen_ids)
            ):
                raise DataError("Bank returned an incomplete order list: paging did not advance. Narrow the filters.")
            seen.add(key)
            seen_ids.update(ids)
            rows.extend(page)
            first += len(page)
            if matches is None or first >= matches:
                break
            if not page:
                raise DataError(
                    "Bank returned an incomplete order list: an expected page is empty. Narrow the filters."
                )
        else:
            raise DataError("Order paging exceeded 100 pages. Narrow the filters.")
        return [map_order(row) for row in rows if all(row.get(key) == value for key, value in filters)]

    def get_order(self, order_id: str) -> Order:
        """Read one order, including executions and combination-order legs."""
        return map_order(self._get_json("/brokerage/v3/orders/{orderId}", [], {"orderId": order_id}))

    def list_depot_transactions(
        self,
        depot_id: str,
        isin: str | None = None,
        min_booking_date: date | None = None,
        max_booking_date: date | None = None,
    ) -> list[DepotTransaction]:
        """Depot movements; booking dates are also checked locally rather than trusting upstream filters."""
        if min_booking_date and max_booking_date and min_booking_date > max_booking_date:
            raise TransactionFilterError("min_booking_date must be on or before max_booking_date.")
        query = []
        if isin:
            query.append(("isin", isin))
        if max_booking_date:
            query.append(("max-bookingDate", max_booking_date.isoformat()))
        values: list[dict[str, Any]] = []
        first = 0
        seen_pages: set[str] = set()
        seen_ids: set[str] = set()
        matches: int | None = None
        for _ in range(100):
            report = self._get_json(
                "/brokerage/v3/depots/{depotId}/transactions",
                [*query, ("paging-first", first), ("paging-count", 500)],
                {"depotId": depot_id},
            )
            page = report.get("values") or []
            paging = report.get("paging") or {}
            reported_matches = paging.get("matches")
            if reported_matches is not None:
                if matches is not None and matches != reported_matches:
                    raise DataError("Depot transaction count changed while paging. Narrow the ISIN/date range.")
                matches = reported_matches
            index = paging.get("index")
            page_key = json.dumps(page, sort_keys=True)
            ids = {tx["transactionId"] for tx in page if tx.get("transactionId")}
            if (index is not None and index != first) or (first and (page_key in seen_pages or seen_ids & ids)):
                raise DataError("Bank returned an incomplete depot transaction list: paging did not advance.")
            seen_pages.add(page_key)
            seen_ids.update(ids)
            values.extend(page)
            first += len(page)
            if matches is None or first >= matches:
                break
            if not page:
                raise DataError("Bank returned an incomplete depot transaction list: an expected page is empty.")
        else:
            raise DataError("Depot transaction paging exceeded 100 pages. Narrow the ISIN/date range.")
        transactions = [map_depot_transaction(tx, depot_id) for tx in values]
        selected = []
        for tx in transactions:
            if min_booking_date or max_booking_date:
                if tx.booking_date is None:
                    raise TransactionFilterError("Depot transaction has no booking date; remove the date filters.")
                if min_booking_date and tx.booking_date < min_booking_date:
                    continue
                if max_booking_date and tx.booking_date > max_booking_date:
                    continue
            selected.append(tx)
        return selected

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
        matches = getattr(getattr(res, "paging", None), "matches", None)
        if isinstance(matches, int) and matches != len(res.values or []):
            raise DataError(
                "Bank returned an incomplete position list. Retry `get_depot_positions` before aggregation."
            )
        balance = map_depot_balance(res.aggregated, depot_id)
        positions = [map_depot_position(p) for p in res.values or []]
        return balance, positions

    def get_depot_position(self, depot_id: str, position_id: str) -> DepotPosition:
        """Read one position with instrument metadata."""
        report = self._get_json(
            "/brokerage/v3/depots/{depotId}/positions/{positionId}",
            [("with-attr", "instrument")],
            {"depotId": depot_id, "positionId": position_id},
        )
        if "values" not in report:
            return map_depot_position(report)
        values = report.get("values") or []
        if len(values) != 1:
            raise DataError("Position lookup did not return exactly one match. Refresh `get_depot_positions`.")
        return map_depot_position(values[0])

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

    def get_document_cover(self, document_id: str) -> bytes:
        """Read the HTML pre-document without loading links or executing active content."""
        method, url, headers, body, posts = self._api_client.param_serialize(
            method="GET",
            resource_path="/messages/v2/documents/{documentId}/predocument",
            path_params={"documentId": document_id},
            query_params=[],
            header_params={"Accept": "text/html"},
            auth_settings=[],
        )
        response = self._api_client.call_api(method, url, header_params=headers, body=body, post_params=posts)
        response.read()
        if not 200 <= response.status < 300:
            raise ApiException(http_resp=response)
        return response.data or b""

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
