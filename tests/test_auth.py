"""
Tests for jike.auth module.

Covers:
- create_session
- build_qr_payload (URL encoding)
- render_qr (with and without qrcode lib)
- _extract_tokens (body x-jike, body access_token, headers)
- poll_confirmation (success, timeout, request exceptions)
- refresh_tokens
- authenticate (full flow)
- auth CLI main

Author: Claude Opus 4.5
"""

import json
import sys
import urllib.parse
from unittest.mock import MagicMock, patch

import pytest
import requests

from jike.auth import (
    POLL_INTERVAL_SEC,
    POLL_TIMEOUT_SEC,
    _extract_tokens,
    authenticate,
    build_qr_payload,
    create_session,
    main,
    poll_confirmation,
    refresh_tokens,
    render_qr,
)
from jike.types import TokenPair


# ── create_session ──────────────────────────────────────────


class TestCreateSession:

    @patch("jike.auth.requests.post")
    def test_returns_uuid(self, mock_post, mock_session_response):
        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_session_response
        mock_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_resp

        uuid = create_session()

        assert uuid == "test-uuid-1234-abcd"

    @patch("jike.auth.requests.post")
    def test_calls_correct_endpoint(self, mock_post, mock_session_response):
        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_session_response
        mock_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_resp

        create_session()

        call_args = mock_post.call_args
        assert "/sessions.create" in call_args[0][0]

    @patch("jike.auth.requests.post")
    def test_raises_on_http_error(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = requests.HTTPError("500")
        mock_post.return_value = mock_resp

        with pytest.raises(requests.HTTPError):
            create_session()

    @patch("jike.auth.requests.post")
    def test_sends_content_type_header(self, mock_post, mock_session_response):
        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_session_response
        mock_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_resp

        create_session()

        call_kwargs = mock_post.call_args
        headers = call_kwargs[1]["headers"]
        assert headers["Content-Type"] == "application/json"


# ── build_qr_payload ───────────────────────────────────────


class TestBuildQrPayload:

    def test_starts_with_jike_deeplink(self):
        payload = build_qr_payload("uuid-123")
        assert payload.startswith("jike://page.jk/web?url=")

    def test_contains_encoded_scan_url(self):
        payload = build_qr_payload("uuid-123")
        expected_scan = "https://www.okjike.com/account/scan?uuid=uuid-123"
        encoded = urllib.parse.quote(expected_scan, safe="")
        assert encoded in payload

    def test_ends_with_display_flags(self):
        payload = build_qr_payload("uuid-123")
        assert payload.endswith(
            "&displayHeader=false&displayFooter=false"
        )

    def test_url_encoding_special_chars(self):
        """Ensure colons and slashes in the scan URL are percent-encoded."""
        payload = build_qr_payload("uuid-123")
        # After "url=", the scan URL should be fully encoded
        url_part = payload.split("url=")[1].split("&displayHeader")[0]
        assert ":" not in url_part
        assert "/" not in url_part

    def test_uuid_preserved_in_payload(self):
        payload = build_qr_payload("my-special-uuid")
        decoded = urllib.parse.unquote(payload)
        assert "my-special-uuid" in decoded


# ── render_qr ───────────────────────────────────────────────


class TestRenderQr:

    @patch.dict(sys.modules, {"qrcode": MagicMock()})
    def test_returns_true_when_qrcode_available(self):
        result = render_qr("test-data")
        assert result is True

    def test_returns_false_when_qrcode_missing(self):
        with patch.dict(sys.modules, {"qrcode": None}):
            result = render_qr("test-data")
            assert result is False


# ── _extract_tokens ─────────────────────────────────────────


class TestExtractTokens:

    def test_from_body_xjike_keys(
        self, access_token, refresh_token, mock_tokens_in_body
    ):
        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_tokens_in_body
        mock_resp.headers = {}

        result = _extract_tokens(mock_resp)

        assert result is not None
        assert result.access_token == access_token
        assert result.refresh_token == refresh_token

    def test_from_body_alt_keys(
        self, access_token, refresh_token, mock_tokens_in_body_alt
    ):
        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_tokens_in_body_alt
        mock_resp.headers = {}

        result = _extract_tokens(mock_resp)

        assert result is not None
        assert result.access_token == access_token
        assert result.refresh_token == refresh_token

    def test_from_headers(self, access_token, refresh_token):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {}
        mock_resp.headers = {
            "x-jike-access-token": access_token,
            "x-jike-refresh-token": refresh_token,
        }

        result = _extract_tokens(mock_resp)

        assert result is not None
        assert result.access_token == access_token
        assert result.refresh_token == refresh_token

    def test_body_takes_priority_over_headers(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "x-jike-access-token": "body-access",
            "x-jike-refresh-token": "body-refresh",
        }
        mock_resp.headers = {
            "x-jike-access-token": "header-access",
            "x-jike-refresh-token": "header-refresh",
        }

        result = _extract_tokens(mock_resp)

        assert result.access_token == "body-access"
        assert result.refresh_token == "body-refresh"

    def test_returns_none_when_no_tokens(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {}
        mock_resp.headers = {}

        result = _extract_tokens(mock_resp)

        assert result is None

    def test_returns_none_when_only_access(self, access_token):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "x-jike-access-token": access_token,
        }
        mock_resp.headers = {}

        result = _extract_tokens(mock_resp)

        assert result is None

    def test_returns_none_when_only_refresh(self, refresh_token):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "x-jike-refresh-token": refresh_token,
        }
        mock_resp.headers = {}

        result = _extract_tokens(mock_resp)

        assert result is None

    def test_handles_json_decode_error(self):
        mock_resp = MagicMock()
        mock_resp.json.side_effect = ValueError("No JSON")
        mock_resp.headers = {}

        result = _extract_tokens(mock_resp)

        assert result is None

    def test_returns_token_pair_type(self, mock_tokens_in_body):
        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_tokens_in_body
        mock_resp.headers = {}

        result = _extract_tokens(mock_resp)

        assert isinstance(result, TokenPair)

    def test_mixed_body_and_header_sources(self, access_token, refresh_token):
        """Access in body, refresh in header."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "x-jike-access-token": access_token,
        }
        mock_resp.headers = {
            "x-jike-refresh-token": refresh_token,
        }

        result = _extract_tokens(mock_resp)

        assert result is not None
        assert result.access_token == access_token
        assert result.refresh_token == refresh_token


# ── poll_confirmation ───────────────────────────────────────


class TestPollConfirmation:

    @patch("jike.auth.time.sleep")
    @patch("jike.auth.requests.get")
    def test_returns_tokens_on_200(
        self, mock_get, mock_sleep, mock_tokens_in_body
    ):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_tokens_in_body
        mock_resp.headers = {}
        mock_get.return_value = mock_resp

        result = poll_confirmation("uuid-123")

        assert result is not None
        assert isinstance(result, TokenPair)

    @patch("jike.auth.time.sleep")
    @patch("jike.auth.requests.get")
    def test_returns_none_on_timeout(self, mock_get, mock_sleep):
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_get.return_value = mock_resp

        result = poll_confirmation("uuid-123")

        assert result is None

    @patch("jike.auth.time.sleep")
    @patch("jike.auth.requests.get")
    def test_retries_on_400(self, mock_get, mock_sleep, mock_tokens_in_body):
        mock_400 = MagicMock()
        mock_400.status_code = 400

        mock_200 = MagicMock()
        mock_200.status_code = 200
        mock_200.json.return_value = mock_tokens_in_body
        mock_200.headers = {}

        mock_get.side_effect = [mock_400, mock_400, mock_200]

        result = poll_confirmation("uuid-123")

        assert result is not None
        assert mock_get.call_count == 3

    @patch("jike.auth.time.sleep")
    @patch("jike.auth.requests.get")
    def test_retries_on_request_exception(
        self, mock_get, mock_sleep, mock_tokens_in_body
    ):
        mock_200 = MagicMock()
        mock_200.status_code = 200
        mock_200.json.return_value = mock_tokens_in_body
        mock_200.headers = {}

        mock_get.side_effect = [
            requests.ConnectionError("network down"),
            mock_200,
        ]

        result = poll_confirmation("uuid-123")

        assert result is not None
        assert mock_get.call_count == 2

    @patch("jike.auth.time.sleep")
    @patch("jike.auth.requests.get")
    def test_sleeps_between_polls(self, mock_get, mock_sleep):
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_get.return_value = mock_resp

        poll_confirmation("uuid-123")

        for call in mock_sleep.call_args_list:
            assert call[0][0] == POLL_INTERVAL_SEC

    @patch("jike.auth.time.sleep")
    @patch("jike.auth.requests.get")
    def test_calls_correct_endpoint(self, mock_get, mock_sleep):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "x-jike-access-token": "a",
            "x-jike-refresh-token": "r",
        }
        mock_resp.headers = {}
        mock_get.return_value = mock_resp

        poll_confirmation("uuid-xyz")

        url = mock_get.call_args[0][0]
        assert "sessions.wait_for_confirmation" in url
        assert "uuid=uuid-xyz" in url

    @patch("jike.auth.time.sleep")
    @patch("jike.auth.requests.get")
    def test_max_attempts_calculated_correctly(
        self, mock_get, mock_sleep
    ):
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_get.return_value = mock_resp

        poll_confirmation("uuid-123")

        expected_attempts = POLL_TIMEOUT_SEC // POLL_INTERVAL_SEC
        assert mock_get.call_count == expected_attempts

    @patch("jike.auth.time.sleep")
    @patch("jike.auth.requests.get")
    def test_retries_on_other_status_codes(
        self, mock_get, mock_sleep, mock_tokens_in_body
    ):
        mock_500 = MagicMock()
        mock_500.status_code = 500

        mock_200 = MagicMock()
        mock_200.status_code = 200
        mock_200.json.return_value = mock_tokens_in_body
        mock_200.headers = {}

        mock_get.side_effect = [mock_500, mock_200]

        result = poll_confirmation("uuid-123")

        assert result is not None


# ── refresh_tokens ──────────────────────────────────────────


class TestRefreshTokens:

    @patch("jike.auth.requests.post")
    def test_returns_new_token_pair(
        self, mock_post, token_pair, new_access_token, new_refresh_token
    ):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.headers = {
            "x-jike-access-token": new_access_token,
            "x-jike-refresh-token": new_refresh_token,
        }
        mock_post.return_value = mock_resp

        result = refresh_tokens(token_pair)

        assert result.access_token == new_access_token
        assert result.refresh_token == new_refresh_token

    @patch("jike.auth.requests.post")
    def test_falls_back_to_old_tokens(self, mock_post, token_pair):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.headers = {}
        mock_post.return_value = mock_resp

        result = refresh_tokens(token_pair)

        assert result.access_token == token_pair.access_token
        assert result.refresh_token == token_pair.refresh_token

    @patch("jike.auth.requests.post")
    def test_sends_refresh_token_header(self, mock_post, token_pair):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.headers = {}
        mock_post.return_value = mock_resp

        refresh_tokens(token_pair)

        call_kwargs = mock_post.call_args
        headers = call_kwargs[1]["headers"]
        assert headers["x-jike-refresh-token"] == token_pair.refresh_token

    @patch("jike.auth.requests.post")
    def test_calls_refresh_endpoint(self, mock_post, token_pair):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.headers = {}
        mock_post.return_value = mock_resp

        refresh_tokens(token_pair)

        url = mock_post.call_args[0][0]
        assert "/app_auth_tokens.refresh" in url

    @patch("jike.auth.requests.post")
    def test_raises_on_http_error(self, mock_post, token_pair):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = requests.HTTPError("403")
        mock_post.return_value = mock_resp

        with pytest.raises(requests.HTTPError):
            refresh_tokens(token_pair)

    @patch("jike.auth.requests.post")
    def test_returns_immutable_token_pair(
        self, mock_post, token_pair, new_access_token, new_refresh_token
    ):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.headers = {
            "x-jike-access-token": new_access_token,
            "x-jike-refresh-token": new_refresh_token,
        }
        mock_post.return_value = mock_resp

        result = refresh_tokens(token_pair)

        assert isinstance(result, TokenPair)
        import dataclasses
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.access_token = "mutated"


# ── authenticate (full flow) ───────────────────────────────


class TestAuthenticate:

    @patch("jike.auth.refresh_tokens")
    @patch("jike.auth.poll_confirmation")
    @patch("jike.auth.render_qr")
    @patch("jike.auth.create_session")
    def test_full_flow_success(
        self,
        mock_create,
        mock_render,
        mock_poll,
        mock_refresh,
        token_pair,
    ):
        mock_create.return_value = "uuid-abc"
        mock_render.return_value = True
        mock_poll.return_value = token_pair
        mock_refresh.return_value = token_pair

        result = authenticate()

        assert result == token_pair
        mock_create.assert_called_once()
        mock_poll.assert_called_once_with("uuid-abc")
        mock_refresh.assert_called_once_with(token_pair)

    @patch("jike.auth.refresh_tokens")
    @patch("jike.auth.poll_confirmation")
    @patch("jike.auth.render_qr")
    @patch("jike.auth.create_session")
    def test_exits_on_timeout(
        self, mock_create, mock_render, mock_poll, mock_refresh
    ):
        mock_create.return_value = "uuid-abc"
        mock_render.return_value = True
        mock_poll.return_value = None

        with pytest.raises(SystemExit) as exc_info:
            authenticate()

        assert exc_info.value.code == 1
        mock_refresh.assert_not_called()

    @patch("jike.auth.refresh_tokens")
    @patch("jike.auth.poll_confirmation")
    @patch("jike.auth.render_qr")
    @patch("jike.auth.create_session")
    def test_prints_qr_payload_when_no_qrcode(
        self,
        mock_create,
        mock_render,
        mock_poll,
        mock_refresh,
        token_pair,
        capsys,
    ):
        mock_create.return_value = "uuid-abc"
        mock_render.return_value = False
        mock_poll.return_value = token_pair
        mock_refresh.return_value = token_pair

        authenticate()

        captured = capsys.readouterr()
        assert "jike://page.jk/web" in captured.err


# ── auth main (CLI) ────────────────────────────────────────


class TestAuthMain:

    @patch("jike.auth.authenticate")
    def test_prints_json_tokens(
        self, mock_auth, token_pair, capsys
    ):
        mock_auth.return_value = token_pair

        main()

        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["access_token"] == token_pair.access_token
        assert output["refresh_token"] == token_pair.refresh_token
