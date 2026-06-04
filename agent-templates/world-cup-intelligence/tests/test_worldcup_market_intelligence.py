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
normalize_market_state = _module.normalize_market_state


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

    def test_kalshi_dollar_fields_and_series_ticker_relevance(self):
        # Real KXWCGAME shape: dollar-string prices, no World Cup wording in
        # the title — the series ticker is the relevance signal.
        record = {
            "ticker": "KXWCGAME-26JUN27CODUZB-UZB",
            "event_ticker": "KXWCGAME-26JUN27CODUZB",
            "title": "Congo DR vs Uzbekistan Winner?",
            "yes_sub_title": "Uzbekistan",
            "no_sub_title": "Uzbekistan",
            "status": "active",
            "yes_bid_dollars": "0.29",
            "no_bid_dollars": "0.67",
            "volume_fp": "357.97",
            "liquidity_dollars": "0.0000",
        }
        result = normalize_market_sources({"params": {"kalshi_markets": {"markets": [record]}}})
        assert result["data"]["count"] == 1
        market = result["data"]["markets"][0]
        outcomes = {o["name"]: o["price"] for o in market["outcomes"]}
        assert outcomes == {"Uzbekistan": 0.29, "No": 0.67}
        assert market["volume"] == "357.97"


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


class TestNormalizeMarketState:
    def test_kalshi_state_full(self):
        # Shapes captured live from Kalshi (KXWCGAME-26JUN16FRASEN-FRA).
        result = normalize_market_state({"params": {
            "market_id": "kalshi:KXWCGAME-26JUN16FRASEN-FRA",
            "cached": {"cache_id": "kalshi:KXWCGAME-26JUN16FRASEN-FRA", "source": "kalshi", "title": "France vs Senegal Winner?"},
            "kalshi_market": {
                "ticker": "KXWCGAME-26JUN16FRASEN-FRA",
                "title": "France vs Senegal Winner?",
                "yes_sub_title": "France",
                "status": "active",
                "yes_bid_dollars": "0.6900",
                "no_bid_dollars": "0.2900",
                "volume_fp": "12988.99",
            },
            "kalshi_book": {"ticker": "KXWCGAME-26JUN16FRASEN-FRA", "orderbook": {
                "yes_dollars": [["0.0100", "100.00"], ["0.6900", "568.15"]],
                "no_dollars": [["0.0200", "50.00"], ["0.2900", "300.00"]],
            }},
            "kalshi_candles": {"candlesticks": [
                {"end_period_ts": 1780545600, "price": {"close_dollars": "0.7000"}, "volume_fp": "140.72"},
                {"end_period_ts": 1780549200, "price": {"close_dollars": "0.6900"}, "volume_fp": "10.00"},
            ]},
            "kalshi_trades": {"trades": [{"taker_side": "yes", "count_fp": "5"}]},
        }})
        d = result["data"]
        assert d["source"] == "kalshi"
        assert d["market"]["outcomes"][0]["name"] == "France"
        yes_book = d["book"]["outcomes"][0]
        # Best bid is the HIGHEST yes bid, not the first level.
        assert yes_book["best_bid"] == 0.69
        # Yes asks implied from no bids: 1 - 0.29 = 0.71 best.
        assert yes_book["best_ask"] == 0.71
        assert yes_book["spread"] == 0.02
        assert [h["price"] for h in d["history"]] == [0.7, 0.69]
        assert d["trades"] and d["warnings"] == []

    def test_polymarket_state_full(self):
        # Shapes captured live from Polymarket (Belgium R16, token 7804...).
        result = normalize_market_state({"params": {
            "market_id": "polymarket:2415458",
            "cached": {
                "cache_id": "polymarket:2415458", "source": "polymarket",
                "title": "Will Belgium reach the Round of 16?",
                "outcomes": [
                    {"name": "Yes", "token_id": "tok-yes"},
                    {"name": "No", "token_id": "tok-no"},
                ],
            },
            "poly_books": [{
                "token_id": "tok-yes",
                # CLOB returns bids ascending / asks descending — worst first.
                "bids": [{"price": 0.01, "size": 100.0}, {"price": 0.60, "size": 200.0}],
                "asks": [{"price": 0.99, "size": 300.0}, {"price": 0.62, "size": 50.0}],
            }],
            "poly_history": {"history": [{"t": 1780547104, "p": 0.605}]},
            "poly_last_trade": {"token_id": "tok-yes", "price": 0.62, "side": "BUY"},
        }})
        d = result["data"]
        book = d["book"]["outcomes"][0]
        assert book["name"] == "Yes"
        # Correct best levels despite provider ordering.
        assert book["best_bid"] == 0.60
        assert book["best_ask"] == 0.62
        assert d["history"][0] == {"ts": 1780547104, "price": 0.605, "volume": None}
        assert d["last_trade"]["price"] == 0.62

    def test_unknown_source_rejected(self):
        result = normalize_market_state({"params": {"market_id": "bovada:123"}})
        assert result["status"] is False

    def test_missing_everything_warns(self):
        result = normalize_market_state({"params": {"market_id": "kalshi:KXNOPE-1"}})
        d = result["data"]
        assert d["market"] == {}
        assert len(d["warnings"]) == 3
