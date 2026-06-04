"""Tests for the worldcup-market-intelligence connector."""
import importlib.util
import os
from datetime import datetime, timedelta, timezone

# Load module with hyphenated filename using importlib
_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location(
    "worldcup_market_intelligence",
    os.path.join(_parent_dir, "worldcup-market-intelligence.py")
)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

normalize_market_sources = _module.normalize_market_sources
filter_cached_markets = _module.filter_cached_markets


def _kalshi_record(**overrides):
    record = {
        "ticker": "KXWC-BRA",
        "title": "Will Brazil win the 2026 FIFA World Cup?",
        "status": "active",
        "yes_price": 22,
        "volume": 5000,
    }
    record.update(overrides)
    return record


def _poly_record(**overrides):
    record = {
        "id": "2415458",
        "question": "Will Belgium reach the Round of 16 at the 2026 FIFA World Cup?",
        "active": True,
        "outcomes": [{"name": "Yes", "price": 0.61}, {"name": "No", "price": 0.39}],
        "clob_token_ids": ["tok-yes", "tok-no"],
        "volume": "998.49",
    }
    record.update(overrides)
    return record


class TestNormalizeMarketSources:
    def test_empty_inputs(self):
        result = normalize_market_sources({"params": {}})
        assert result["status"] is True
        assert result["data"]["count"] == 0
        assert result["data"]["warnings"]

    def test_kalshi_cents_normalized_and_no_derived(self):
        result = normalize_market_sources(
            {"params": {"kalshi_markets": {"markets": [_kalshi_record()]}, "status": "all"}}
        )
        markets = result["data"]["markets"]
        assert len(markets) == 1
        outcomes = {o["name"]: o["price"] for o in markets[0]["outcomes"]}
        assert outcomes["Yes"] == 0.22
        assert outcomes["No"] == 0.78

    def test_polymarket_token_ids_aligned(self):
        result = normalize_market_sources(
            {"params": {"polymarket_markets": {"markets": [_poly_record()]}}}
        )
        markets = result["data"]["markets"]
        assert len(markets) == 1
        assert [o["token_id"] for o in markets[0]["outcomes"]] == ["tok-yes", "tok-no"]

    def test_metadata_is_upsert_key(self):
        result = normalize_market_sources(
            {"params": {"polymarket_markets": {"markets": [_poly_record()]}}}
        )
        market = result["data"]["markets"][0]
        assert market["id"] == market["cache_id"] == "polymarket:2415458"
        # Document-store bulk-update upserts on {metadata, name}; without a
        # unique per-item metadata every market collapses into one document.
        assert market["metadata"] == {"cache_id": "polymarket:2415458"}

    def test_search_entity_payload_shape(self):
        payload = {"kalshi": [_kalshi_record()], "polymarket": [_poly_record()], "total_results": 2}
        result = normalize_market_sources({"params": {"sports_skills_markets": payload}})
        sources = {m["source"] for m in result["data"]["markets"]}
        assert sources == {"kalshi", "polymarket"}

    def test_dedup_same_market_across_payloads(self):
        result = normalize_market_sources(
            {
                "params": {
                    "sports_skills_markets": {"polymarket": [_poly_record()]},
                    "polymarket_markets": {"markets": [_poly_record()]},
                }
            }
        )
        assert result["data"]["count"] == 1

    def test_non_numeric_volume_does_not_crash_sort(self):
        records = [
            _poly_record(id="a", volume={"total": 1}),
            _poly_record(id="b", volume="not-a-number"),
            _poly_record(id="c", volume="50.5"),
        ]
        result = normalize_market_sources({"params": {"polymarket_markets": {"markets": records}}})
        assert result["data"]["count"] == 3
        # Numeric volume sorts first; non-numeric coerces to 0.0.
        assert result["data"]["markets"][0]["cache_id"] == "polymarket:c"

    def test_query_with_specific_token_filters(self):
        records = [_kalshi_record(), _kalshi_record(ticker="KXWC-ARG", title="Will Argentina win the 2026 FIFA World Cup?")]
        result = normalize_market_sources(
            {"params": {"kalshi_markets": {"markets": records}, "query": "Brazil", "status": "all"}}
        )
        titles = [m["title"] for m in result["data"]["markets"]]
        assert titles == ["Will Brazil win the 2026 FIFA World Cup?"]

    def test_generic_query_keeps_all_world_cup_markets(self):
        records = [_kalshi_record(), _kalshi_record(ticker="KXWC-ARG", title="Will Argentina win the 2026 FIFA World Cup?")]
        result = normalize_market_sources(
            {"params": {"kalshi_markets": {"markets": records}, "query": "FIFA World Cup 2026", "status": "all"}}
        )
        assert result["data"]["count"] == 2

    def test_non_world_cup_market_filtered_out(self):
        records = [_kalshi_record(ticker="NBA-LAL", title="Will the Lakers win the NBA Finals?")]
        result = normalize_market_sources({"params": {"kalshi_markets": {"markets": records}, "status": "all"}})
        assert result["data"]["count"] == 0

    def test_status_open_filter(self):
        records = [_kalshi_record(), _kalshi_record(ticker="KXWC-X", status="settled")]
        result = normalize_market_sources({"params": {"kalshi_markets": {"markets": records}, "status": "open"}})
        assert result["data"]["count"] == 1
        assert result["data"]["markets"][0]["status"] == "open"


class TestFilterCachedMarkets:
    def _cached(self, fetched_at, **overrides):
        market = {
            "id": "kalshi:KXWC-BRA",
            "cache_id": "kalshi:KXWC-BRA",
            "source": "kalshi",
            "title": "Will Brazil win the 2026 FIFA World Cup?",
            "status": "open",
            "volume": 100,
            "fetched_at": fetched_at,
        }
        market.update(overrides)
        return market

    def test_limit_clamped_to_250(self):
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        cached = [self._cached(now, id=f"kalshi:{i}", cache_id=f"kalshi:{i}") for i in range(300)]
        result = filter_cached_markets({"params": {"cached_markets": cached, "limit": 9999}})
        assert result["data"]["count"] == 250

    def test_fresh_cache_has_no_staleness_warning(self):
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        result = filter_cached_markets({"params": {"cached_markets": [self._cached(now)]}})
        assert result["data"]["warnings"] == []

    def test_stale_cache_warns(self):
        old = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat().replace("+00:00", "Z")
        result = filter_cached_markets({"params": {"cached_markets": [self._cached(old)]}})
        assert any("minutes old" in w for w in result["data"]["warnings"])

    def test_missing_fetched_at_warns_unknown_freshness(self):
        result = filter_cached_markets({"params": {"cached_markets": [self._cached("")]}})
        assert any("freshness unknown" in w for w in result["data"]["warnings"])

    def test_no_match_warning(self):
        result = filter_cached_markets({"params": {"cached_markets": [], "query": "Brazil"}})
        assert result["data"]["count"] == 0
        assert result["data"]["warnings"]
