import unittest
from decimal import Decimal
from unittest.mock import MagicMock, patch

from comdirect_mcp.auth import TanChallenge
from comdirect_mcp.client import ComdirectApiClient, ComdirectClient
from comdirect_mcp.domain.models import Account
from comdirect_mcp.exceptions import AuthenticationError


class TestComdirectClient(unittest.TestCase):
    def setUp(self):
        self.credentials = {
            "client_id": "cid",
            "client_secret": "csec",
            "username": "user",
            "password": "pwd",
        }
        self.tan_handlers = {}

        # Patching dependencies
        self.auth_patcher = patch("comdirect_mcp.client.Authenticator")
        self.MockAuthenticator = self.auth_patcher.start()

        self.banking_patcher = patch("comdirect_mcp.client.BankingApi")
        self.MockBankingApi = self.banking_patcher.start()

        self.brokerage_patcher = patch("comdirect_mcp.client.BrokerageApi")
        self.MockBrokerageApi = self.brokerage_patcher.start()

        self.messages_patcher = patch("comdirect_mcp.client.MessagesApi")
        self.MockMessagesApi = self.messages_patcher.start()

        self.client = ComdirectClient(self.credentials, self.tan_handlers)

        # Setup common mock behavior
        self.mock_auth_instance = self.MockAuthenticator.return_value
        self.mock_auth_instance.authenticate.return_value = (
            "session_123",
            {"access_token": "token_abc"},
        )

    def tearDown(self):
        self.auth_patcher.stop()
        self.banking_patcher.stop()
        self.brokerage_patcher.stop()
        self.messages_patcher.stop()

    def test_login(self):
        self.client.login()

        self.mock_auth_instance.authenticate.assert_called_once()
        self.assertEqual(self.client._session_id, "session_123")
        self.assertEqual(self.client._api_client.configuration.access_token, "token_abc")

    def test_list_accounts(self):
        # Mock response from banking API
        mock_balance = MagicMock()
        mock_balance.account_id = "acc_1"
        mock_balance.balance.unit = "EUR"
        mock_balance.balance.value = "100.50"
        mock_balance.available_cash_amount.value = "50.00"

        mock_response = MagicMock()
        mock_response.values = [mock_balance]
        self.client._banking.banking_v2_get_account_balances.return_value = mock_response

        accounts = self.client.list_accounts()

        self.assertEqual(len(accounts), 1)
        self.assertIsInstance(accounts[0], Account)
        self.assertEqual(accounts[0].id, "acc_1")
        self.assertEqual(accounts[0].balance, Decimal("100.50"))

        self.client._banking.banking_v2_get_account_balances.assert_called_with(user="user")

    def test_list_transactions(self):
        # Mock first page
        mock_tx1 = MagicMock()
        mock_tx1.booking_date = "2023-01-01"
        mock_tx1.amount.value = "10.00"
        mock_tx1.amount.unit = "EUR"
        mock_tx1.transaction_type.key = "DEBIT"
        mock_tx1.remittance_info = "Test Tx"
        mock_tx1.valuta_date = None
        mock_tx1.new_transaction = False

        mock_response_data = MagicMock()
        mock_response_data.values = [mock_tx1]

        # We patch _get_account_transactions_page directly for simplicity
        with patch.object(self.client, "_get_account_transactions_page") as mock_get_page:
            # First call returns data, second call returns empty (simulating end of pages)
            mock_get_page.side_effect = [
                mock_response_data,
                MagicMock(values=[]),
            ]

            txs = self.client.list_transactions("acc_1")

            self.assertEqual(len(txs), 1)
            self.assertEqual(txs[0].amount, Decimal("10.00"))

    def test_list_depots(self):
        mock_depot = MagicMock()
        mock_depot.depot_id = "dep_1"
        mock_depot.depot_display_id = "Depot 1"
        mock_depot.client_id = "cli_1"

        mock_response = MagicMock()
        mock_response.values = [mock_depot]
        self.client._brokerage.brokerage_v3_get_depots.return_value = mock_response

        depots = self.client.list_depots()

        self.assertEqual(len(depots), 1)
        self.assertEqual(depots[0].id, "dep_1")

    def test_get_depot_positions(self):
        mock_agg = {
            "depotId": "dep_1",
            "currentValue": {"value": "1000.00", "unit": "EUR"},
            "purchaseValue": {"value": "900.00", "unit": "EUR"},
            "prevDayValue": {"value": "950.00", "unit": "EUR"},
            "dateLastUpdate": "2023-01-01",
        }

        mock_pos = MagicMock()
        mock_pos.depot_id = "dep_1"
        mock_pos.quantity.value = "10"
        mock_pos.current_value.value = "100"
        mock_pos.purchase_value.value = "90"
        mock_pos.profit_loss_purchase_abs.value = "10"
        mock_pos.profit_loss_prev_day_abs.value = "5"

        mock_response = MagicMock()
        mock_response.aggregated = mock_agg
        mock_response.values = [mock_pos]

        self.client._brokerage.brokerage_v3_get_depot_positions.return_value = mock_response

        balance, positions = self.client.get_depot_positions("dep_1")

        self.assertEqual(balance.current_value, Decimal("1000.00"))
        self.assertEqual(len(positions), 1)
        self.client._brokerage.brokerage_v3_get_depot_positions.assert_called_with("dep_1", with_attr="instrument")

    def test_list_documents(self):
        mock_doc = MagicMock()
        mock_doc.document_id = "doc_1"
        mock_doc.name = "Statement"
        mock_doc.date_creation = "2023-01-01"
        mock_doc.mime_type = "application/pdf"
        mock_doc.advertisement = False

        mock_response = MagicMock()
        mock_response.values = [mock_doc]
        self.client._messages.messages_v2_get_documents.return_value = mock_response

        docs = self.client.list_documents()

        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0].id, "doc_1")

    def test_download_document(self):
        mock_response = MagicMock()
        mock_response.raw_data = b"pdf_content"
        self.client._messages.messages_v2_get_document_with_http_info.return_value = mock_response

        content = self.client.download_document("doc_1", "application/pdf")

        self.assertEqual(content, b"pdf_content")
        self.client._messages.messages_v2_get_document_with_http_info.assert_called_with(
            "doc_1", _headers={"Accept": "application/pdf"}
        )

    def test_two_step_login(self):
        challenge = TanChallenge(id="ch_1", typ="P_TAN_PUSH", session_id="session_123")
        self.mock_auth_instance.start.return_value = challenge
        self.mock_auth_instance.complete.return_value = ("session_123", {"access_token": "token_abc"})

        self.assertIs(self.client.start_login(), challenge)
        self.assertFalse(self.client.is_logged_in)

        self.client.complete_login(challenge)

        self.mock_auth_instance.complete.assert_called_once_with(challenge, "")
        self.assertTrue(self.client.is_logged_in)

    def test_expiring_token_is_refreshed(self):
        self.mock_auth_instance.authenticate.return_value = (
            "session_123",
            {"access_token": "old", "refresh_token": "r1", "expires_in": 30},
        )
        self.mock_auth_instance.refresh.return_value = {
            "access_token": "new",
            "refresh_token": "r2",
            "expires_in": 599,
        }
        self.client.login()

        # 30s left is inside the refresh margin
        self.assertEqual(self.client._valid_access_token(), "new")
        self.mock_auth_instance.refresh.assert_called_once_with("r1")

        # fresh token is used as is
        self.assertEqual(self.client._valid_access_token(), "new")
        self.mock_auth_instance.refresh.assert_called_once()

    def test_failed_refresh_ends_session(self):
        self.mock_auth_instance.authenticate.return_value = (
            "session_123",
            {"access_token": "old", "refresh_token": "r1", "expires_in": 0},
        )
        self.mock_auth_instance.refresh.side_effect = AuthenticationError("expired")
        self.client.login()

        with self.assertRaises(AuthenticationError):
            self.client._valid_access_token()
        self.assertFalse(self.client.is_logged_in)

    def test_token_without_expiry_is_not_refreshed(self):
        self.client.login()

        self.assertEqual(self.client._valid_access_token(), "token_abc")
        self.mock_auth_instance.refresh.assert_not_called()

    def test_logout_revokes_tokens_at_comdirect(self):
        self.client.login()

        self.client.logout()

        self.mock_auth_instance.revoke.assert_called_once_with("token_abc")
        self.assertFalse(self.client.is_logged_in)

    def test_logout_clears_session_even_if_revoke_fails(self):
        self.client.login()
        self.mock_auth_instance.revoke.side_effect = AuthenticationError("expired")

        self.client.logout()

        self.assertFalse(self.client.is_logged_in)

    def test_logout_without_session_does_not_call_comdirect(self):
        self.client.logout()

        self.mock_auth_instance.revoke.assert_not_called()

    def test_logout(self):
        self.client.login()
        self.assertIsNotNone(self.client._session_id)

        self.client.logout()
        self.assertIsNone(self.client._session_id)
        self.assertIsNone(self.client._api_client.configuration.access_token)


class TestComdirectApiClient(unittest.TestCase):
    def test_header_injection(self):
        # Mock session provider
        session_provider = MagicMock(return_value="sess_123")

        # Config
        config = MagicMock()
        config.access_token = "token_abc"
        config.assert_hostname = None
        config.proxy = None
        config.ssl_ca_cert = None
        config.cert_file = None
        config.key_file = None

        client = ComdirectApiClient(session_provider, configuration=config)

        # Test call_api
        with patch("comdirect_mcp._openapi.ApiClient.call_api") as mock_super_call:
            client.call_api("GET", "/test")

            # Check args passed to super
            args, kwargs = mock_super_call.call_args
            headers = kwargs["header_params"]

            self.assertIn("Authorization", headers)
            self.assertEqual(headers["Authorization"], "Bearer token_abc")

            self.assertIn("x-http-request-info", headers)
            self.assertIn("sess_123", headers["x-http-request-info"])

            self.assertEqual(headers["Content-Type"], "application/json")
