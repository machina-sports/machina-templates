"""Offline unit tests for the ProphetX Affiliate connector (no network)."""

import importlib.util
import time
from pathlib import Path
from unittest.mock import patch

import pytest

CONNECTOR_DIR = Path(__file__).resolve().parents[1]


def load_module(name="prophetx_connector_tests"):
    spec = importlib.util.spec_from_file_location(name, CONNECTOR_DIR / "prophetx.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


px = load_module()

SANDBOX = "https://api.sandbox.prophetx.dev/partner"
PROD = "https://cash.api.prophetx.co/partner"

FAKE_KEY = "unit-test-api-key-value"
FAKE_TOKEN = "unit-test-access-token-value"


class FakeResponse:
    def __init__(self, status_code=200, body=None, headers=None, raw_text=None):
        self.status_code = status_code
        self._body = body
        self.headers = headers or {}
        self._raw_text = raw_text

    def json(self):
        if self._raw_text is not None:
            raise ValueError("not json")
        return self._body


class FakeRequests:
    """Captures every call; scripted responses per (method, path-suffix)."""

    RequestException = px.requests.RequestException

    def __init__(self):
        self.calls = []
        self.script = []

    def queue(self, response):
        self.script.append(response)
        return self

    def _next(self):
        if not self.script:
            raise AssertionError("no scripted response left")
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append({"method": "GET", "url": url, "params": params, "headers": headers})
        return self._next()

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append({"method": "POST", "url": url, "json": json, "headers": headers})
        return self._next()


@pytest.fixture()
def fake():
    original = px.requests
    fake_requests = FakeRequests()
    px.requests = fake_requests
    px._token_cache.clear()
    yield fake_requests
    px.requests = original
    px._token_cache.clear()


def _req(params=None, api_key=FAKE_KEY, access_key=None, secret_key=None):
    headers = {}
    if api_key:
        headers["api_key"] = api_key
    if access_key:
        headers["access_key"] = access_key
    if secret_key:
        headers["secret_key"] = secret_key
    return {"headers": headers, "params": params or {}}


def _tournaments_body(count=2):
    return {"data": {"tournaments": [{"id": i, "name": f"T{i}"} for i in range(count)]}}


# ============================================================
# Auth
# ============================================================


class TestAuth:
    def test_mode_a_raw_key_no_bearer(self, fake):
        fake.queue(FakeResponse(200, _tournaments_body()))
        result = px.get_tournaments(_req())
        assert result["status"] is True
        assert fake.calls[0]["headers"]["Authorization"] == FAKE_KEY

    def test_mode_a_bearer_scheme_opt_in(self, fake):
        fake.queue(FakeResponse(200, _tournaments_body()))
        px.get_tournaments(_req(params={"auth_scheme": "bearer"}))
        assert fake.calls[0]["headers"]["Authorization"] == f"Bearer {FAKE_KEY}"

    def test_mode_b_login_then_cached(self, fake):
        login_body = {
            "data": {
                "access_token": FAKE_TOKEN,
                "access_expire_time": time.time() + 600,
                "refresh_token": "refresh-1",
                "refresh_expire_time": time.time() + 3600,
            }
        }
        fake.queue(FakeResponse(200, login_body))
        fake.queue(FakeResponse(200, _tournaments_body()))
        fake.queue(FakeResponse(200, _tournaments_body(3)))

        request = _req(api_key=None, access_key="ak", secret_key="sk")
        first = px.get_tournaments(request)
        second = px.get_tournaments(request)
        assert first["status"] is True and second["status"] is True
        posts = [c for c in fake.calls if c["method"] == "POST"]
        assert len(posts) == 1  # login happened once; token cached
        assert posts[0]["url"] == f"{SANDBOX}/auth/login"
        gets = [c for c in fake.calls if c["method"] == "GET"]
        assert all(c["headers"]["Authorization"] == FAKE_TOKEN for c in gets)

    def test_mode_b_401_relogin_once_then_typed_error(self, fake):
        login_body = {"data": {"access_token": FAKE_TOKEN, "access_expire_time": time.time() + 600}}
        # login -> GET 401 -> re-login -> GET 401 again => credential_invalid
        fake.queue(FakeResponse(200, login_body))
        fake.queue(FakeResponse(401, {"error": "unauthorized"}))
        fake.queue(FakeResponse(200, login_body))
        fake.queue(FakeResponse(401, {"error": "unauthorized"}))

        result = px.get_tournaments(_req(api_key=None, access_key="ak", secret_key="sk"))
        assert result["status"] is False
        assert result["error_class"] == "credential_invalid"
        assert len([c for c in fake.calls if c["method"] == "POST"]) == 2

    def test_mode_a_401_is_typed_without_relogin(self, fake):
        fake.queue(FakeResponse(401, {"error": "unauthorized"}))
        result = px.get_tournaments(_req())
        assert result["status"] is False
        assert result["error_class"] == "credential_invalid"
        assert len(fake.calls) == 1

    def test_credentials_missing_is_typed(self, fake):
        result = px.get_tournaments({"headers": {}, "params": {}})
        assert result["status"] is False
        assert result["error_class"] == "credential_missing"
        assert fake.calls == []

    def test_expired_token_uses_refresh(self, fake):
        expired = {
            "data": {
                "access_token": "old-token",
                "access_expire_time": time.time() - 10,
                "refresh_token": "refresh-1",
                "refresh_expire_time": time.time() + 3600,
            }
        }
        refreshed = {"data": {"access_token": "new-token", "access_expire_time": time.time() + 600}}
        fake.queue(FakeResponse(200, expired))  # login
        fake.queue(FakeResponse(200, _tournaments_body()))  # first GET (old token still fresh enough? no - expired)
        request = _req(api_key=None, access_key="ak", secret_key="sk")
        # Prime the cache with the expired record via one call path:
        px._token_cache[("sandbox", "ak")] = {
            "access_token": "old-token",
            "access_expire_time": time.time() - 10,
            "refresh_token": "refresh-1",
            "refresh_expire_time": time.time() + 3600,
        }
        fake.script = []
        fake.queue(FakeResponse(200, refreshed))  # POST /auth/refresh
        fake.queue(FakeResponse(200, _tournaments_body()))  # GET with new token
        result = px.get_tournaments(request)
        assert result["status"] is True
        posts = [c for c in fake.calls if c["method"] == "POST"]
        assert posts[-1]["url"] == f"{SANDBOX}/auth/refresh"
        gets = [c for c in fake.calls if c["method"] == "GET"]
        assert gets[-1]["headers"]["Authorization"] == "new-token"

    def test_no_credential_echo_in_errors(self, fake):
        fake.queue(FakeResponse(500, {"error": "boom", "message": "internal"}))
        fake.queue(FakeResponse(500, {"error": "boom", "message": "internal"}))
        fake.queue(FakeResponse(500, {"error": "boom", "message": "internal"}))
        with patch.object(px.time, "sleep"):
            result = px.get_tournaments(_req())
        assert result["status"] is False
        assert FAKE_KEY not in str(result)
        assert "Authorization" not in str(result)


# ============================================================
# Environment allowlist
# ============================================================


class TestEnvironment:
    def test_sandbox_default_host(self, fake):
        fake.queue(FakeResponse(200, _tournaments_body()))
        px.get_tournaments(_req())
        assert fake.calls[0]["url"].startswith(SANDBOX)

    def test_production_host(self, fake):
        fake.queue(FakeResponse(200, _tournaments_body()))
        px.get_tournaments(_req(params={"environment": "production"}))
        assert fake.calls[0]["url"].startswith(PROD)

    def test_unknown_environment_rejected(self, fake):
        result = px.get_tournaments(_req(params={"environment": "staging"}))
        assert result["status"] is False
        assert result["error_class"] == "invalid_request"
        assert fake.calls == []

    def test_arbitrary_base_url_param_is_ignored(self, fake):
        fake.queue(FakeResponse(200, _tournaments_body()))
        px.get_tournaments(_req(params={"base_url": "https://evil.example.com"}))
        assert fake.calls[0]["url"].startswith(SANDBOX)


# ============================================================
# Retries / rate limit / errors
# ============================================================


class TestResilience:
    def test_429_backoff_honors_retry_after_then_typed(self, fake):
        for _ in range(3):
            fake.queue(FakeResponse(429, {"error": "rate_limit_reached"}, headers={"Retry-After": "2"}))
        sleeps = []
        with patch.object(px.time, "sleep", side_effect=sleeps.append):
            result = px.get_tournaments(_req())
        assert result["status"] is False
        assert result["error_class"] == "provider_rate_limited"
        assert len([c for c in fake.calls if c["method"] == "GET"]) == 3
        assert sleeps and sleeps[0] == 2.0

    def test_5xx_retry_then_success(self, fake):
        fake.queue(FakeResponse(503, {"error": "down"}))
        fake.queue(FakeResponse(200, _tournaments_body()))
        with patch.object(px.time, "sleep"):
            result = px.get_tournaments(_req())
        assert result["status"] is True
        assert len(fake.calls) == 2

    def test_404_typed(self, fake):
        fake.queue(FakeResponse(404, {"error": "data_not_found"}))
        result = px.get_markets(_req(params={"event_id": 999}))
        assert result["status"] is False
        assert result["error_class"] == "data_not_found"

    def test_network_exception_retries_then_typed(self, fake):
        fake.queue(px.requests.RequestException("boom"))
        fake.queue(px.requests.RequestException("boom"))
        fake.queue(px.requests.RequestException("boom"))
        with patch.object(px.time, "sleep"):
            result = px.get_tournaments(_req())
        assert result["status"] is False
        assert result["error_class"] == "provider_unavailable"

    def test_malformed_json_typed(self, fake):
        fake.queue(FakeResponse(200, raw_text="<html>waf</html>"))
        result = px.get_tournaments(_req())
        assert result["status"] is False
        assert result["error_class"] == "provider_bad_response"


# ============================================================
# Markets: versions, CFTC header, batches, dual-shape
# ============================================================


def _market_v3(event_id=101):
    return {
        "id": 219,
        "name": "Moneyline",
        "display_name": "Moneyline",
        "group_name": "Game Lines",
        "type": "moneyline",
        "favourite": True,
        "selections": [
            [
                {"line_id": "abc123", "outcome_id": 4, "odds": -150, "display_odds": "-150", "stake": 250.0},
                {"line_id": "abc124", "outcome_id": 4, "odds": -155, "display_odds": "-155", "stake": 100.0},
            ],
            [{"line_id": "def456", "outcome_id": 5, "odds": 130, "display_odds": "+130", "stake": 80.0}],
        ],
    }


def _market_v4(event_id=101):
    return {
        "id": 219,
        "name": "Moneyline",
        "type": "moneyline",
        "strike": 0,
        "selections": [
            [{"strike_id": "abc123", "outcome_id": 4, "price": -150, "display_price": "-150", "quantity": 250.0}],
            [{"strike_id": "def456", "outcome_id": 5, "price": 130, "display_price": "+130", "quantity": 80.0}],
        ],
    }


class TestMarkets:
    def test_version_paths(self, fake):
        for version, expected in (
            ("v1", "/affiliate/get_markets"),
            ("v2", "/v2/affiliate/get_markets"),
            ("v3", "/v3/affiliate/get_markets"),
            ("v4", "/v4/affiliate/get_markets"),
        ):
            fake.calls, fake.script = [], []
            fake.queue(FakeResponse(200, {"data": {"event_id": 1, "markets": []}}))
            result = px.get_markets(_req(params={"event_id": 1, "api_version": version}))
            assert result["status"] is True, version
            assert fake.calls[0]["url"] == f"{SANDBOX}{expected}"

    def test_default_version_is_v3(self, fake):
        fake.queue(FakeResponse(200, {"data": {"event_id": 1, "markets": []}}))
        result = px.get_markets(_req(params={"event_id": 1}))
        assert result["data"]["api_version"] == "v3"

    def test_invalid_version_rejected(self, fake):
        result = px.get_markets(_req(params={"event_id": 1, "api_version": "v9"}))
        assert result["status"] is False
        assert fake.calls == []

    def test_cftc_header_only_on_v3_opt_in(self, fake):
        fake.queue(FakeResponse(200, {"data": {"event_id": 1, "markets": []}}))
        px.get_markets(_req(params={"event_id": 1, "api_version": "v3", "cftc_terminology": True}))
        assert fake.calls[0]["headers"].get("X-CFTC-Terminology") == "true"

        fake.calls, fake.script = [], []
        fake.queue(FakeResponse(200, {"data": {"event_id": 1, "markets": []}}))
        px.get_markets(_req(params={"event_id": 1, "api_version": "v3"}))
        assert "X-CFTC-Terminology" not in fake.calls[0]["headers"]

        fake.calls, fake.script = [], []
        fake.queue(FakeResponse(200, {"data": {"event_id": 1, "markets": []}}))
        px.get_markets(_req(params={"event_id": 1, "api_version": "v4", "cftc_terminology": True}))
        assert "X-CFTC-Terminology" not in fake.calls[0]["headers"]

    def test_v3_normalization_preserves_liquidity_levels(self, fake):
        fake.queue(FakeResponse(200, {"data": {"event_id": 101, "markets": [_market_v3()]}}))
        result = px.get_markets(_req(params={"event_id": 101, "api_version": "v3"}))
        market = result["data"]["markets"][0]
        assert market["market_key"] == "101:219"
        assert market["favourite"] is True
        assert len(market["selections"]) == 2  # two sides
        assert len(market["selections"][0]) == 2  # two liquidity levels preserved
        level = market["selections"][0][0]
        assert level["line_id"] == "abc123"
        assert level["odds"] == -150
        assert level["implied_probability"] == 0.6  # American odds confirmed live
        assert level["stake"] == 250.0
        assert level["_raw"]["line_id"] == "abc123"

    def test_v4_cftc_names_map_to_neutral_fields(self, fake):
        fake.queue(FakeResponse(200, {"data": {"event_id": 101, "markets": [_market_v4()]}}))
        result = px.get_markets(_req(params={"event_id": 101, "api_version": "v4"}))
        level = result["data"]["markets"][0]["selections"][0][0]
        assert level["line_id"] == "abc123"  # strike_id mapped
        assert level["odds"] == -150  # price mapped
        assert level["implied_probability"] == 0.6
        assert level["stake"] == 250.0  # quantity mapped

    def test_implied_probability_absent_when_no_odds(self, fake):
        market = _market_v3()
        market["selections"] = [[{"line_id": "x", "odds": None, "stake": 0}]]
        fake.queue(FakeResponse(200, {"data": {"event_id": 101, "markets": [market]}}))
        result = px.get_markets(_req(params={"event_id": 101, "api_version": "v3"}))
        level = result["data"]["markets"][0]["selections"][0][0]
        assert level["implied_probability"] is None

    def test_updated_at_ns_normalized_to_seconds(self, fake):
        market = _market_v3()
        market["selections"] = [[{"line_id": "x", "odds": -110, "updated_at": 1786643339351933000}]]
        fake.queue(FakeResponse(200, {"data": {"event_id": 101, "markets": [market]}}))
        result = px.get_markets(_req(params={"event_id": 101, "api_version": "v3"}))
        level = result["data"]["markets"][0]["selections"][0][0]
        assert level["updated_at"] == 1786643339351933000
        assert level["updated_at_s"] == pytest.approx(1786643339.35, abs=0.01)

    def test_empty_markets_is_success(self, fake):
        fake.queue(FakeResponse(200, {"data": {"event_id": 1, "markets": []}}))
        result = px.get_markets(_req(params={"event_id": 1}))
        assert result["status"] is True
        assert result["data"]["count"] == 0

    def test_markets_drift_fails_closed(self, fake):
        fake.queue(FakeResponse(200, {"data": {"event_id": 1, "markets": "nope"}}))
        result = px.get_markets(_req(params={"event_id": 1}))
        assert result["status"] is False
        assert result["error_class"] == "provider_bad_response"


class TestMultipleMarkets:
    def test_batch_cap_enforced_without_network(self, fake):
        result = px.get_multiple_markets(_req(params={"event_ids": list(range(51))}))
        assert result["status"] is False
        assert result["error_class"] == "invalid_request"
        assert fake.calls == []

    def test_dict_shape(self, fake):
        fake.queue(FakeResponse(200, {"data": {"101": [_market_v3()], "102": []}}))
        result = px.get_multiple_markets(_req(params={"event_ids": [101, 102]}))
        assert result["status"] is True
        assert result["data"]["market_count"] == 1
        assert result["data"]["markets_by_event"]["101"][0]["market_key"] == "101:219"
        assert result["data"]["markets_by_event"]["102"] == []

    def test_flat_list_shape_attributed_by_event_field(self, fake):
        flat = [dict(_market_v3(), sport_event_id=101), dict(_market_v3(), sport_event_id=999)]
        fake.queue(FakeResponse(200, {"data": flat}))
        result = px.get_multiple_markets(_req(params={"event_ids": [101, 102]}))
        assert result["status"] is True
        grouped = result["data"]["markets_by_event"]
        assert len(grouped["101"]) == 1
        assert grouped["102"] == []
        assert len(grouped["_unattributed"]) == 1

    def test_null_and_odd_values_do_not_fail_the_batch(self, fake):
        # Observed live: per-event values vary between calls; null and odd
        # scalars must not poison the whole batch.
        fake.queue(
            FakeResponse(
                200,
                {"data": {"101": [_market_v3()], "102": None, "103": "weird"}},
            )
        )
        result = px.get_multiple_markets(_req(params={"event_ids": [101, 102, 103]}))
        assert result["status"] is True
        grouped = result["data"]["markets_by_event"]
        assert len(grouped["101"]) == 1
        assert grouped["102"] == []
        assert grouped["_unattributed"][0]["event_key"] == "103"

    def test_drift_fails_closed(self, fake):
        fake.queue(FakeResponse(200, {"data": "garbage"}))
        result = px.get_multiple_markets(_req(params={"event_ids": [1]}))
        assert result["status"] is False
        assert result["error_class"] == "provider_bad_response"


# ============================================================
# Sport events + normalization
# ============================================================


class TestSportEvents:
    def test_requires_tournament_or_event_ids(self, fake):
        result = px.get_sport_events(_req(params={}))
        assert result["status"] is False
        assert fake.calls == []

    def test_normalizes_side_and_names(self, fake):
        body = {
            "data": {
                "sport_events": [
                    {
                        "event_id": 101,
                        "name": "CIN at PHI",
                        "display_name": "Bengals at Eagles",
                        "tournament_id": 31,
                        "tournament_name": "NFL",
                        "sport_name": "American Football",
                        "scheduled": "2026-08-14T00:15:00Z",
                        "status": "not_started",
                        "competitors": [
                            {"id": 1, "display_name": "Philadelphia Eagles", "abbreviation": "PHI", "side": "home"},
                            {"id": 2, "display_name": "Cincinnati Bengals", "abbreviation": "CIN", "side": "away"},
                        ],
                    }
                ]
            }
        }
        fake.queue(FakeResponse(200, body))
        result = px.get_sport_events(_req(params={"tournament_id": 31}))
        event = result["data"]["sport_events"][0]
        assert event["name"] == "Bengals at Eagles"
        assert event["tournament"] == "NFL"
        assert event["competitors"][0]["side"] == "home"
        assert event["_raw"]["event_id"] == 101


# ============================================================
# Auto-Fill handoff (pure)
# ============================================================


class TestAutofill:
    def test_single_line(self, fake):
        result = px.build_autofill_link({"params": {"line_id": "abc", "partner_id": "machina"}})
        assert result["status"] is True
        data = result["data"]
        assert data["app_link"] == "prophetx://addtobetslip?line_id=abc&line_ids=abc&partner_id=machina"
        assert data["web_link"].startswith("https://www.prophetx.co/?action=addtobetslip&line_id=abc")
        assert "deep_link_sub1=machina" in data["onelink"]
        assert fake.calls == []  # pure — no network

    def test_multiple_lines_and_odds(self, fake):
        result = px.build_autofill_link(
            {"params": {"line_ids": ["a", "b"], "partner_id": "machina", "odds": -150}}
        )
        data = result["data"]
        assert "line_id=a&line_ids=a,b" in data["app_link"]
        assert "odds=-150" in data["app_link"]
        assert "deep_link_sub2=a,b" in data["onelink"]
        assert "deep_link_sub3=-150" in data["onelink"]

    def test_partner_id_required(self, fake):
        result = px.build_autofill_link({"params": {"line_id": "abc"}})
        assert result["status"] is False
        assert result["error_class"] == "invalid_request"

    def test_line_required(self, fake):
        result = px.build_autofill_link({"params": {"partner_id": "machina"}})
        assert result["status"] is False


# ============================================================
# Health + misc
# ============================================================


class TestHealthAndMisc:
    def test_health_ok(self, fake):
        fake.queue(FakeResponse(200, _tournaments_body(5)))
        result = px.health(_req())
        assert result["status"] is True
        assert result["data"]["healthy"] is True
        assert result["data"]["tournament_count"] == 5

    def test_health_propagates_typed_failure(self, fake):
        fake.queue(FakeResponse(401, {"error": "unauthorized"}))
        result = px.health(_req())
        assert result["status"] is False
        assert result["error_class"] == "credential_invalid"

    def test_epoch_normalization_units(self):
        assert px._as_epoch_seconds(1736126912) == 1736126912
        assert px._as_epoch_seconds(1736126912002) == pytest.approx(1736126912.002)
        assert px._as_epoch_seconds(1736126912002271000) == pytest.approx(1736126912.002271)
        assert px._as_epoch_seconds("n/a") is None

    def test_no_write_commands_exposed(self):
        forbidden = ("place", "create", "cancel", "wager", "order", "balance", "withdraw", "deposit")
        public = [n for n in dir(px) if not n.startswith("_") and callable(getattr(px, n))]
        for name in public:
            assert not any(word in name.lower() for word in forbidden), name
