"""
Runs ComdirectClient through the generated client (comdirect_mcp._openapi) down to urllib3, with only the HTTP
transport mocked. Catches incompatibilities between the generated code, pydantic and urllib3
that the API-level mocks in test_client.py cannot see.
"""

import json
import unittest
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
                "iban": "DE89370400440532013000",
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
        "remittanceInfo": "01Einkauf",
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
        if path.endswith("/banking/v1/accounts/acc_1/transactions"):
            if query.get("transactionState") == ["NOTBOOKED"]:
                pending = {**_transaction(None, "-5.00"), "valutaDate": "2026-02-30"}  # docs: may be no real date
                return self._json({"paging": {"index": 0, "matches": 1}, "values": [pending]})
            first = int(query.get("paging-first", ["0"])[0])
            pages = [[_transaction("2026-10-09", "-12.34"), _transaction("2026-10-08", "100.00")], []]
            values = pages[0] if first == 0 else pages[1]
            return self._json({"paging": {"index": first, "matches": 2}, "values": values})
        if path.endswith("/brokerage/v3/depots/dep_1/positions"):
            # Like the live API: instrument data only with with-attr=instrument
            if query.get("with-attr") == ["instrument"]:
                return self._json(DEPOT_POSITIONS)
            values = [{k: v for k, v in p.items() if k != "instrument"} for p in DEPOT_POSITIONS["values"]]
            return self._json({**DEPOT_POSITIONS, "values": values})
        if path.endswith("/messages/clients/user/v2/documents"):
            return self._json(DOCUMENTS)
        if path.endswith("/messages/v2/documents/doc_1"):
            return urllib3.HTTPResponse(
                body=b"%PDF-1.7", status=200, headers={"Content-Type": "application/pdf"}, preload_content=True
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
        self.assertEqual(str(account.balance), "1234.56")
        self.assertEqual(str(account.available), "2234.56")

    def test_list_transactions_paginates(self):
        transactions = self.client.list_transactions("acc_1", min_booking_date="2026-10-01")

        self.assertEqual([str(tx.amount) for tx in transactions], ["-12.34", "100.00"])
        self.assertEqual(transactions[0].booking_date.isoformat(), "2026-10-09")
        self.assertEqual(transactions[0].creditor.iban, "DE89370400440532013000")
        self.assertEqual(transactions[0].type, "DIRECT_DEBIT")
        first_query = parse_qs(urlparse(self.fake.requests[0][1]).query)
        self.assertEqual(first_query["min-bookingDate"], ["2026-10-01"])
        self.assertEqual(len(self.fake.requests), 2)  # second page is empty

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
        self.assertEqual(content, b"%PDF-1.7")
        self.assertEqual(self.fake.requests[-1][2]["Accept"], "application/pdf")


if __name__ == "__main__":
    unittest.main()
