"""
Runs ComdirectClient through the generated client (comdirect_mcp._openapi) down to urllib3, with only the HTTP
transport mocked. Catches incompatibilities between the generated code, pydantic and urllib3
that the API-level mocks in test_client.py cannot see.
"""

import io
import json
import unittest
from decimal import Decimal
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import urllib3

from comdirect_mcp.client import ComdirectClient

ACCOUNT_BALANCES = {
    "paging": {"index": 0, "matches": 1},
    "values": [
        {
            "account": {
                "accountId": "acc_1",
                "accountDisplayId": "1234567890",
                "currency": "EUR",
                "clientId": "cli_1",
                "accountType": {"key": "CA", "text": "Girokonto"},
                "iban": "DE75512108001245126199",
            },
            "accountId": "acc_1",
            "balance": {"value": "1234.56", "unit": "EUR"},
            "balanceEUR": {"value": "1234.56", "unit": "EUR"},
            "availableCashAmount": {"value": "2234.56", "unit": "EUR"},
            "availableCashAmountEUR": {"value": "2234.56", "unit": "EUR"},
        }
    ],
}


def _transaction(booking_date, amount):
    return {
        "reference": "ref",
        "bookingStatus": "BOOKED" if booking_date else "NOTBOOKED",
        "bookingDate": booking_date,
        "amount": {"value": amount, "unit": "EUR"},
        "remitter": None,
        "deptor": None,
        "creditor": {"holderName": "Shop", "iban": "DE89370400440532013000", "bic": "COBADEFFXXX"},
        "valutaDate": booking_date,
        "remittanceInfo": "01" + "Einkauf Beispielhandel Bonn XYZ Gmb" + "02" + "H".ljust(35),
        "transactionType": {"key": "DIRECT_DEBIT", "text": "Lastschrift"},
        "newTransaction": False,
    }


DEPOT_POSITIONS = {
    "paging": {"index": 0, "matches": 1},
    # Real API shape: depot nested, no top-level depotId (found in a live test)
    "aggregated": {
        "depot": {"depotId": "dep_1", "depotDisplayId": "123", "clientId": "cli_1"},
        "dateLastUpdate": "2026-10-09",
        "currentValue": {"value": "1100.00", "unit": "EUR"},
        "purchaseValue": {"value": "1000.00", "unit": "EUR"},
        "prevDayValue": {"value": "1090.00", "unit": "EUR"},
        "profitLossPurchaseAbs": {"value": "100.00", "unit": "EUR"},
        "profitLossPurchaseRel": "10.00",
        "profitLossPrevDayAbs": {"value": "10.00", "unit": "EUR"},
        "profitLossPrevDayRel": "0.92",
    },
    "values": [
        {
            "depotId": "dep_1",
            "positionId": "pos_1",
            "wkn": "A0RPWH",
            "custodyType": "CAR",
            "quantity": {"value": "10", "unit": "XXX"},
            "currentValue": {"value": "1100.00", "unit": "EUR"},
            "purchaseValue": {"value": "1000.00", "unit": "EUR"},
            "profitLossPurchaseAbs": {"value": "100.00", "unit": "EUR"},
            "profitLossPurchaseRel": "10.00",
            "instrument": {
                "instrumentId": "ins_1",
                "wkn": "A0RPWH",
                "isin": "IE00B4L5Y983",
                "name": "iShares MSCI World",
            },
        }
    ],
}

ALL_BALANCES = {
    "paging": {"index": 0, "matches": 2},
    "aggregated": {"balanceEUR": {"value": "958.00", "unit": "EUR"}},
    "values": [
        {
            "productId": "c1",
            "productType": "CARD",
            "targetClientId": "cli_1",
            "clientConnectionType": "CURRENT_CLIENT",
            "balance": {
                "cardId": "c1",
                "card": {
                    "cardId": "c1",
                    "cardType": {"key": "VISA_PREPAID", "text": "Visa-Karte (Prepaid-Kreditkarte)"},
                    "primaryAccountNumberSuffix": "4242",
                    "cardLimit": {"value": "1000.00", "unit": "EUR"},
                    "status": "ACTIVE",
                },
                "balance": {"value": "-42.00", "unit": "EUR"},
                "availableCashAmount": {"value": "958.00", "unit": "EUR"},
            },
        },
        # products of other types are filtered out by the client
        {"productId": "a1", "productType": "ACCOUNT", "balance": {"accountId": "a1"}},
    ],
}

DOCUMENTS = {
    "paging": {"index": 0, "matches": 1},
    "values": [
        {
            "documentId": "doc_1",
            "name": "Finanzreport Nr. 09 per 30.09.2026",
            "dateCreation": "2026-10-01",
            "mimeType": "application/pdf",
            "deletable": False,
            "advertisement": False,
            "documentMetaData": {"archived": False, "alreadyRead": False, "predocumentExists": False},
        }
    ],
}


WEALTH_REPORT = {
    "paging": {"index": 0, "matches": 5},
    "aggregated": {
        "balanceEUR": {"value": "758.00", "unit": "EUR"},
        "availableCashAmountEUR": {"value": "110.00", "unit": "EUR"},
    },
    "values": [
        {
            "productId": "a1",
            "productType": "ACCOUNT",
            "balance": {
                "account": {"accountDisplayId": "1234567890", "accountType": {"key": "CA", "text": "Girokonto"}},
                "balance": {"value": "100", "unit": "EUR"},
                "availableCashAmount": {"value": "110", "unit": "EUR"},
            },
        },
        ALL_BALANCES["values"][0],
        {
            "productId": "dep_1",
            "productType": "DEPOT",
            "balance": {"depot": {"depotDisplayId": "9876543210"}, "currentValue": {"value": "1000", "unit": "EUR"}},
        },
        {
            "productId": "loan_1",
            "productType": "LOAN",
            "balance": {
                "installmentLoan": {"productDisplayId": "1122334455"},
                "balance": {"value": "-500", "unit": "EUR"},
            },
        },
        {
            "productId": "sav_1",
            "productType": "SAVINGS",
            "balance": {
                "savingsAmount": {"value": "200", "unit": "EUR"},
                "fixedTermSavingsType": {"key": "FIXED", "text": "Fixed term"},
            },
        },
    ],
}

INSTRUMENT = {
    "instrumentId": "instrument_1",
    "name": "Example Fund",
    "isin": "DE0001234567",
    "wkn": "123456",
    "staticData": {"instrumentType": "ETF", "currency": "EUR", "notation": "XXX", "kidAvailable": False},
    "fundsDistribution": {
        "totalExpenseRatio": "0.20",
        "investmentCategory": "Equity",
        "fundFlags": ["ETF"],
        "rating": {"morningstar": "4"},
    },
    "derivativeData": {
        "underlyingInstrument": {"name": "Example Share", "isin": "DE0007654321"},
        "strikePrice": {"value": "123.45", "unit": "USD"},
        "leverage": "2.5",
        "expiryDate": "2027-06-30",
    },
}

DEPOT_TRANSACTIONS = {
    "paging": {"index": 0, "matches": 2},
    "values": [
        {
            "transactionId": "movement_1",
            "bookingDate": "2026-10-08",
            "bookingStatus": "BOOKED",
            "instrument": {"name": "Example Fund", "isin": "DE0001234567", "wkn": "123456"},
            "transactionDirection": "IN",
            "transactionType": {"key": "BUY", "text": "Kauf"},
            "quantity": {"value": "2", "unit": "XXX"},
            "executionPrice": {"value": "10", "unit": "EUR"},
            "transactionValue": {"value": "20", "unit": "EUR"},
        },
        {
            "transactionId": "movement_2",
            "bookingDate": "2026-10-09",
            "bookingStatus": "BOOKED",
            "instrument": {"name": "Example Fund", "isin": "DE0001234567"},
            "transactionDirection": "OUT",
            "transactionType": "SELL",
            "transactionValue": {"value": "15", "unit": "EUR"},
        },
    ],
}


ORDER = {
    "orderId": "order_1",
    "depotId": "dep_1",
    "instrumentId": "DE0001234567",
    "instrument": {"name": "Example Fund", "isin": "DE0001234567"},
    "orderStatus": "OPEN",
    "orderType": "LIMIT",
    "side": "BUY",
    "quantity": {"value": "3", "unit": "XXX"},
    "openQuantity": {"value": "2", "unit": "XXX"},
    "limit": {"value": "10.50", "unit": "EUR"},
    "validity": "2026-10-31",
    "bestEx": False,
    "executions": [
        {
            "executionId": "exec_1",
            "executedQuantity": {"value": "1", "unit": "XXX"},
            "executionPrice": {"value": "10", "unit": "EUR"},
            "executionTimestamp": "2026-10-09T12:00:00Z",
        }
    ],
    "subOrders": [{"orderId": "leg_1", "orderType": "STOP_LIMIT", "side": "SELL"}],
}
ORDER_DIMENSIONS = {
    "venues": [
        {
            "venueId": "venue_1",
            "name": "Example Exchange",
            "type": "EXCHANGE",
            "currencies": ["EUR"],
            "sides": ["BUY", "SELL"],
            "validityTypes": ["GFD", "GTD"],
            "orderTypes": {"LIMIT": {"limitExtensions": ["IOC"], "tradingRestrictions": []}},
        }
    ]
}


def synthetic_pdf():
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = PdfWriter()
    for text in ("Synthetic statement page one", "Synthetic statement page two"):
        page = writer.add_blank_page(width=200, height=200)
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
        )
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 10 100 Td ({text}) Tj ET".encode())
        page[NameObject("/Contents")] = writer._add_object(stream)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


class FakeComdirect:
    """Answers requests like api.comdirect.de and records them."""

    def __init__(self):
        self.requests = []
        self.unbooked = False

    def __call__(self, method, url, **kwargs):
        self.requests.append((method, url, kwargs.get("headers", {})))
        parsed = urlparse(url)
        path, query = parsed.path, parse_qs(parsed.query)

        if path.endswith("/banking/clients/user/v2/accounts/balances"):
            return self._json(ACCOUNT_BALANCES)
        if path.endswith("/banking/v2/accounts/acc_1/balances"):
            return self._json(ACCOUNT_BALANCES["values"][0])
        if path.endswith("/brokerage/v3/orders/dimensions"):
            if query.get("instrumentId") == ["DE0001234567"]:
                return urllib3.HTTPResponse(body=b"{}", status=422, preload_content=True)
            return self._json({"values": [ORDER_DIMENSIONS]})
        if path.endswith("/brokerage/depots/dep_1/v3/orders"):
            rows = [ORDER, {**ORDER, "orderId": "order_2", "side": "SELL", "orderStatus": "SETTLED"}]
            first = int(query.get("paging-first", ["0"])[0])
            return self._json({"paging": {"index": first, "matches": 2}, "values": rows[first : first + 1]})
        if path.endswith("/brokerage/v3/orders/order_1"):
            return self._json(ORDER)
        if path.endswith("/banking/v1/accounts/acc_1/transactions"):
            if query.get("transactionState") == ["NOTBOOKED"]:
                pending = {**_transaction(None, "-5.00"), "valutaDate": "2026-02-30"}  # docs: may be no real date
                return self._json({"paging": {"index": 0, "matches": 1}, "values": [pending]})
            direction = query.get("transactionDirection", [None])[0]
            if direction not in (None, "CREDIT", "DEBIT", "CREDIT_AND_DEBIT"):
                return urllib3.HTTPResponse(body=b"{}", status=422, reason="Unprocessable", preload_content=True)
            first = int(query.get("paging-first", ["0"])[0])
            pages = [[_transaction("2026-10-09", "-12.34"), _transaction("2026-10-08", "100.00")], []]
            selected = pages[0]
            if direction in ("CREDIT", "DEBIT"):
                selected = [tx for tx in selected if (Decimal(tx["amount"]["value"]) > 0) == (direction == "CREDIT")]
            values = selected if first == 0 else pages[1]
            return self._json({"paging": {"index": first, "matches": 2}, "values": values})
        if path.endswith("/brokerage/v3/depots/dep_1/transactions"):
            # Ignore dates deliberately: the client must enforce them too.
            values = DEPOT_TRANSACTIONS["values"]
            if query.get("isin"):
                values = [tx for tx in values if (tx.get("instrument") or {}).get("isin") == query["isin"][0]]
            first = int(query.get("paging-first", ["0"])[0])
            count = min(int(query.get("paging-count", ["500"])[0]), 2)
            return self._json(
                {"paging": {"index": first, "matches": len(values)}, "values": values[first : first + count]}
            )
        if path.endswith("/brokerage/v1/instruments/DE0001234567"):
            attrs = query.get("with-attr", [""])[0].split(",")
            value = {
                k: v
                for k, v in INSTRUMENT.items()
                if k not in ("fundsDistribution", "derivativeData")
                or (k == "fundsDistribution" and "fundDistribution" in attrs)
                or (k == "derivativeData" and "derivativeData" in attrs)
            }
            if "orderDimensions" in attrs:
                value = {**value, "orderDimensions": ORDER_DIMENSIONS}
            return self._json({"values": [value]})
        if path.endswith("/brokerage/v3/depots/dep_1/positions/pos_1"):
            # The live single-position endpoint returns an object, not a values envelope.
            return self._json(DEPOT_POSITIONS["values"][0])
        if path.endswith("/brokerage/clients/user/v3/depots"):
            return self._json({"values": [{"depotId": "dep_1", "depotDisplayId": "1234567890"}]})
        if path.endswith("/brokerage/v3/depots/dep_1/positions"):
            # Like the live API: instrument data only with with-attr=instrument
            if query.get("with-attr") == ["instrument"]:
                return self._json(DEPOT_POSITIONS)
            values = [{k: v for k, v in p.items() if k != "instrument"} for p in DEPOT_POSITIONS["values"]]
            return self._json({**DEPOT_POSITIONS, "values": values})
        if path.endswith("/reports/participants/user/v1/allbalances"):
            return self._json(ALL_BALANCES if query.get("productType") == ["CARD"] else WEALTH_REPORT)
        if path.endswith("/messages/clients/user/v2/documents"):
            first = int(query.get("paging-first", ["0"])[0])
            count = int(query.get("paging-count", ["1000"])[0])
            return self._json({**DOCUMENTS, "values": DOCUMENTS["values"][first : first + count]})
        if path.endswith("/messages/v2/documents/doc_1"):
            return urllib3.HTTPResponse(
                body=synthetic_pdf(), status=200, headers={"Content-Type": "application/pdf"}, preload_content=True
            )
        if path.endswith("/messages/v2/documents/doc_1/predocument"):
            return urllib3.HTTPResponse(
                body=b"<p>Synthetic cover</p><script>never execute</script>",
                status=200,
                headers={"Content-Type": "text/html"},
                preload_content=True,
            )
        return urllib3.HTTPResponse(body=b"{}", status=404, reason="Not Found", preload_content=True)

    @staticmethod
    def _json(payload):
        return urllib3.HTTPResponse(
            body=json.dumps(payload).encode(),
            status=200,
            headers={"Content-Type": "application/json"},
            preload_content=True,
        )


class TestHttpRoundtrip(unittest.TestCase):
    def setUp(self):
        self.fake = FakeComdirect()
        patcher = patch.object(urllib3.PoolManager, "request", side_effect=self.fake)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.client = ComdirectClient({"client_id": "c", "client_secret": "s", "username": "u", "password": "p"})
        self.client._set_session("sess_1", {"access_token": "tok", "refresh_token": "r", "expires_in": 599})

    def test_sparse_documents_preserve_unknown_flags_through_transport(self):
        with patch.dict(DOCUMENTS, {"values": [{}]}):
            (document,) = self.client.list_documents()
        self.assertIsNone(document.advertisement)
        self.assertIsNone(document.already_read)
        self.assertIsNone(document.id)

    def test_requests_carry_auth_and_session_headers(self):
        self.client.list_accounts()

        method, url, headers = self.fake.requests[0]
        self.assertEqual(method, "GET")
        self.assertTrue(url.startswith("https://api.comdirect.de/api/"))
        self.assertEqual(headers["Authorization"], "Bearer tok")
        self.assertEqual(json.loads(headers["x-http-request-info"])["clientRequestId"]["sessionId"], "sess_1")

    def test_list_accounts(self):
        (account,) = self.client.list_accounts()

        self.assertEqual(account.id, "acc_1")
        self.assertEqual((account.type, account.type_name, account.display_id), ("CA", "Girokonto", "1234567890"))
        self.assertEqual(str(account.balance), "1234.56")
        self.assertEqual(str(account.available), "2234.56")

    def test_list_transactions_paginates(self):
        transactions = self.client.list_transactions("acc_1", min_booking_date="2026-10-01")

        self.assertEqual([str(tx.amount) for tx in transactions], ["-12.34", "100.00"])
        self.assertEqual(transactions[0].booking_date.isoformat(), "2026-10-09")
        self.assertEqual(transactions[0].creditor.iban, "DE89370400440532013000")
        self.assertEqual(transactions[0].type, "DIRECT_DEBIT")
        first_query = parse_qs(urlparse(self.fake.requests[0][1]).query)
        self.assertNotIn("min-bookingDate", first_query)
        self.assertNotIn("max-bookingDate", first_query)
        self.assertEqual(len(self.fake.requests), 2)  # second page is empty

    def test_date_filters_are_enforced_when_bank_ignores_them(self):
        transactions = self.client.list_transactions(
            "acc_1", min_booking_date="2026-10-08", max_booking_date="2026-10-08"
        )
        self.assertEqual(len(transactions), 1)
        self.assertEqual(transactions[0].booking_date.isoformat(), "2026-10-08")

    def test_direction_filters_use_banking_values(self):
        for direction, expected, query_value in (("INCOMING", "in", "CREDIT"), ("OUTGOING", "out", "DEBIT")):
            transactions = self.client.list_transactions("acc_1", transaction_direction=direction)
            self.assertEqual(len(transactions), 1)
            self.assertEqual(transactions[0].direction, expected)
            query = parse_qs(urlparse(self.fake.requests[-1][1]).query)
            self.assertEqual(query["transactionDirection"], [query_value])

    def test_unbooked_transactions_have_no_booking_date(self):
        (tx,) = self.client.list_transactions("acc_1", transaction_state="NOTBOOKED")

        self.assertIsNone(tx.booking_date)
        self.assertEqual(tx.booking_status, "NOTBOOKED")
        self.assertEqual(tx.valuta_date, "2026-02-30")

    def test_depot_positions(self):
        balance, (position,) = self.client.get_depot_positions("dep_1")

        self.assertEqual(balance.depot_id, "dep_1")
        self.assertEqual(str(balance.current_value), "1100.00")
        self.assertEqual(balance.profit_loss_purchase_rel, "10.00")
        self.assertEqual(position.instrument_name, "iShares MSCI World")
        self.assertEqual(position.isin, "IE00B4L5Y983")
        self.assertEqual(str(position.quantity), "10")

    def test_documents(self):
        (doc,) = self.client.list_documents()
        content = self.client.download_document(doc.id, doc.mime_type)

        self.assertEqual(doc.name, "Finanzreport Nr. 09 per 30.09.2026")
        self.assertIs(doc.already_read, False)
        self.assertTrue(content.startswith(b"%PDF"))
        self.assertEqual(self.fake.requests[-1][2]["Accept"], "application/pdf")

    def test_purpose_is_normalized_and_counterparty_derived(self):
        tx = self.client.list_transactions("acc_1")[0]

        self.assertEqual(tx.purpose, "Einkauf Beispielhandel Bonn XYZ GmbH")
        self.assertTrue(tx.purpose_raw.startswith("01Einkauf"))
        self.assertEqual((tx.direction, tx.counterparty.holder_name), ("out", "Shop"))

    def test_list_cards(self):
        (card,) = self.client.list_cards()

        self.assertEqual((card.type, card.number_suffix, card.status), ("VISA_PREPAID", "4242", "ACTIVE"))
        self.assertEqual((str(card.balance), str(card.available), str(card.limit)), ("-42.00", "958.00", "1000.00"))
        query = parse_qs(urlparse(self.fake.requests[-1][1]).query)
        self.assertEqual(query["productType"], ["CARD"])


if __name__ == "__main__":
    unittest.main()


def test_pending_date_filters_fail_before_network():
    from comdirect_mcp.exceptions import TransactionFilterError

    client = ComdirectClient({"client_id": "c", "client_secret": "s", "username": "u", "password": "p"})
    with patch.object(client, "_get_account_transactions_page") as transport:
        import pytest

        with pytest.raises(TransactionFilterError, match="Pending transactions"):
            client.list_transactions("synthetic", transaction_state="NOTBOOKED", min_booking_date="2026-01-01")
        transport.assert_not_called()
