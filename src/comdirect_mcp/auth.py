import base64
import json
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import requests

from .exceptions import AuthenticationError, TanError
from .utils import request_id

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TanChallenge:
    """A pending 2FA challenge, created by `Authenticator.start()` and consumed by `Authenticator.complete()`."""

    id: str
    typ: str  # P_TAN_PUSH, P_TAN or M_TAN
    session_id: str
    challenge: str | None = None  # base64 PNG for P_TAN
    primary_token: str = field(default="", repr=False)


class Authenticator:
    """
    Handles the complicated OAuth + 2FA authentication flow for Comdirect.

    The flow can run in one go via `authenticate()` (using the TAN callbacks), or in two steps via
    `start()` and `complete()` for callers that collect the TAN asynchronously (e.g. the MCP server).
    """

    TOKEN_URL = "https://api.comdirect.de/oauth/token"
    REVOKE_URL = "https://api.comdirect.de/oauth/revoke"
    SESSION_URL = "https://api.comdirect.de/api/session/clients/user/v1/sessions"

    def __init__(
        self,
        username: str,
        password: str,
        client_id: str,
        client_secret: str,
        *,
        photo_tan_cb: Callable[[bytes], str] | None = None,
        sms_tan_cb: Callable[[], str] | None = None,
        push_tan_cb: Callable[[], str] | None = None,
    ):
        self._username = username
        self._password = password
        self._client_id = client_id
        self._client_secret = client_secret
        self._photo_cb = photo_tan_cb
        self._sms_cb = sms_tan_cb
        self._push_cb = push_tan_cb

        self._session = requests.Session()

    def authenticate(self) -> tuple[str, dict[str, Any]]:
        """
        Performs the full authentication flow, resolving the TAN through the configured callbacks.

        Returns:
            Tuple containing (session_id, token_response_dict)
        """
        challenge = self.start()
        tan = self._resolve_tan(challenge)
        return self.complete(challenge, tan)

    def start(self, tan_type: str | None = None) -> TanChallenge:
        """
        Steps 1-3a: get the primary token, create a session and trigger the 2FA challenge.

        Without `tan_type` comdirect uses the account's preferred TAN method; pass e.g. "P_TAN_PUSH" to request a
        specific one. Note: five challenges without a successfully confirmed TAN in between lock the online access.
        """
        logger.info("Starting authentication flow")
        try:
            token = self._primary_token()
            session_id = self._create_session(token)
            return self._request_challenge(token, session_id, tan_type)
        except requests.RequestException as e:
            logger.error(f"Network error during authentication: {e}")
            raise AuthenticationError(f"Network error: {str(e)}") from e

    def complete(self, challenge: TanChallenge, tan: str) -> tuple[str, dict[str, Any]]:
        """
        Steps 3b-4: confirm the 2FA challenge and exchange the primary for the secondary token.

        Returns:
            Tuple containing (session_id, token_response_dict)
        """
        try:
            self._confirm_challenge(challenge, tan)
            secondary_token = self._secondary_token(challenge.primary_token)
        except requests.RequestException as e:
            logger.error(f"Network error during authentication: {e}")
            raise AuthenticationError(f"Network error: {str(e)}") from e

        logger.info("Authentication successful")
        return challenge.session_id, secondary_token

    def refresh(self, refresh_token: str) -> dict[str, Any]:
        """Exchanges a refresh token for a new access/refresh token pair. The session stays the same."""
        logger.debug("Refreshing access token")
        try:
            response = self._session.post(
                self.TOKEN_URL,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
            )
        except requests.RequestException as e:
            raise AuthenticationError(f"Network error: {str(e)}") from e
        self._handle_error(response, "Token refresh failed")
        return response.json()

    def revoke(self, access_token: str) -> None:
        """
        Revokes the token pair at comdirect (DELETE /oauth/revoke, expects 204).

        Observed live: the refresh token is rejected right away, the access token stays valid until it expires.
        """
        logger.debug("Revoking access token")
        try:
            response = self._session.delete(
                self.REVOKE_URL,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Authorization": f"Bearer {access_token}",
                },
            )
        except requests.RequestException as e:
            raise AuthenticationError(f"Network error: {str(e)}") from e
        self._handle_error(response, "Token revocation failed", expected_codes=[204])
        logger.info("Tokens revoked at comdirect (HTTP %s)", response.status_code)

    def _primary_token(self) -> str:
        """Step 1: Get initial OAuth access token using password grant."""
        logger.debug("Requesting primary token")
        payload = {
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "username": self._username,
            "password": self._password,
            "grant_type": "password",
        }

        response = self._session.post(
            self.TOKEN_URL,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data=payload,
        )

        self._handle_error(response, "Primary OAuth failed")
        return response.json()["access_token"]

    def _create_session(self, token: str) -> str:
        """Step 2: Initialize a session with the API."""
        logger.debug("Creating API session")
        headers = self._get_base_headers(token)
        headers["x-http-request-info"] = self._build_request_info_header(uuid.uuid4().hex)

        response = self._session.get(self.SESSION_URL, headers=headers)

        self._handle_error(response, "Session creation failed")

        try:
            return response.json()[0]["identifier"]
        except (IndexError, KeyError, json.JSONDecodeError) as e:
            raise AuthenticationError(f"Invalid session response format: {response.text}") from e

    def _session_headers(self, token: str, session_id: str) -> dict[str, str]:
        headers = self._get_base_headers(token)
        headers.update(
            {
                "Content-Type": "application/json",
                "x-http-request-info": self._build_request_info_header(session_id),
            }
        )
        return headers

    def _request_challenge(self, token: str, session_id: str, tan_type: str | None = None) -> TanChallenge:
        """Step 3a: trigger the 2FA challenge for the session."""
        logger.debug("Validating session (2FA challenge)")

        response = self._session.post(
            f"{self.SESSION_URL}/{session_id}/validate",
            headers={
                **self._session_headers(token, session_id),
                **({"x-once-authentication-info": json.dumps({"typ": tan_type})} if tan_type else {}),
            },
            json={
                "identifier": session_id,
                "sessionTanActive": True,
                "activated2FA": True,
            },
        )
        self._handle_error(response, "Session validation init failed", expected_codes=[201])

        challenge_header = response.headers.get("x-once-authentication-info")
        if not challenge_header:
            raise AuthenticationError("Missing x-once-authentication-info header in response")

        auth_info = json.loads(challenge_header)
        logger.info("Received 2FA challenge of type: %s", auth_info.get("typ"))

        return TanChallenge(
            id=auth_info["id"],
            typ=auth_info.get("typ"),
            session_id=session_id,
            challenge=auth_info.get("challenge"),
            primary_token=token,
        )

    def _confirm_challenge(self, challenge: TanChallenge, tan: str) -> None:
        """Step 3b: submit the TAN (not needed for an approved push TAN) to activate the session."""
        logger.debug("Submitting TAN")
        headers = self._session_headers(challenge.primary_token, challenge.session_id)
        headers["x-once-authentication-info"] = json.dumps({"id": challenge.id})
        # For photoTAN push the approval happens in the app and the TAN header is omitted (API docs 2.4).
        if challenge.typ != "P_TAN_PUSH" and tan:
            headers["x-once-authentication"] = tan

        response = self._session.patch(
            f"{self.SESSION_URL}/{challenge.session_id}",
            headers=headers,
            json={
                "identifier": challenge.session_id,
                "sessionTanActive": True,
                "activated2FA": True,
            },
        )
        self._handle_error(response, "TAN confirmation failed")

    def _secondary_token(self, primary_token: str) -> dict[str, Any]:
        """Step 4: public token exchange for full access."""
        logger.debug("Requesting secondary token")
        payload = {
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "grant_type": "cd_secondary",
            "token": primary_token,
        }

        response = self._session.post(
            self.TOKEN_URL,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data=payload,
        )
        self._handle_error(response, "Secondary OAuth failed")
        return response.json()

    def _resolve_tan(self, challenge: TanChallenge) -> str:
        """Dispatches the TAN challenge to the correct callback."""
        typ = challenge.typ
        if typ not in ("P_TAN", "M_TAN", "P_TAN_PUSH"):
            raise TanError(f"Unknown TAN type: {typ}")

        try:
            if typ == "P_TAN":  # PhotoTAN
                if self._photo_cb is None or challenge.challenge is None:
                    raise TanError("PhotoTAN requested, but no photo_tan_cb or challenge image available")
                return self._photo_cb(base64.b64decode(challenge.challenge))
            if typ == "M_TAN":  # SMS TAN
                if self._sms_cb is None:
                    raise TanError("SMS-TAN requested, but no sms_tan_cb configured")
                return self._sms_cb()
            if self._push_cb is None:  # App Approval
                raise TanError("Push-TAN requested, but no push_tan_cb configured")
            return self._push_cb()
        except TanError:
            raise
        except Exception as e:
            logger.error(f"Error in TAN callback: {e}")
            raise TanError(f"TAN callback failed: {str(e)}") from e

    def _handle_error(
        self,
        response: requests.Response,
        msg: str,
        expected_codes: list[int] | None = None,
    ):
        if expected_codes is None:
            expected_codes = [200]

        if response.status_code not in expected_codes:
            error_details = response.text
            try:
                # Try to parse nice error JSON if available
                details_json = response.json()
                if "error_description" in details_json:
                    error_details = details_json["error_description"]
                elif "error" in details_json:
                    error_details = details_json.get("error")
            except ValueError:
                pass

            logger.error(f"{msg}: HTTP {response.status_code} - {error_details}")
            raise AuthenticationError(f"{msg} (HTTP {response.status_code}): {error_details}")

    @staticmethod
    def _get_base_headers(token: str) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
        }

    @staticmethod
    def _build_request_info_header(session_id: str) -> str:
        return json.dumps(
            {
                "clientRequestId": {
                    "sessionId": session_id,
                    "requestId": request_id(),
                }
            }
        )
