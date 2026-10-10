import base64
import json
import unittest
from unittest.mock import MagicMock

from comdirect_mcp.auth import Authenticator, TanChallenge
from comdirect_mcp.exceptions import AuthenticationError, TanError


def _response(status=200, json_data=None, headers=None):
    response = MagicMock()
    response.status_code = status
    response.json.return_value = json_data
    response.headers = headers or {}
    response.text = json.dumps(json_data)
    return response


class TestAuthenticator(unittest.TestCase):
    def setUp(self):
        self.push_cb = MagicMock(return_value="")
        self.photo_cb = MagicMock(return_value="123456")
        self.auth = Authenticator("user", "pwd", "cid", "csec", push_tan_cb=self.push_cb, photo_tan_cb=self.photo_cb)
        self.http = MagicMock()
        self.auth._session = self.http

    def _challenge_responses(self, typ="P_TAN_PUSH", challenge=None):
        info = {"id": "ch_1", "typ": typ}
        if challenge:
            info["challenge"] = challenge
        self.http.post.side_effect = [
            _response(json_data={"access_token": "primary"}),
            _response(status=201, headers={"x-once-authentication-info": json.dumps(info)}),
            _response(json_data={"access_token": "secondary", "refresh_token": "r", "expires_in": 599}),
        ]
        self.http.get.return_value = _response(json_data=[{"identifier": "sess_1"}])
        self.http.patch.return_value = _response()

    def test_start_returns_challenge(self):
        self._challenge_responses()

        challenge = self.auth.start()

        self.assertEqual(challenge.id, "ch_1")
        self.assertEqual(challenge.typ, "P_TAN_PUSH")
        self.assertEqual(challenge.session_id, "sess_1")
        self.assertEqual(challenge.primary_token, "primary")
        self.http.patch.assert_not_called()

    def test_complete_confirms_tan_and_exchanges_token(self):
        self._challenge_responses()
        challenge = self.auth.start()

        session_id, tokens = self.auth.complete(challenge, "")

        self.assertEqual(session_id, "sess_1")
        self.assertEqual(tokens["access_token"], "secondary")
        headers = self.http.patch.call_args.kwargs["headers"]
        self.assertEqual(json.loads(headers["x-once-authentication-info"]), {"id": "ch_1"})
        self.assertEqual(headers["Authorization"], "Bearer primary")
        secondary = self.http.post.call_args.kwargs["data"]
        self.assertEqual(secondary["grant_type"], "cd_secondary")
        self.assertEqual(secondary["token"], "primary")

    def test_authenticate_uses_push_callback(self):
        self._challenge_responses()

        session_id, tokens = self.auth.authenticate()

        self.push_cb.assert_called_once_with()
        self.assertEqual(tokens["access_token"], "secondary")

    def test_authenticate_passes_photo_tan_image(self):
        self._challenge_responses(typ="P_TAN", challenge=base64.b64encode(b"png").decode())

        self.auth.authenticate()

        self.photo_cb.assert_called_once_with(b"png")
        self.assertEqual(self.http.patch.call_args.kwargs["headers"]["x-once-authentication"], "123456")

    def test_missing_callback_raises_tan_error(self):
        self._challenge_responses(typ="M_TAN")

        with self.assertRaises(TanError):
            self.auth.authenticate()

    def test_push_tan_is_confirmed_without_tan_header(self):
        # API docs 2.4: for photoTAN push the x-once-authentication header is not sent.
        self._challenge_responses()

        self.auth.complete(self.auth.start(), "")

        self.assertNotIn("x-once-authentication", self.http.patch.call_args.kwargs["headers"])

    def test_start_can_request_a_tan_type(self):
        self._challenge_responses()

        self.auth.start("P_TAN_PUSH")

        validate_headers = self.http.post.call_args_list[1].kwargs["headers"]
        self.assertEqual(json.loads(validate_headers["x-once-authentication-info"]), {"typ": "P_TAN_PUSH"})

    def test_start_uses_preferred_tan_type_by_default(self):
        self._challenge_responses()

        self.auth.start()

        self.assertNotIn("x-once-authentication-info", self.http.post.call_args_list[1].kwargs["headers"])

    def test_client_session_id_is_hex(self):
        # API docs 1.2.2: session id max. 32 hexadecimal characters
        self._challenge_responses()

        self.auth.start()

        info = json.loads(self.http.get.call_args.kwargs["headers"]["x-http-request-info"])["clientRequestId"]
        self.assertRegex(info["sessionId"], r"^[0-9a-f]{1,32}$")
        self.assertRegex(info["requestId"], r"^\d{9}$")

    def test_revoke(self):
        self.http.delete.return_value = _response(status=204)

        self.auth.revoke("access")

        self.assertEqual(self.http.delete.call_args.args[0], "https://api.comdirect.de/oauth/revoke")
        self.assertEqual(self.http.delete.call_args.kwargs["headers"]["Authorization"], "Bearer access")

    def test_revoke_error(self):
        self.http.delete.return_value = _response(status=401, json_data={"error": "invalid_token"})

        with self.assertRaises(AuthenticationError):
            self.auth.revoke("access")

    def test_refresh(self):
        self.http.post.return_value = _response(json_data={"access_token": "new", "refresh_token": "r2"})

        tokens = self.auth.refresh("r1")

        self.assertEqual(tokens["access_token"], "new")
        data = self.http.post.call_args.kwargs["data"]
        self.assertEqual(data["grant_type"], "refresh_token")
        self.assertEqual(data["refresh_token"], "r1")

    def test_refresh_error(self):
        self.http.post.return_value = _response(status=401, json_data={"error": "invalid_grant"})

        with self.assertRaisesRegex(AuthenticationError, "invalid_grant"):
            self.auth.refresh("r1")

    def test_challenge_repr_hides_token(self):
        challenge = TanChallenge(id="1", typ="P_TAN_PUSH", session_id="s", primary_token="secret")
        self.assertNotIn("secret", repr(challenge))


if __name__ == "__main__":
    unittest.main()
