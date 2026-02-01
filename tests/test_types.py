"""
Tests for jike.types module.

Covers:
- TokenPair creation and field access
- Frozen dataclass immutability
- to_dict serialization
- Module-level constants

Author: Claude Opus 4.5
"""

import dataclasses

import pytest

from jike.types import API_BASE, DEFAULT_HEADERS, TokenPair


class TestTokenPairCreation:
    """Test TokenPair construction and field access."""

    def test_create_with_positional_args(self):
        tp = TokenPair("acc-123", "ref-456")
        assert tp.access_token == "acc-123"
        assert tp.refresh_token == "ref-456"

    def test_create_with_keyword_args(self):
        tp = TokenPair(access_token="acc-kw", refresh_token="ref-kw")
        assert tp.access_token == "acc-kw"
        assert tp.refresh_token == "ref-kw"

    def test_create_with_mixed_args(self):
        tp = TokenPair("acc-mix", refresh_token="ref-mix")
        assert tp.access_token == "acc-mix"
        assert tp.refresh_token == "ref-mix"

    def test_create_with_empty_strings(self):
        tp = TokenPair("", "")
        assert tp.access_token == ""
        assert tp.refresh_token == ""

    def test_create_missing_args_raises(self):
        with pytest.raises(TypeError):
            TokenPair()

    def test_create_missing_refresh_raises(self):
        with pytest.raises(TypeError):
            TokenPair("acc-only")


class TestTokenPairFrozen:
    """Test frozen=True dataclass behavior."""

    def test_cannot_set_access_token(self, token_pair):
        with pytest.raises(dataclasses.FrozenInstanceError):
            token_pair.access_token = "hacked"

    def test_cannot_set_refresh_token(self, token_pair):
        with pytest.raises(dataclasses.FrozenInstanceError):
            token_pair.refresh_token = "hacked"

    def test_cannot_set_new_attribute(self, token_pair):
        with pytest.raises(dataclasses.FrozenInstanceError):
            token_pair.new_field = "injected"

    def test_cannot_delete_field(self, token_pair):
        with pytest.raises(dataclasses.FrozenInstanceError):
            del token_pair.access_token


class TestTokenPairToDict:
    """Test to_dict serialization."""

    def test_to_dict_returns_dict(self, token_pair):
        result = token_pair.to_dict()
        assert isinstance(result, dict)

    def test_to_dict_keys(self, token_pair):
        result = token_pair.to_dict()
        assert set(result.keys()) == {"access_token", "refresh_token"}

    def test_to_dict_values(self, access_token, refresh_token, token_pair):
        result = token_pair.to_dict()
        assert result["access_token"] == access_token
        assert result["refresh_token"] == refresh_token

    def test_to_dict_is_new_dict(self, token_pair):
        """Ensure to_dict returns a new dict each time (no shared state)."""
        d1 = token_pair.to_dict()
        d2 = token_pair.to_dict()
        assert d1 == d2
        assert d1 is not d2


class TestTokenPairEquality:
    """Test dataclass equality behavior."""

    def test_equal_tokens_are_equal(self):
        t1 = TokenPair("a", "b")
        t2 = TokenPair("a", "b")
        assert t1 == t2

    def test_different_access_not_equal(self):
        t1 = TokenPair("a", "b")
        t2 = TokenPair("x", "b")
        assert t1 != t2

    def test_different_refresh_not_equal(self):
        t1 = TokenPair("a", "b")
        t2 = TokenPair("a", "x")
        assert t1 != t2

    def test_not_equal_to_dict(self):
        tp = TokenPair("a", "b")
        assert tp != {"access_token": "a", "refresh_token": "b"}


class TestTokenPairHashable:
    """Frozen dataclasses should be hashable."""

    def test_is_hashable(self, token_pair):
        h = hash(token_pair)
        assert isinstance(h, int)

    def test_equal_tokens_same_hash(self):
        t1 = TokenPair("a", "b")
        t2 = TokenPair("a", "b")
        assert hash(t1) == hash(t2)

    def test_usable_in_set(self):
        t1 = TokenPair("a", "b")
        t2 = TokenPair("a", "b")
        t3 = TokenPair("x", "y")
        s = {t1, t2, t3}
        assert len(s) == 2


class TestConstants:
    """Test module-level constants."""

    def test_api_base_is_https(self):
        assert API_BASE.startswith("https://")

    def test_api_base_value(self):
        assert API_BASE == "https://api.ruguoapp.com"

    def test_default_headers_has_origin(self):
        assert "Origin" in DEFAULT_HEADERS

    def test_default_headers_has_user_agent(self):
        assert "User-Agent" in DEFAULT_HEADERS

    def test_default_headers_has_accept(self):
        assert "Accept" in DEFAULT_HEADERS

    def test_default_headers_has_dnt(self):
        assert DEFAULT_HEADERS["DNT"] == "1"

    def test_default_headers_origin_is_okjike(self):
        assert "okjike.com" in DEFAULT_HEADERS["Origin"]
