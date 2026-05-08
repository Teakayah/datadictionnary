"""Tests for src/auth_graph.py — Entra ID groups overage handling.

Coverage:
  - has_groups_overage: True only when inline groups missing AND
    _claim_names.groups is set
  - fetch_member_groups: success path returns the value array
  - fetch_member_groups: pagination follows @odata.nextLink
  - fetch_member_groups: 5xx → returns [] and logs warning (fail closed)
  - fetch_member_groups: 403 (missing scope) → returns [] and logs warning
  - fetch_member_groups: network error → returns [] and logs warning
  - fetch_member_groups: cache hit on second call within TTL
  - fetch_member_groups: cache miss after TTL expiry
  - fetch_member_groups: empty user_oid path doesn't break
  - _resolve_user_groups: inline groups → uses them, never calls Graph
  - _resolve_user_groups: overage → calls fetch_member_groups
  - _resolve_user_groups: neither → returns []
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest
import requests


# ── has_groups_overage ───────────────────────────────────────────────────────

class TestHasGroupsOverage:
    def test_inline_groups_present_returns_false(self):
        from src.auth_graph import has_groups_overage
        assert has_groups_overage({"groups": ["g1", "g2"]}) is False

    def test_inline_groups_with_claim_names_still_false(self):
        """If both inline groups and _claim_names exist, prefer inline."""
        from src.auth_graph import has_groups_overage
        claims = {
            "groups": ["g1"],
            "_claim_names": {"groups": "src1"},
        }
        assert has_groups_overage(claims) is False

    def test_overage_indicator_returns_true(self):
        from src.auth_graph import has_groups_overage
        claims = {
            "_claim_names": {"groups": "src1"},
            "_claim_sources": {"src1": {"endpoint": "https://graph..."}},
        }
        assert has_groups_overage(claims) is True

    def test_no_groups_no_indicator_returns_false(self):
        """Tenant with no group config at all — not an overage."""
        from src.auth_graph import has_groups_overage
        assert has_groups_overage({}) is False

    def test_claim_names_without_groups_key_returns_false(self):
        from src.auth_graph import has_groups_overage
        claims = {"_claim_names": {"roles": "src1"}}
        assert has_groups_overage(claims) is False

    def test_handles_none_claim_names(self):
        from src.auth_graph import has_groups_overage
        assert has_groups_overage({"_claim_names": None}) is False


# ── fetch_member_groups ──────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _clear_cache_between_tests():
    """Ensure each test starts with an empty cache."""
    import src.auth_graph as ag
    ag._clear_cache()
    yield
    ag._clear_cache()


def _resp(status: int, payload: dict) -> MagicMock:
    """Build a fake requests.Response."""
    r = MagicMock(spec=requests.Response)
    r.status_code = status
    r.json.return_value = payload
    if status >= 400:
        r.raise_for_status.side_effect = requests.HTTPError(f"HTTP {status}")
    else:
        r.raise_for_status.return_value = None
    return r


class TestFetchMemberGroups:
    def test_success_returns_value_list(self):
        from src.auth_graph import fetch_member_groups
        with patch("src.auth_graph.requests") as r:
            r.post.return_value = _resp(200, {"value": ["g1", "g2", "g3"]})
            result = fetch_member_groups("tok", "user-oid-1")
        assert result == ["g1", "g2", "g3"]
        r.post.assert_called_once()
        # Verify the POST body and auth header.
        kwargs = r.post.call_args.kwargs
        assert kwargs["json"] == {"securityEnabledOnly": True}
        assert kwargs["headers"]["Authorization"] == "Bearer tok"

    def test_pagination_follows_next_link(self):
        from src.auth_graph import fetch_member_groups
        with patch("src.auth_graph.requests") as r:
            r.post.return_value = _resp(200, {
                "value": ["g1", "g2"],
                "@odata.nextLink": "https://graph.microsoft.com/v1.0/$page2",
            })
            r.get.side_effect = [
                _resp(200, {
                    "value": ["g3", "g4"],
                    "@odata.nextLink": "https://graph.microsoft.com/v1.0/$page3",
                }),
                _resp(200, {"value": ["g5"]}),
            ]
            result = fetch_member_groups("tok", "user-oid-2")
        assert result == ["g1", "g2", "g3", "g4", "g5"]
        assert r.post.call_count == 1
        assert r.get.call_count == 2

    def test_5xx_returns_empty_and_logs_warning(self, caplog):
        from src.auth_graph import fetch_member_groups
        with caplog.at_level(logging.WARNING, logger="src.auth_graph"):
            with patch("src.auth_graph.requests") as r:
                r.post.return_value = _resp(503, {"error": "down"})
                result = fetch_member_groups("tok", "user-oid-3")
        assert result == []  # fail-closed
        assert any("Failed to fetch groups" in rec.message for rec in caplog.records)

    def test_403_returns_empty_and_logs_warning(self, caplog):
        """Missing GroupMember.Read.All scope → 403 → empty (no silent grant)."""
        from src.auth_graph import fetch_member_groups
        with caplog.at_level(logging.WARNING, logger="src.auth_graph"):
            with patch("src.auth_graph.requests") as r:
                r.post.return_value = _resp(403, {"error": {"code": "Forbidden"}})
                result = fetch_member_groups("tok", "user-oid-4")
        assert result == []
        assert any("Failed to fetch groups" in rec.message for rec in caplog.records)

    def test_network_error_returns_empty(self, caplog):
        from src.auth_graph import fetch_member_groups
        with caplog.at_level(logging.WARNING, logger="src.auth_graph"):
            with patch("src.auth_graph.requests") as r:
                r.post.side_effect = requests.ConnectionError("dns")
                result = fetch_member_groups("tok", "user-oid-5")
        assert result == []
        assert any("dns" in rec.message for rec in caplog.records)

    def test_cache_hit_within_ttl(self):
        from src.auth_graph import fetch_member_groups
        with patch("src.auth_graph.requests") as r:
            r.post.return_value = _resp(200, {"value": ["g1"]})
            first = fetch_member_groups("tok", "user-oid-cache")
            second = fetch_member_groups("tok", "user-oid-cache")
        assert first == ["g1"]
        assert second == ["g1"]
        # Only one Graph call — second was cached.
        assert r.post.call_count == 1

    def test_cache_miss_after_ttl_expiry(self):
        from src.auth_graph import fetch_member_groups
        import src.auth_graph as ag

        with patch("src.auth_graph.requests") as r:
            r.post.return_value = _resp(200, {"value": ["g1"]})
            fetch_member_groups("tok", "user-oid-ttl")

        # Force the cache entry to be older than the TTL.
        with ag._CACHE_LOCK:
            ts, groups = ag._GROUPS_CACHE["user-oid-ttl"]
            ag._GROUPS_CACHE["user-oid-ttl"] = (ts - ag.GROUPS_TTL_S - 1, groups)

        with patch("src.auth_graph.requests") as r2:
            r2.post.return_value = _resp(200, {"value": ["g1", "g2"]})
            result = fetch_member_groups("tok", "user-oid-ttl")
        assert result == ["g1", "g2"]
        assert r2.post.call_count == 1

    def test_empty_oid_skips_cache(self):
        """Without an OID we still query Graph but never cache the result."""
        from src.auth_graph import fetch_member_groups
        import src.auth_graph as ag

        with patch("src.auth_graph.requests") as r:
            r.post.return_value = _resp(200, {"value": ["g1"]})
            fetch_member_groups("tok", "")
            fetch_member_groups("tok", "")
        # Both calls hit Graph (no cache key without OID).
        assert r.post.call_count == 2
        assert ag._GROUPS_CACHE == {}

    def test_returns_empty_list_when_value_missing(self):
        from src.auth_graph import fetch_member_groups
        with patch("src.auth_graph.requests") as r:
            r.post.return_value = _resp(200, {})
            result = fetch_member_groups("tok", "user-oid-empty")
        assert result == []


class TestClearGroupsCache:
    def test_clear_specific_oid(self):
        from src.auth_graph import clear_groups_cache, fetch_member_groups
        with patch("src.auth_graph.requests") as r:
            r.post.return_value = _resp(200, {"value": ["g1"]})
            fetch_member_groups("tok", "u1")
            fetch_member_groups("tok", "u2")
            n = clear_groups_cache("u1")
            # Only u1 was dropped — u2 still cached, u1 must re-fetch.
            fetch_member_groups("tok", "u2")  # cache hit, no new POST
            fetch_member_groups("tok", "u1")  # cache miss → POST
        assert n == 1
        # 2 initial fetches + 1 re-fetch for u1 = 3 total POSTs.
        assert r.post.call_count == 3

    def test_clear_all_with_no_oid_arg(self):
        from src.auth_graph import clear_groups_cache, fetch_member_groups
        with patch("src.auth_graph.requests") as r:
            r.post.return_value = _resp(200, {"value": ["g1"]})
            fetch_member_groups("tok", "u1")
            fetch_member_groups("tok", "u2")
            fetch_member_groups("tok", "u3")
            n = clear_groups_cache()
        assert n == 3

    def test_clear_unknown_oid_returns_zero(self):
        from src.auth_graph import clear_groups_cache
        assert clear_groups_cache("never-cached") == 0

    def test_clear_empty_cache_returns_zero(self):
        from src.auth_graph import clear_groups_cache
        assert clear_groups_cache() == 0


# ── _resolve_user_groups (auth.py integration) ──────────────────────────────

class TestResolveUserGroups:
    def test_inline_groups_take_precedence(self):
        from src.auth import _resolve_user_groups
        with patch("src.auth_graph.fetch_member_groups") as mocked:
            result = _resolve_user_groups(
                {"groups": ["a", "b"], "oid": "u1"},
                "tok",
            )
        assert result == ["a", "b"]
        mocked.assert_not_called()

    def test_overage_calls_fetch_member_groups(self):
        from src.auth import _resolve_user_groups
        # Patch where the function is *imported into* auth.py at call-time
        # — _resolve_user_groups uses a local import of src.auth_graph, so
        # patching the source module is enough.
        with patch("src.auth_graph.fetch_member_groups") as mocked:
            mocked.return_value = ["g1", "g2", "g3"]
            result = _resolve_user_groups(
                {
                    "_claim_names": {"groups": "src1"},
                    "_claim_sources": {"src1": {"endpoint": "https://graph..."}},
                    "oid": "user-oid-overage",
                },
                "access-tok",
            )
        assert result == ["g1", "g2", "g3"]
        mocked.assert_called_once_with("access-tok", "user-oid-overage")

    def test_no_groups_no_overage_returns_empty(self):
        from src.auth import _resolve_user_groups
        with patch("src.auth_graph.fetch_member_groups") as mocked:
            result = _resolve_user_groups({"oid": "u3"}, "tok")
        assert result == []
        mocked.assert_not_called()

    def test_inline_empty_list_is_used_not_overage(self):
        """An inline empty list means 'tenant has no groups', not 'overage'.
        Don't fall through to Graph in that case."""
        from src.auth import _resolve_user_groups
        with patch("src.auth_graph.fetch_member_groups") as mocked:
            result = _resolve_user_groups(
                {"groups": [], "oid": "u4"},
                "tok",
            )
        assert result == []
        mocked.assert_not_called()
