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
normalize_standings = _module.normalize_standings
normalize_squads = _module.normalize_squads
normalize_injuries = _module.normalize_injuries
normalize_schedule = _module.normalize_schedule
resolve_player = _module.resolve_player
normalize_identity_crosswalk = _module.normalize_identity_crosswalk
mint_event_identity = _module.mint_event_identity
merge_provider_entities = _module.merge_provider_entities
build_player_crosswalk = _module.build_player_crosswalk
build_event_crosswalk = _module.build_event_crosswalk
link_market_entities = _module.link_market_entities
build_market_snapshots = _module.build_market_snapshots
compute_market_movers = _module.compute_market_movers
compute_coverage_signals = _module.compute_coverage_signals
apply_live_status = _module.apply_live_status
finalize_stale_live_events = getattr(_module, "finalize_stale_live_events", None)
compute_power_ranking = _module.compute_power_ranking
compute_match_probabilities = _module.compute_match_probabilities
build_event_forecasts = _module.build_event_forecasts
compute_model_vs_market_edge = _module.compute_model_vs_market_edge
compute_forecast_audit = _module.compute_forecast_audit
detect_market_edges = _module.detect_market_edges
normalize_fifa_seed = _module.normalize_fifa_seed
select_prematch_fixtures = _module.select_prematch_fixtures
_match_team_urns = _module._match_team_urns
compute_signal = _module.compute_signal
build_signal_ledger_rows = _module.build_signal_ledger_rows
compute_clv = _module.compute_clv
compute_clv_report = _module.compute_clv_report
_result_outcome = _module._result_outcome
pair_cross_source = _module.pair_cross_source


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

    def test_polymarket_game_moneyline_passes_relevance_via_fifwc_slug(self):
        # Game markets are titled by team with no "World Cup" wording; the
        # fifwc-* slug is the only relevance signal (regression for U1).
        record = _poly_record(id="2735826", question="Will Mexico win on 2026-06-30?",
                              slug="fifwc-mex-ecu-2026-06-30-mex",
                              outcomes=[{"name": "Yes", "price": 0.435}, {"name": "No", "price": 0.565}],
                              clob_token_ids=["t-yes", "t-no"])
        result = normalize_market_sources({"params": {"polymarket_markets": {"markets": [record]}}})
        markets = result["data"]["markets"]
        assert len(markets) == 1 and markets[0]["source"] == "polymarket"
        assert markets[0]["title"] == "Will Mexico win on 2026-06-30?"

    def test_foreach_accumulated_polymarket_payloads(self):
        # The per-fixture sweep passes [bulk] + one {'markets': [...]} per
        # foreach iteration; records in every wrapper must be extracted.
        bulk = {"markets": [_poly_record()]}  # futures via "FIFA World Cup" wording
        sweep = {"markets": [_poly_record(id="2735826", question="Will Mexico win on 2026-06-30?",
                                          slug="fifwc-mex-ecu-2026-06-30-mex")]}
        result = normalize_market_sources({"params": {"polymarket_markets": [bulk, sweep]}})
        ids = {m["cache_id"] for m in result["data"]["markets"]}
        assert "polymarket:2735826" in ids and "polymarket:2415458" in ids

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

    def test_placeholder_wide_spread_book_flagged_unreliable(self):
        # Just-listed props quote 0.50/0.50 (sums to 1.0 -> passes the binary
        # check) with a ~0.96 spread — meaningless midpoint, must be flagged.
        record = _poly_record(outcomes=[{"name": "Yes", "price": 0.5}, {"name": "No", "price": 0.5}],
                              spread=0.96, volume=0)
        result = normalize_market_sources({"params": {"polymarket_markets": {"markets": [record]}}})
        assert result["data"]["markets"][0]["price_quality"] == "unreliable"
        # A normal tight book stays ok.
        tight = _poly_record(spread=0.01)
        result2 = normalize_market_sources({"params": {"polymarket_markets": {"markets": [tight]}}})
        assert result2["data"]["markets"][0]["price_quality"] == "ok"

    def test_foreach_accumulated_kalshi_payloads(self):
        # The sync workflow's per-fixture sweep passes a LIST of payload
        # wrappers ([bulk] + one {'markets': [...]} per foreach iteration);
        # records inside every wrapper must be extracted and deduped by ticker.
        bulk = {"markets": [_kalshi_record()]}
        sweep1 = {"markets": [_kalshi_record(ticker="KXWCGAME-26JUN13BRAMAR-BRA",
                                             title="Brazil vs Morocco Winner?",
                                             yes_price=58, volume=157878)]}
        sweep2 = {"markets": [_kalshi_record()]}  # duplicate of bulk record
        result = normalize_market_sources(
            {"params": {"kalshi_markets": [bulk, sweep1, sweep2], "status": "all"}}
        )
        ids = sorted(m["cache_id"] for m in result["data"]["markets"])
        assert ids == ["kalshi:KXWC-BRA", "kalshi:KXWCGAME-26JUN13BRAMAR-BRA"]

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

    def test_limit_clamped_to_500(self):
        # 500, not 250: the full tournament book exceeds 250 and the volume
        # sort was silently dropping the thin tail (near-term draw legs).
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        cached = [self._cached(now, id=f"kalshi:{i}", cache_id=f"kalshi:{i}") for i in range(600)]
        result = filter_cached_markets({"params": {"cached_markets": cached, "limit": 9999}})
        assert result["data"]["count"] == 500

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

    def test_state_refresh_preserves_entity_links(self):
        # The live re-normalization can't know entity links — they must be
        # carried forward from the cached record, or a state read unlinks the
        # market from its fixture and get-signal loses the leg.
        result = normalize_market_state({"params": {
            "market_id": "kalshi:KXWCGAME-26JUN13BRAMAR-MAR",
            "cached": {
                "cache_id": "kalshi:KXWCGAME-26JUN13BRAMAR-MAR", "source": "kalshi",
                "event_urn": "urn:machina:sport:soccer:event:brazil-vs-morocco:20260613:wor",
                "related_team_urns": ["urn:t:bra", "urn:t:mar"],
                "competition_urn": "urn:c:wc2026",
            },
            "kalshi_market": {
                "ticker": "KXWCGAME-26JUN13BRAMAR-MAR", "title": "Brazil vs Morocco Winner?",
                "yes_sub_title": "Morocco", "status": "active",
                "yes_bid_dollars": "0.1700", "no_bid_dollars": "0.8200",
            },
        }})
        m = result["data"]["market"]
        assert m["event_urn"] == "urn:machina:sport:soccer:event:brazil-vs-morocco:20260613:wor"
        assert m["related_team_urns"] == ["urn:t:bra", "urn:t:mar"]
        assert m["competition_urn"] == "urn:c:wc2026"
        # And the refreshed price still comes from the live record.
        assert m["outcomes"][0]["price"] == 0.17

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


detect_market_edges = _module.detect_market_edges
detect_price_move = _module.detect_price_move


def _leg(cache_id, event_id, name, price):
    return {
        "cache_id": cache_id, "source": "kalshi", "source_event_id": event_id,
        "title": "Game", "outcomes": [{"name": name, "price": price}],
    }


class TestDetectMarketEdges:
    def test_within_venue_book_sum_underround(self):
        # Three-way book summing to 0.97 → 300 bps "buy all no" lock.
        cached = [
            _leg("kalshi:G-A", "G", "Colombia", 0.66),
            _leg("kalshi:G-B", "G", "Congo DR", 0.10),
            _leg("kalshi:G-TIE", "G", "Tie", 0.21),
        ]
        r = detect_market_edges({"params": {"cached_markets": cached, "min_edge_bps": 50}})
        cands = r["data"]["edge_candidates"]
        assert len(cands) == 1
        assert cands[0]["candidate_type"] == "within_venue_book_sum"
        assert cands[0]["book_sum"] == 0.97
        assert cands[0]["edge_bps"] == 300
        assert cands[0]["direction"] == "buy_all_no"

    def test_efficient_book_no_edge(self):
        cached = [
            _leg("kalshi:G-A", "G", "A", 0.50),
            _leg("kalshi:G-B", "G", "B", 0.48),
            _leg("kalshi:G-TIE", "G", "Tie", 0.03),
        ]  # sum 1.01 → 100 bps
        r = detect_market_edges({"params": {"cached_markets": cached, "min_edge_bps": 150}})
        assert r["data"]["count"] == 0

    def test_group_qualify_market_not_flagged(self):
        # "Top 2 advance" group markets sum to ~2.0 by design (no draw leg) —
        # must NOT be reported as a book-sum edge.
        cached = [
            _leg("kalshi:Q-MAR", "Q", "Morocco", 0.84),
            _leg("kalshi:Q-BRA", "Q", "Brazil", 0.98),
            _leg("kalshi:Q-SCO", "Q", "Scotland", 0.73),
            _leg("kalshi:Q-HAI", "Q", "Haiti", 0.13),
        ]
        r = detect_market_edges({"params": {"cached_markets": cached, "min_edge_bps": 50}})
        assert r["data"]["count"] == 0

    def test_cross_venue_draw(self):
        cached = [_leg("kalshi:KXWCGAME-26JUN27JORARG-TIE", "KXWCGAME-26JUN27JORARG", "Tie", 0.28)]
        matches = [{
            "title": "Jordan vs. Argentina", "match_method": "code",
            "kalshi": {"market_tickers": ["KXWCGAME-26JUN27JORARG-JOR", "KXWCGAME-26JUN27JORARG-TIE"]},
            "polymarket": {"markets": [
                {"question": "Will Jordan vs. Argentina end in a draw?",
                 "outcomes": [{"name": "Yes", "price": 0.125}, {"name": "No", "price": 0.875}]},
            ]},
        }]
        r = detect_market_edges({"params": {"cached_markets": cached, "matches": matches, "min_edge_bps": 50}})
        cross = [c for c in r["data"]["edge_candidates"] if c["candidate_type"] == "cross_venue_draw"]
        assert len(cross) == 1
        assert cross[0]["kalshi_tie_price"] == 0.28
        assert cross[0]["polymarket_draw_price"] == 0.125
        assert cross[0]["edge_bps"] == 1550
        assert cross[0]["cheaper_venue"] == "polymarket"

    def test_empty_warns(self):
        r = detect_market_edges({"params": {}})
        assert r["data"]["count"] == 0
        assert any("sync" in w for w in r["data"]["warnings"])


class TestDetectPriceMove:
    def test_detects_net_move(self):
        hist = [{"ts": 1, "price": 0.50}, {"ts": 2, "price": 0.55}, {"ts": 3, "price": 0.62}]
        r = detect_price_move({"params": {"history": hist, "min_move_bps": 200}})
        d = r["data"]
        assert d["moved"] is True
        assert d["net_move_bps"] == 1200
        assert d["direction"] == "up"
        assert d["from_price"] == 0.50 and d["to_price"] == 0.62

    def test_swing_within_flat_net(self):
        # Net flat, but a real intraday swing should still register.
        hist = [{"timestamp": 1, "p": 0.50}, {"timestamp": 2, "p": 0.40}, {"timestamp": 3, "p": 0.50}]
        r = detect_price_move({"params": {"history": hist, "min_move_bps": 500}})
        assert r["data"]["swing_bps"] == 1000
        assert r["data"]["moved"] is True

    def test_quiet_market_no_move(self):
        hist = [{"ts": 1, "price": 0.70}, {"ts": 2, "price": 0.705}, {"ts": 3, "price": 0.70}]
        r = detect_price_move({"params": {"history": hist, "min_move_bps": 200}})
        assert r["data"]["moved"] is False

    def test_insufficient_history(self):
        r = detect_price_move({"params": {"history": [{"ts": 1, "price": 0.5}]}})
        assert r["data"]["moved"] is False
        assert r["data"]["warnings"]


class TestEdgeDataQuality:
    def test_duplicate_leg_deduped(self):
        # Two cache docs for the same outcome must count once.
        cached = [
            _leg("kalshi:M-FRA", "M", "France", 0.70),
            _leg("kalshi:M-FRA", "M", "France", 0.70),  # dup
            _leg("kalshi:M-SEN", "M", "Senegal", 0.13),
            _leg("kalshi:M-TIE", "M", "Tie", 0.20),
        ]
        r = detect_market_edges({"params": {"cached_markets": cached, "min_edge_bps": 50}})
        cands = r["data"]["edge_candidates"]
        assert len(cands) == 1
        assert cands[0]["book_sum"] == 1.03  # not 1.73

    def test_zero_priced_tie_excluded_from_book(self):
        cached = [
            _leg("kalshi:M-A", "M", "A", 0.70),
            _leg("kalshi:M-B", "M", "B", 0.13),
            _leg("kalshi:M-TIE", "M", "Tie", 0.0),  # unpriced
        ]
        r = detect_market_edges({"params": {"cached_markets": cached, "min_edge_bps": 50}})
        assert r["data"]["count"] == 0

    def test_zero_kalshi_tie_excluded_cross_venue(self):
        cached = [_leg("kalshi:KXWCGAME-X-TIE", "KXWCGAME-X", "Tie", 0.0)]
        matches = [{
            "title": "A vs. B", "match_method": "code",
            "kalshi": {"market_tickers": ["KXWCGAME-X-TIE"]},
            "polymarket": {"markets": [
                {"question": "Will A vs. B end in a draw?",
                 "outcomes": [{"name": "Yes", "price": 0.30}]},
            ]},
        }]
        r = detect_market_edges({"params": {"cached_markets": cached, "matches": matches, "min_edge_bps": 50}})
        assert not [c for c in r["data"]["edge_candidates"] if c["candidate_type"] == "cross_venue_draw"]


# -- Canonical reads: standings + squads -------------------------------------


def _af_standings(**overrides):
    """Minimal api-football /standings response (one group, two rows)."""
    return {
        "response": [{
            "league": {
                "id": 1, "name": "World Cup", "season": 2026,
                "standings": [[
                    {"rank": 1, "team": {"id": 7, "name": "Uruguay", "logo": "af://7.png"},
                     "points": 6, "goalsDiff": 3, "group": "Group H",
                     "all": {"played": 2, "win": 2, "draw": 0, "lose": 0,
                             "goals": {"for": 4, "against": 1}}},
                    {"rank": 2, "team": {"id": 9, "name": "Spain"},
                     "points": 3, "goalsDiff": 0, "group": "Group H",
                     "all": {"played": 2, "win": 1, "draw": 0, "lose": 1,
                             "goals": {"for": 2, "against": 2}}},
                ]],
            }
        }]
    }


def _ss_standings():
    """Minimal sports-skills get_season_standings payload (with crests)."""
    return {"standings": [{
        "name": "Group H", "type": "TOTAL", "entries": [
            {"position": 1, "team": {"id": "203", "name": "Uruguay", "crest": "espn://uru.png"},
             "played": 2, "won": 2, "drawn": 0, "lost": 0,
             "goals_for": 4, "goals_against": 1, "goal_difference": 3, "points": 6},
            {"position": 2, "team": {"id": "204", "name": "Spain", "crest": "espn://esp.png"},
             "played": 2, "won": 1, "drawn": 0, "lost": 1,
             "goals_for": 2, "goals_against": 2, "goal_difference": 0, "points": 3},
        ],
    }]}


class TestNormalizeStandings:
    def test_af_primary(self):
        r = normalize_standings({"params": {"af": _af_standings(), "season": "2026", "league_id": "1"}})
        assert r["status"] is True
        data = r["data"]
        assert data["source"] == "api-football"
        assert data["group_count"] == 1
        table = data["groups"][0]["table"]
        assert data["groups"][0]["group"] == "Group H"
        assert table[0]["team"] == "Uruguay"
        assert table[0]["points"] == 6 and table[0]["goal_diff"] == 3
        assert table[0]["goals_for"] == 4 and table[0]["goals_against"] == 1

    def test_ss_fallback_when_af_empty(self):
        r = normalize_standings({"params": {"af": {}, "ss": _ss_standings()}})
        assert r["data"]["source"] == "sports-skills"
        assert r["data"]["groups"][0]["table"][0]["crest"] == "espn://uru.png"

    def test_crest_backfill_from_ss(self):
        # Spain has no logo in af; should be backfilled from ss by name.
        r = normalize_standings({"params": {"af": _af_standings(), "ss": _ss_standings()}})
        assert r["data"]["source"] == "api-football"
        rows = {row["team"]: row for row in r["data"]["groups"][0]["table"]}
        assert rows["Uruguay"]["crest"] == "af://7.png"   # af logo kept
        assert rows["Spain"]["crest"] == "espn://esp.png"  # backfilled

    def test_rows_sorted_by_rank(self):
        r = normalize_standings({"params": {"af": _af_standings()}})
        ranks = [row["rank"] for row in r["data"]["groups"][0]["table"]]
        assert ranks == [1, 2]

    def test_empty(self):
        r = normalize_standings({"params": {}})
        assert r["data"]["group_count"] == 0
        assert r["data"]["warnings"]


def _af_squad(team_id, team_name, n=2):
    return {"response": [{
        "team": {"id": team_id, "name": team_name},
        "players": [
            {"id": team_id * 10 + i, "name": f"{team_name} Player {i}",
             "number": i, "position": "Midfielder", "age": 25 + i,
             "photo": f"af://p{i}.png"}
            for i in range(1, n + 1)
        ],
    }]}


class TestNormalizeSquads:
    def test_two_teams(self):
        r = normalize_squads({"params": {
            "home_af": _af_squad(7, "Uruguay", 3),
            "away_af": _af_squad(9, "Spain", 2),
            "home_team": "Uruguay", "away_team": "Spain",
            "home_team_id": 7, "away_team_id": 9,
        }})
        assert r["status"] is True
        teams = {t["side"]: t for t in r["data"]["teams"]}
        assert teams["home"]["team"] == "Uruguay" and teams["home"]["count"] == 3
        assert teams["away"]["count"] == 2
        assert teams["home"]["players"][0]["position"] == "Midfielder"
        assert teams["home"]["source"] == "api-football"

    def test_team_identity_backfilled_from_payload(self):
        # No labels passed; should read team identity from the af response.
        r = normalize_squads({"params": {"home_af": _af_squad(7, "Uruguay", 1)}})
        team = r["data"]["teams"][0]
        assert team["team"] == "Uruguay" and team["team_id"] == 7

    def test_empty_payload_skipped(self):
        r = normalize_squads({"params": {"home_af": {}, "away_af": {}}})
        assert r["data"]["teams"] == []
        assert r["data"]["warnings"]

    def test_ss_fallback_when_af_empty(self):
        # api-football empty (e.g. unauthenticated) -> fall back to ss roster.
        ss_profile = {"team": {"id": "212", "name": "Uruguay", "crest": "espn://uru.png"},
                      "players": [
                          {"id": "1", "name": "Sergio Rochet", "position": "G",
                           "shirt_number": "1", "age": 33, "nationality": "Uruguay"},
                          {"id": "2", "name": "Federico Valverde", "position": "M",
                           "shirt_number": "15", "age": 27, "nationality": "Uruguay"},
                      ]}
        r = normalize_squads({"params": {"home_af": {}, "home_ss": ss_profile}})
        team = r["data"]["teams"][0]
        assert team["source"] == "sports-skills"
        assert team["team"] == "Uruguay" and team["team_id"] == "212"
        assert team["count"] == 2
        # shirt_number maps to number.
        assert team["players"][1]["number"] == "15"

    def test_af_preferred_over_ss(self):
        ss_profile = {"team": {"id": "212", "name": "Uruguay"},
                      "players": [{"id": "x", "name": "Pool Player", "position": "M"}]}
        r = normalize_squads({"params": {
            "home_af": _af_squad(7, "Uruguay", 3), "home_ss": ss_profile,
        }})
        team = r["data"]["teams"][0]
        assert team["source"] == "api-football" and team["count"] == 3


# -- Canonical reads: injuries -----------------------------------------------


def _af_injury(team_id, team_name, player_id, name, reason, itype="Missing Fixture",
               fixture_id=1, ts=1000):
    # Matches the real api-football /injuries shape: type/reason nested in player.
    return {
        "player": {"id": player_id, "name": name, "photo": f"af://p{player_id}.png",
                   "type": itype, "reason": reason},
        "team": {"id": team_id, "name": team_name, "logo": f"af://t{team_id}.png"},
        "fixture": {"id": fixture_id, "timezone": "UTC", "date": "2026-06-26T18:00:00+00:00",
                    "timestamp": ts},
        "league": {"id": 1, "season": 2026, "name": "World Cup"},
    }


class TestNormalizeInjuries:
    def test_filters_to_two_teams_and_maps_fields(self):
        af = {"response": [
            _af_injury(7, "Uruguay", 100, "G. De Arrascaeta", "Calf Injury"),
            _af_injury(9, "Spain", 200, "Fermin Lopez", "Suspended", itype="Questionable"),
            _af_injury(50, "Other", 300, "Someone Else", "Knee Injury"),  # filtered out
        ]}
        r = normalize_injuries({"params": {
            "af": af, "home_team_id": 7, "away_team_id": 9,
            "home_team": "Uruguay", "away_team": "Spain",
        }})
        assert r["status"] is True and r["data"]["source"] == "api-football"
        teams = {t["side"]: t for t in r["data"]["teams"]}
        assert teams["home"]["count"] == 1
        m = teams["home"]["missing"][0]
        assert m["name"] == "G. De Arrascaeta" and m["reason"] == "Calf Injury"
        assert m["type"] == "Missing Fixture" and m["player_id"] == 100
        assert teams["away"]["missing"][0]["reason"] == "Suspended"
        # the third team's player must not leak into either side
        assert all(p["player_id"] != 300 for t in teams.values() for p in t["missing"])

    def test_dedup_keeps_latest_fixture_per_player(self):
        af = {"response": [
            _af_injury(7, "Uruguay", 100, "Player A", "Thigh Injury", fixture_id=1, ts=1000),
            _af_injury(7, "Uruguay", 100, "Player A", "Thigh Injury", fixture_id=2, ts=2000),
        ]}
        r = normalize_injuries({"params": {"af": af, "home_team_id": 7, "home_team": "Uruguay"}})
        team = r["data"]["teams"][0]
        assert team["count"] == 1
        assert team["missing"][0]["fixture_id"] == 2  # most recent kept
        assert "_ts" not in team["missing"][0]         # helper field stripped

    def test_empty_injuries_warns(self):
        r = normalize_injuries({"params": {
            "af": {"response": []}, "home_team_id": 7, "away_team_id": 9,
            "home_team": "Uruguay", "away_team": "Spain",
        }})
        assert len(r["data"]["teams"]) == 2
        assert all(t["count"] == 0 for t in r["data"]["teams"])
        assert any("closer to matchday" in w for w in r["data"]["warnings"])

    def test_accepts_bare_list(self):
        items = [_af_injury(7, "Uruguay", 100, "Player A", "Injury")]
        r = normalize_injuries({"params": {"af": items, "home_team_id": 7, "home_team": "Uruguay"}})
        assert r["data"]["teams"][0]["count"] == 1

    def test_no_team_ids_skips(self):
        r = normalize_injuries({"params": {"af": {"response": []}}})
        assert r["data"]["teams"] == []
        assert r["data"]["warnings"]


# -- Canonical reads: schedule -----------------------------------------------


def _event_doc(urn, name, start, status="NS", home="A", away="B", venue="Stadium", fixture="100"):
    # Mirrors the worldcup:event doc value shape (IPTC summary fields).
    return {
        "_id": urn, "name": name, "start_date": start, "status": status,
        "competition": "World Cup",
        "teams": [
            {"name": home, "sport:qualifier": "home", "schema:logo": f"af://{home}.png"},
            {"name": away, "sport:qualifier": "away", "schema:logo": f"af://{away}.png"},
        ],
        "venue": {"name": venue, "schema:addressLocality": "City"},
        "provider_ids": {"api_football": fixture},
    }


class TestNormalizeSchedule:
    def _events(self):
        return [
            _event_doc("urn:x:1", "Uruguay vs Spain", "2026-06-27T00:00:00+00:00", home="Uruguay", away="Spain"),
            _event_doc("urn:x:2", "Brazil vs Serbia", "2026-06-15T18:00:00+00:00", home="Brazil", away="Serbia"),
            _event_doc("urn:x:3", "France vs Senegal", "2026-06-16T15:00:00+00:00", status="FT", home="France", away="Senegal"),
        ]

    def test_sorted_by_start_and_shaped(self):
        r = normalize_schedule({"params": {"events": self._events()}})
        assert r["status"] is True
        evs = r["data"]["events"]
        assert [e["event_urn"] for e in evs] == ["urn:x:2", "urn:x:3", "urn:x:1"]
        first = evs[0]
        assert first["name"] == "Brazil vs Serbia"
        assert first["venue"] == "Stadium" and first["fixture_id"] == "100"
        assert {t["qualifier"] for t in first["teams"]} == {"home", "away"}
        assert first["teams"][0]["crest"] == "af://Brazil.png"

    def test_team_filter(self):
        r = normalize_schedule({"params": {"events": self._events(), "team": "spain"}})
        assert [e["event_urn"] for e in r["data"]["events"]] == ["urn:x:1"]

    def test_event_free_text_resolves_fixture(self):
        # The landing's contract: {"event": "Brazil vs Morocco"} must resolve.
        r = normalize_schedule({"params": {"events": self._events(), "event": "Uruguay vs Spain"}})
        assert [e["event_urn"] for e in r["data"]["events"]] == ["urn:x:1"]
        # Alternate separators and reversed order also pin the fixture.
        r2 = normalize_schedule({"params": {"events": self._events(), "event": "spain x uruguay"}})
        assert [e["event_urn"] for e in r2["data"]["events"]] == ["urn:x:1"]
        # Single-team text falls back to a team filter.
        r3 = normalize_schedule({"params": {"events": self._events(), "event": "Brazil"}})
        assert [e["event_urn"] for e in r3["data"]["events"]] == ["urn:x:2"]
        # Explicit team/opponent take precedence over event text.
        r4 = normalize_schedule({"params": {"events": self._events(),
                                            "event": "Uruguay vs Spain", "team": "france"}})
        assert [e["event_urn"] for e in r4["data"]["events"]] == ["urn:x:3"]

    def test_team_and_opponent_pin_single_fixture(self):
        # "Uruguay vs Spain" resolves uniquely; same team without the opponent would
        # match nothing extra here, but team+opponent is how callers resolve "X vs Y".
        r = normalize_schedule({"params": {"events": self._events(),
                                           "team": "uruguay", "opponent": "spain"}})
        assert [e["event_urn"] for e in r["data"]["events"]] == ["urn:x:1"]
        # Opponent that doesn't share a fixture with the team yields nothing.
        r2 = normalize_schedule({"params": {"events": self._events(),
                                            "team": "uruguay", "opponent": "serbia"}})
        assert r2["data"]["events"] == []

    def test_date_range_inclusive(self):
        r = normalize_schedule({"params": {"events": self._events(),
                                           "date_from": "2026-06-15", "date_to": "2026-06-16"}})
        urns = {e["event_urn"] for e in r["data"]["events"]}
        assert urns == {"urn:x:2", "urn:x:3"}

    def test_status_filter(self):
        r = normalize_schedule({"params": {"events": self._events(), "status": "FT"}})
        assert [e["event_urn"] for e in r["data"]["events"]] == ["urn:x:3"]

    def test_limit_and_empty_warns(self):
        r = normalize_schedule({"params": {"events": self._events(), "limit": 1}})
        assert len(r["data"]["events"]) == 1
        r2 = normalize_schedule({"params": {"events": [], "team": "nobody"}})
        assert r2["data"]["events"] == [] and r2["data"]["warnings"]


# -- Identity resolution: player ----------------------------------------------


def _player_doc(urn, name, team, nationality="", position="Attacker"):
    return {"_id": urn, "@id": urn, "id": urn, "@type": ["sport:IdentityCrosswalk", "sport:Player"],
            "name": name, "position": position, "nationality": nationality,
            "team": {"@id": "urn:t:" + team.lower(), "name": team}, "provider_ids": {}}


class TestResolvePlayer:
    def _players(self):
        return [
            _player_doc("urn:p:vinicius", "Vinícius Júnior", "Brazil", "Brazil"),
            _player_doc("urn:p:rodrygo", "Rodrygo", "Brazil", "Brazil"),
            _player_doc("urn:p:hakimi", "Achraf Hakimi", "Morocco", "Morocco", position="Defender"),
            _player_doc("urn:p:rodri", "Rodri", "Spain", "Spain", position="Midfielder"),
        ]

    def test_accent_insensitive_match(self):
        r = resolve_player({"params": {"players": self._players(), "player": "vinicius junior"}})
        assert r["data"]["player"]["player_urn"] == "urn:p:vinicius"
        assert r["data"]["warnings"] == []

    def test_partial_name_with_team_filter(self):
        r = resolve_player({"params": {"players": self._players(), "player": "hakimi", "team": "morocco"}})
        assert r["data"]["player"]["player_urn"] == "urn:p:hakimi"

    def test_exact_slug_ranks_before_superstring(self):
        # "rodri" is a substring of "rodrygo"'s slug? (no) but of nothing here;
        # exact match must outrank any longer candidate that also contains it.
        r = resolve_player({"params": {"players": self._players(), "player": "Rodri"}})
        assert r["data"]["player"]["player_urn"] == "urn:p:rodri"

    def test_no_match_warns_and_skips_non_players(self):
        team_doc = {"_id": "urn:t:bra", "@type": ["sport:IdentityCrosswalk", "sport:Team"],
                    "name": "Brazil", "team": {}}
        r = resolve_player({"params": {"players": self._players() + [team_doc], "player": "Brazil"}})
        assert r["data"]["player"] == {} and r["data"]["candidates"] == []
        assert r["data"]["warnings"]

    def test_empty_query_warns(self):
        r = resolve_player({"params": {"players": self._players(), "player": ""}})
        assert r["data"]["player"] == {} and r["data"]["warnings"]

    def test_real_iptc_doc_shape(self):
        # The actual worldcup:event value is raw IPTC: schema:startDate,
        # sport:status, sport:competitors, sport:venue, sport:competition.
        iptc = {
            "_id": "urn:apifootball:sport_event:1489417",
            "name": "Uruguay vs Spain - World Cup",
            "schema:startDate": "2026-06-27T00:00:00+00:00",
            "sport:status": "NS",
            "sport:competition": {"@type": "sport:Competition", "name": "World Cup"},
            "sport:venue": {"@type": "sport:Venue", "name": "Estadio Akron"},
            "sport:competitors": [
                {"name": "Uruguay", "sport:qualifier": "home", "schema:logo": "u.png"},
                {"name": "Spain", "sport:qualifier": "away", "schema:logo": "s.png"},
            ],
            "provider_ids": {"api_football": "1489417"},
        }
        r = normalize_schedule({"params": {"events": [iptc], "team": "spain"}})
        ev = r["data"]["events"][0]
        assert ev["event_urn"] == "urn:apifootball:sport_event:1489417"
        assert ev["start_date"] == "2026-06-27T00:00:00+00:00"
        assert ev["status"] == "ns"
        assert ev["competition"] == "World Cup"
        assert ev["venue"] == "Estadio Akron"
        assert ev["fixture_id"] == "1489417"
        assert {t["name"] for t in ev["teams"]} == {"Uruguay", "Spain"}


class TestNormalizeIdentityCrosswalk:
    def test_player_urn_uses_birth_date_and_country_to_avoid_same_name_collisions(self):
        result = normalize_identity_crosswalk({"params": {"items": [
            {
                "type": "player",
                "name": "Luis Suárez Jr.",
                "birth_date": "1987-01-24",
                "country": "Uruguay",
                "provider_ids": {"api_football": "123", "entain": "p-9"},
                "source_evidence": [{"provider": "api_football", "id": "123"}],
            }
        ]}})
        doc = result["data"]["normalized_items"][0]
        assert doc["@id"] == "urn:machina:sport:soccer:player:luis-suarez:19870124:ury"
        assert doc["metadata"] == {"entity_urn": doc["@id"]}
        assert doc["provider_ids"] == {"api_football": "123", "entain": "p-9"}
        assert doc["mapping_status"]["verified_ids_only"] is True
        assert doc["source_evidence"] == [{"provider": "api_football", "id": "123"}]

    def test_same_team_names_are_country_scoped(self):
        result = normalize_identity_crosswalk({"params": {"items": [
            {"type": "team", "name": "Georgia", "country": "Georgia", "provider_ids": {"api_football": "1"}},
            {"type": "team", "name": "Georgia", "country": "United States", "provider_ids": {"espn": "uga"}},
        ]}})
        urns = [d["@id"] for d in result["data"]["normalized_items"]]
        assert urns == [
            "urn:machina:sport:soccer:team:georgia:geo",
            "urn:machina:sport:soccer:team:georgia:usa",
        ]

    def test_event_and_competition_documents_use_standard_metadata_keys(self):
        result = normalize_identity_crosswalk({"params": {"items": [
            {"type": "event", "home_team": "Brazil", "away_team": "Serbia", "date": "2026-06-15", "provider_ids": {"entain": "2:7811126"}},
            {"type": "competition", "name": "FIFA World Cup 2026", "scope": "world", "provider_ids": {"entain": "102868"}},
        ]}})
        event, competition = result["data"]["normalized_items"]
        assert event["@id"] == "urn:machina:sport:soccer:event:brazil-vs-serbia:20260615:wor"
        assert event["metadata"] == {"event_urn": event["@id"]}
        assert competition["@id"] == "urn:machina:sport:soccer:competition:fifa-world-cup-2026:wor"
        assert competition["metadata"] == {"entity_urn": competition["@id"]}

    def test_force_disambiguator_adds_verified_provider_hash_suffix(self):
        result = normalize_identity_crosswalk({"params": {"items": [
            {
                "type": "player",
                "name": "Same Name",
                "birth_date": "2000-01-01",
                "country": "Brazil",
                "provider_ids": {"provider_a": "abc"},
                "force_disambiguator": True,
            }
        ]}})
        urn = result["data"]["normalized_items"][0]["@id"]
        assert urn.startswith("urn:machina:sport:soccer:player:same-name:20000101:bra:")
        assert len(urn.rsplit(":", 1)[-1]) == 8


# -- Canonical event identity (machina URN) ----------------------------------


def _af_fixture(**overrides):
    base = {
        "fixture": {"id": 1489417, "date": "2026-06-27T00:00:00+00:00",
                    "status": {"short": "NS"},
                    "venue": {"id": 1076, "name": "Estadio Akron", "city": "Guadalajara"}},
        "league": {"id": 1, "name": "World Cup"},
        "teams": {"home": {"id": 7, "name": "Uruguay", "logo": "u.png"},
                  "away": {"id": 9, "name": "Spain", "logo": "s.png"}},
    }
    base.update(overrides)
    return base


class TestMintEventIdentity:
    def test_machina_urns_and_provider_ids(self):
        d = mint_event_identity({"params": {"fixtures": [_af_fixture()]}})["data"]["events"][0]
        assert d["_id"] == d["@id"] == d["metadata"]["event_urn"]
        assert d["_id"] == "urn:machina:sport:soccer:event:uruguay-vs-spain:20260627:wor"
        assert d["sport:competition"]["@id"] == "urn:machina:sport:soccer:competition:fifa-world-cup-2026:wor"
        comps = {c["sport:qualifier"]: c["@id"] for c in d["sport:competitors"]}
        assert comps["home"] == "urn:machina:sport:soccer:team:uruguay:ury"
        assert comps["away"] == "urn:machina:sport:soccer:team:spain:esp"
        assert d["provider_ids"] == {"api_football": "1489417"}
        assert d["sport:status"] == "NS"

    def test_full_iso_date_not_degraded_to_year(self):
        # Regression: trailing \b in _event_date dropped the day/month on ISO datetimes.
        d = mint_event_identity({"params": {"fixtures": [_af_fixture()]}})["data"]["events"][0]
        assert ":20260627:wor" in d["_id"]

    def test_null_venue_omits_urn_no_none_string(self):
        fx = _af_fixture()
        fx["fixture"]["venue"] = {"id": None, "name": None}
        d = mint_event_identity({"params": {"fixtures": [fx]}})["data"]["events"][0]
        assert "@id" not in d["sport:venue"]
        assert "None" not in d["_id"]
        assert "api_football_venue_id" not in d["provider_ids"]

    def test_idempotent_urn_for_same_fixture(self):
        a = mint_event_identity({"params": {"fixtures": [_af_fixture()]}})["data"]["events"][0]
        b = mint_event_identity({"params": {"fixtures": [_af_fixture()]}})["data"]["events"][0]
        assert a["_id"] == b["_id"]

    def test_skips_fixture_missing_ids(self):
        fx = _af_fixture()
        fx["teams"]["home"] = {}
        r = mint_event_identity({"params": {"fixtures": [fx]}})
        assert r["data"]["events"] == []
        assert r["data"]["warnings"]

    def test_carries_forward_crosswalk_event_ids(self):
        # Existing event doc holds crosswalk-added ids; re-mint must preserve them.
        existing = [{"provider_ids": {"api_football_fixture_id": "1489417",
                                      "sportradar_event_id": "sr:sport_event:123",
                                      "entain_event_id": "7722030"}}]
        d = mint_event_identity({"params": {"fixtures": [_af_fixture()],
                                            "existing_events": existing}})["data"]["events"][0]
        assert d["provider_ids"]["sportradar"] == "sr:sport_event:123"
        assert d["provider_ids"]["entain"] == "7722030"
        # Ingest still owns the api_football (fixture) id.
        assert d["provider_ids"]["api_football"] == "1489417"


# -- Provider entity merge (identity crosswalk producer) ---------------------


class TestMergeProviderEntities:
    def test_iso3_join_converges_name_variants(self):
        r = merge_provider_entities({"params": {
            "api_football_teams": [{"id": "17", "name": "Korea Republic"}, {"id": "7", "name": "Uruguay"}],
            "espn_teams": [{"id": "451", "name": "South Korea"}, {"id": "212", "name": "Uruguay"}],
        }})["data"]
        assert r["count"] == 2
        by_name = {it["name"]: it for it in r["items"]}
        # canonical name comes from api_football ("Korea Republic", not "South Korea")
        assert "Korea Republic" in by_name
        assert by_name["Korea Republic"]["provider_ids"] == {"api_football": "17", "espn": "451"}
        assert by_name["Uruguay"]["provider_ids"] == {"api_football": "7", "espn": "212"}
        assert r["provider_summary"] == {"api_football": 2, "espn": 2}

    def test_only_id_provider_creates_entity_when_api_football_missing(self):
        r = merge_provider_entities({"params": {"espn_teams": [{"id": "99", "name": "Wales"}]}})["data"]
        assert r["items"][0]["provider_ids"] == {"espn": "99"}
        assert r["items"][0]["name"] == "Wales"

    def test_unmapped_names_do_not_collide(self):
        # Two distinct names that fall back to "unk" must not merge into one.
        r = merge_provider_entities({"params": {"api_football_teams": [
            {"id": "1", "name": "Zzzland"}, {"id": "2", "name": "Qqqstan"},
        ]}})["data"]
        assert r["count"] == 2

    def test_skips_incomplete_rows_and_warns_when_empty(self):
        r = merge_provider_entities({"params": {"api_football_teams": [{"id": "", "name": "X"}, {"name": "NoId"}]}})["data"]
        assert r["count"] == 0
        assert r["warnings"]


# -- Provider entity merge (identity crosswalk producer) ---------------------


class TestMergeProviderEntities:
    def test_iso3_join_converges_name_variants(self):
        r = merge_provider_entities({"params": {
            "api_football_teams": [{"id": "17", "name": "Korea Republic"}, {"id": "7", "name": "Uruguay"}],
            "espn_teams": [{"id": "451", "name": "South Korea"}, {"id": "212", "name": "Uruguay"}],
        }})["data"]
        by_name = {it["name"]: it for it in r["items"]}
        assert r["count"] == 2
        # canonical name from api_football ("Korea Republic", not ESPN's "South Korea")
        assert by_name["Korea Republic"]["provider_ids"] == {"api_football": "17", "espn": "451"}
        assert by_name["Uruguay"]["provider_ids"] == {"api_football": "7", "espn": "212"}

    def test_enrich_only_provider_attaches_but_never_creates(self):
        # Sportradar lists a superset (incl. teams not in the 48). It should only
        # attach to existing canonical teams, never add new ones.
        r = merge_provider_entities({"params": {
            "api_football_teams": [{"id": "7", "name": "Uruguay"}],
            "sportradar_teams": [
                {"id": "sr:competitor:1", "name": "Uruguay"},      # matches -> attaches
                {"id": "sr:competitor:9", "name": "Scotland"},     # not in 48 -> skipped
            ],
        }})["data"]
        assert r["count"] == 1
        assert r["items"][0]["provider_ids"] == {"api_football": "7", "sportradar": "sr:competitor:1"}

    def test_canonical_provider_creates_entity(self):
        r = merge_provider_entities({"params": {"espn_teams": [{"id": "99", "name": "Wales"}]}})["data"]
        assert r["count"] == 1 and r["items"][0]["provider_ids"] == {"espn": "99"}

    def test_unmapped_names_do_not_collide(self):
        r = merge_provider_entities({"params": {"api_football_teams": [
            {"id": "1", "name": "Zzzland"}, {"id": "2", "name": "Qqqstan"},
        ]}})["data"]
        assert r["count"] == 2

    def test_warns_when_empty(self):
        r = merge_provider_entities({"params": {}})["data"]
        assert r["count"] == 0 and r["warnings"]


# -- iso3 accent normalization + Opta enrich convergence ---------------------

_to_iso3 = _module._to_iso3


class TestIso3AccentNormalization:
    def test_accents_and_variants_converge(self):
        assert _to_iso3("Cape Verde Islands") == _to_iso3("Cabo Verde") == "cpv"
        assert _to_iso3("Ivory Coast") == _to_iso3("Côte d'Ivoire") == "civ"
        assert _to_iso3("Türkiye") == _to_iso3("Turkey") == "tur"
        assert _to_iso3("Korea Republic") == _to_iso3("South Korea") == "kor"

    def test_opta_names_enrich_canonical_team_by_iso3(self):
        # Opta's "Cabo Verde"/"Côte d'Ivoire" must attach to api-football's
        # "Cape Verde Islands"/"Ivory Coast" — enrich-only, by iso3.
        r = merge_provider_entities({"params": {
            "api_football_teams": [{"id": "1533", "name": "Cape Verde Islands"},
                                   {"id": "1501", "name": "Ivory Coast"}],
            "opta_teams": [{"id": "opta-cpv", "name": "Cabo Verde"},
                           {"id": "opta-civ", "name": "Côte d'Ivoire"},
                           {"id": "opta-x", "name": "Kenya"}],  # not in 48 -> skipped
        }})["data"]
        by_name = {it["name"]: it for it in r["items"]}
        assert r["count"] == 2
        assert by_name["Cape Verde Islands"]["provider_ids"] == {"api_football": "1533", "opta": "opta-cpv"}
        assert by_name["Ivory Coast"]["provider_ids"] == {"api_football": "1501", "opta": "opta-civ"}


# -- Player crosswalk (api-football canonical, others enrich by team+name) ----


class TestBuildPlayerCrosswalk:
    def _teams(self):
        return [{"_id": "urn:machina:sport:soccer:team:spain:esp", "name": "Spain", "country": "Spain",
                 "provider_ids": {"api_football": "9", "opta": "o-esp"}}]

    def test_af_canonical_plus_opta_enrich(self):
        af = [{"response": [{"team": {"id": 9}, "players": [
            {"id": 386828, "name": "Lamine Yamal", "position": "Attacker"}]}]}]
        afp = [{"response": [{"player": {"id": 386828, "name": "Lamine Yamal",
                                          "birth": {"date": "2007-07-13"}}}]}]
        opta = {"squad": [{"contestantId": "o-esp", "person": [
            {"id": "o-yamal", "firstName": "Lamine", "lastName": "Yamal", "type": "player"}]}]}
        r = build_player_crosswalk({"params": {"teams": self._teams(), "af_squads": af,
                                               "af_players": afp, "opta_squads": opta}})["data"]
        d = r["normalized_items"][0]
        assert r["count"] == 1
        assert d["_id"] == "urn:machina:sport:soccer:player:lamine-yamal:20070713:esp"
        assert d["provider_ids"] == {"api_football": "386828", "opta": "o-yamal"}
        assert d["team"]["@id"] == "urn:machina:sport:soccer:team:spain:esp"
        assert "sport:Player" in d["@type"]

    def test_unmatched_opta_name_leaves_af_only(self):
        af = [{"response": [{"team": {"id": 9}, "players": [{"id": "44", "name": "Rodri"}]}]}]
        afp = [{"response": [{"player": {"id": 44, "name": "Rodri", "birth": {"date": "1996-06-22"}}}]}]
        opta = {"squad": [{"contestantId": "o-esp", "person": [
            {"id": "o-r", "firstName": "Rodrigo", "lastName": "Hernandez", "type": "player"}]}]}
        r = build_player_crosswalk({"params": {"teams": self._teams(), "af_squads": af,
                                               "af_players": afp, "opta_squads": opta}})["data"]
        assert r["normalized_items"][0]["provider_ids"] == {"api_football": "44"}

    def test_empty_warns(self):
        r = build_player_crosswalk({"params": {}})["data"]
        assert r["count"] == 0 and r["warnings"]

    def test_player_without_dob_is_excluded(self):
        af = [{"response": [{"team": {"id": 9}, "players": [{"id": "44", "name": "Rodri"}]}]}]
        r = build_player_crosswalk({"params": {"teams": self._teams(), "af_squads": af}})["data"]
        assert r["count"] == 0
        assert r["provider_summary"]["excluded_no_dob"] == 1

    def test_dob_from_af_players_plus_espn_id(self):
        teams = [{"_id": "urn:machina:sport:soccer:team:spain:esp", "name": "Spain", "country": "Spain",
                  "provider_ids": {"api_football": "9", "opta": "o-esp", "espn": "e-esp"}}]
        af_squads = [{"response": [{"team": {"id": 9}, "players": [
            {"id": "386828", "name": "Lamine Yamal", "position": "Attacker"}]}]}]
        af_players = [{"response": [{"player": {
            "id": 386828, "name": "Lamine Yamal", "birth": {"date": "2007-07-13"}, "nationality": "Spain"}}]}]
        espn = {"team": {"id": "e-esp"}, "players": [{"id": "espn-yamal", "name": "Lamine Yamal"}]}
        r = build_player_crosswalk({"params": {"teams": teams, "af_squads": af_squads,
                                               "af_players": af_players, "espn_rosters": [espn]}})["data"]
        d = r["normalized_items"][0]
        assert d["_id"] == "urn:machina:sport:soccer:player:lamine-yamal:20070713:esp"
        assert d["birth_date"] == "2007-07-13"
        assert d["provider_ids"] == {"api_football": "386828", "espn": "espn-yamal"}
        assert r["provider_summary"]["with_dob"] == 1

    def test_players_full_name_overrides_abbreviated_squad_name(self):
        teams = [{"_id": "urn:machina:sport:soccer:team:uruguay:ury", "name": "Uruguay", "country": "Uruguay",
                  "provider_ids": {"api_football": "7"}}]
        # Squad name is abbreviated; /players carries the full name.
        af_squads = [{"response": [{"team": {"id": 7}, "players": [
            {"id": "429", "name": "F. Muslera", "position": "Goalkeeper"}]}]}]
        af_players = [{"response": [{"player": {
            "id": 429, "firstname": "Fernando", "lastname": "Muslera",
            "name": "Fernando Muslera", "birth": {"date": "1986-06-16"}, "nationality": "Uruguay"}}]}]
        r = build_player_crosswalk({"params": {"teams": teams, "af_squads": af_squads,
                                               "af_players": af_players}})["data"]
        d = r["normalized_items"][0]
        assert d["_id"] == "urn:machina:sport:soccer:player:fernando-muslera:19860616:ury"
        assert d["name"] == "Fernando Muslera"
        assert d["birth_date"] == "1986-06-16"

    def test_carry_forward_entain_transfermarkt_by_af_id(self):
        teams = [{"_id": "urn:machina:sport:soccer:team:argentina:arg", "name": "Argentina", "country": "Argentina",
                  "provider_ids": {"api_football": "26"}}]
        af_squads = [{"response": [{"team": {"id": 26}, "players": [
            {"id": "154", "name": "L. Messi", "position": "Attacker"}]}]}]
        af_players = [{"response": [{"player": {
            "id": 154, "firstname": "Lionel", "lastname": "Messi", "name": "Lionel Messi",
            "birth": {"date": "1987-06-24"}, "nationality": "Argentina"}}]}]
        # Legacy doc uses the *_player_id key style; ids must be inherited + renamed.
        existing = [{"provider_ids": {"api_football_player_id": "154",
                                      "entain_player_id": "223306",
                                      "transfermarkt_player_id": "28003"}}]
        r = build_player_crosswalk({"params": {"teams": teams, "af_squads": af_squads,
                                               "af_players": af_players, "existing_players": existing}})["data"]
        d = r["normalized_items"][0]
        assert d["_id"] == "urn:machina:sport:soccer:player:lionel-messi:19870624:arg"
        assert d["provider_ids"] == {"api_football": "154", "entain": "223306", "transfermarkt": "28003"}

    def test_profiles_abbreviated_name_falls_back_to_firstlast(self):
        teams = [{"_id": "urn:machina:sport:soccer:team:uruguay:ury", "name": "Uruguay", "country": "Uruguay",
                  "provider_ids": {"api_football": "7"}}]
        af = [{"response": [{"team": {"id": 7}, "players": [{"id": "5995", "name": "N. de la Cruz"}]}]}]
        # /players/profiles abbreviates `name` but carries full firstname/lastname.
        afp = [{"response": [{"player": {"id": 5995, "name": "N. de la Cruz",
                                          "firstname": "Diego Nicolás", "lastname": "de la Cruz Arcosa",
                                          "birth": {"date": "1997-06-01"}}}]}]
        r = build_player_crosswalk({"params": {"teams": teams, "af_squads": af, "af_players": afp}})["data"]
        d = r["normalized_items"][0]
        assert d["name"] == "Diego Nicolás de la Cruz Arcosa"
        assert d["_id"] == "urn:machina:sport:soccer:player:diego-nicolas-de-la-cruz-arcosa:19970601:ury"


class TestBuildEventCrosswalk:
    def _teams(self):
        return [
            {"_id": "urn:machina:sport:soccer:team:mexico:mex", "name": "Mexico",
             "provider_ids": {"sportradar": "sr:competitor:4781", "entain": "234216"}},
            {"_id": "urn:machina:sport:soccer:team:south-africa:zaf", "name": "South Africa",
             "provider_ids": {"sportradar": "sr:competitor:4736", "entain": "201277"}},
        ]

    def _events(self):
        return [{
            "_id": "urn:machina:sport:soccer:event:mexico-vs-south-africa:20260611:wor",
            "sport:competitors": [
                {"@id": "urn:machina:sport:soccer:team:mexico:mex"},
                {"@id": "urn:machina:sport:soccer:team:south-africa:zaf"},
            ],
            "provider_ids": {"api_football": "1489369"},
        }]

    def test_attaches_sportradar_and_entain_event_ids(self):
        sr = {"schedules": [{"sport_event": {"id": "sr:sport_event:66456904", "competitors": [
            {"id": "sr:competitor:4781"}, {"id": "sr:competitor:4736"}]}}]}
        bwin = {"items": [{"id": {"entityId": 7722030, "full": "2:7722030"},
                           "participants": [{"id": 201277}, {"id": 234216}]}]}
        r = build_event_crosswalk({"params": {"teams": self._teams(), "events": self._events(),
                                              "sportradar_schedule": sr, "entain_fixtures": bwin}})["data"]
        ev = r["normalized_items"][0]
        assert ev["provider_ids"]["api_football"] == "1489369"
        assert ev["provider_ids"]["sportradar"] == "sr:sport_event:66456904"
        assert ev["provider_ids"]["entain"] == "7722030"
        assert ev["metadata"]["event_urn"] == "urn:machina:sport:soccer:event:mexico-vs-south-africa:20260611:wor"
        assert r["provider_summary"] == {"events": 1, "sportradar": 1, "entain": 1, "opta": 0}

    def test_unmatched_pair_is_left_untouched(self):
        # sportradar event for a different pair (one unknown competitor) → no attach.
        sr = {"schedules": [{"sport_event": {"id": "sr:sport_event:999", "competitors": [
            {"id": "sr:competitor:4781"}, {"id": "sr:competitor:0000"}]}}]}
        r = build_event_crosswalk({"params": {"teams": self._teams(), "events": self._events(),
                                              "sportradar_schedule": sr}})["data"]
        assert "sportradar_event_id" not in r["normalized_items"][0]["provider_ids"]
        assert r["provider_summary"]["sportradar"] == 0


def test_build_event_crosswalk_opta():
    teams = [
        {"_id": "urn:machina:sport:soccer:team:mexico:mex", "provider_ids": {"opta": "4vofb84dzb5fyc81n2ssws6ah"}},
        {"_id": "urn:machina:sport:soccer:team:south-africa:zaf", "provider_ids": {"opta": "xmip8t9f2kefltjkraxzsxl9"}},
    ]
    events = [{"_id": "urn:machina:sport:soccer:event:mexico-vs-south-africa:20260611:wor",
               "sport:competitors": [{"@id": "urn:machina:sport:soccer:team:mexico:mex"},
                                     {"@id": "urn:machina:sport:soccer:team:south-africa:zaf"}],
               "provider_ids": {"api_football": "1489369"}}]
    opta = {"matchDate": [{"match": [{"id": "4tcpns1nwyc0jtpucgzj9dp90",
            "homeContestantId": "4vofb84dzb5fyc81n2ssws6ah", "awayContestantId": "xmip8t9f2kefltjkraxzsxl9"}]}]}
    r = build_event_crosswalk({"params": {"teams": teams, "events": events, "opta_schedule": opta}})["data"]
    assert r["normalized_items"][0]["provider_ids"]["opta"] == "4tcpns1nwyc0jtpucgzj9dp90"
    assert r["provider_summary"]["opta"] == 1


def test_build_player_crosswalk_sportradar():
    teams = [{"_id": "urn:machina:sport:soccer:team:belgium:bel", "name": "Belgium", "country": "Belgium",
              "provider_ids": {"api_football": "1", "sportradar": "sr:competitor:4717"}}]
    af_squads = [{"response": [{"team": {"id": 1}, "players": [{"id": "100", "name": "Axel Witsel"}]}]}]
    af_players = [{"response": [{"player": {"id": 100, "name": "Axel Witsel", "firstname": "Axel",
                  "lastname": "Witsel", "birth": {"date": "1989-01-12"}}}]}]
    sr = [{"competitor": {"id": "sr:competitor:4717"}, "players": [{"id": "sr:player:35612", "name": "Witsel, Axel"}]}]
    r = build_player_crosswalk({"params": {"teams": teams, "af_squads": af_squads,
            "af_players": af_players, "sportradar_rosters": sr}})["data"]
    d = r["normalized_items"][0]
    assert d["provider_ids"]["sportradar"] == "sr:player:35612"
    assert d["provider_ids"]["api_football"] == "100"


class TestLinkMarketEntities:
    def _teams(self):
        return [
            {"_id": "urn:machina:sport:soccer:team:brazil:bra", "name": "Brazil"},
            {"_id": "urn:machina:sport:soccer:team:haiti:hti", "name": "Haiti"},
            {"_id": "urn:machina:sport:soccer:team:czech-republic:cze", "name": "Czech Republic"},
            {"_id": "urn:machina:sport:soccer:team:south-africa:zaf", "name": "South Africa"},
        ]

    def _events(self):
        return [{"_id": "urn:machina:sport:soccer:event:brazil-vs-haiti:20260619:wor",
                 "sport:competitors": [{"@id": "urn:machina:sport:soccer:team:brazil:bra"},
                                       {"@id": "urn:machina:sport:soccer:team:haiti:hti"}]}]

    def test_game_market_links_teams_and_event(self):
        markets = [{"cache_id": "kalshi:x", "title": "Brazil vs Haiti Winner?",
                    "slug": "KXWCGAME-26JUN19BRAHTI-BRA", "outcomes": [{"name": "Brazil"}, {"name": "No"}]}]
        r = link_market_entities({"params": {"markets": markets, "teams": self._teams(), "events": self._events()}})["data"]
        m = r["normalized_markets"][0]
        assert m["competition_urn"] == "urn:machina:sport:soccer:competition:fifa-world-cup-2026:wor"
        assert set(m["related_team_urns"]) == {"urn:machina:sport:soccer:team:brazil:bra", "urn:machina:sport:soccer:team:haiti:hti"}
        assert m["event_urn"] == "urn:machina:sport:soccer:event:brazil-vs-haiti:20260619:wor"

    def test_outright_market_single_team_no_event(self):
        markets = [{"cache_id": "poly:y", "title": "Will Brazil win the 2026 FIFA World Cup?", "slug": "", "outcomes": []}]
        r = link_market_entities({"params": {"markets": markets, "teams": self._teams(), "events": self._events()}})["data"]
        m = r["normalized_markets"][0]
        assert m["related_team_urns"] == ["urn:machina:sport:soccer:team:brazil:bra"]
        assert m["event_urn"] is None

    def test_alias_czechia_matches_czech_republic(self):
        markets = [{"cache_id": "k:z", "title": "Will Czechia advance?", "slug": "", "outcomes": []}]
        r = link_market_entities({"params": {"markets": markets, "teams": self._teams(), "events": self._events()}})["data"]
        assert r["normalized_markets"][0]["related_team_urns"] == ["urn:machina:sport:soccer:team:czech-republic:cze"]

    def test_no_team_market_empty(self):
        markets = [{"cache_id": "k:w", "title": "2026 World Cup - Top Goalscorer", "slug": "", "outcomes": []}]
        r = link_market_entities({"params": {"markets": markets, "teams": self._teams(), "events": self._events()}})["data"]
        assert r["normalized_markets"][0]["related_team_urns"] == []
        assert r["normalized_markets"][0]["event_urn"] is None


class TestMarketSnapshotsAndMovers:
    def test_snapshot_id_is_hourly_and_slim(self):
        markets = [{"cache_id": "kalshi:x", "source": "kalshi", "title": "Brazil vs Haiti Winner?",
                    "fetched_at": "2026-06-06T15:17:27.989043Z",
                    "outcomes": [{"name": "Brazil", "price": 0.9}, {"name": "No", "price": 0.1}],
                    "volume": 100, "event_urn": "urn:e", "related_team_urns": ["urn:t"]}]
        r = build_market_snapshots({"params": {"markets": markets}})["data"]
        s = r["snapshots"][0]
        assert s["metadata"]["snapshot_id"] == "kalshi:x:2026-06-06T15"
        assert s["primary_name"] == "Brazil" and s["primary_price"] == 0.9
        assert s["ts"] == "2026-06-06T15:17:27.989043Z"

    def test_movers_rank_by_abs_delta(self):
        markets = [
            {"cache_id": "m1", "title": "A", "source": "kalshi", "outcomes": [{"name": "Yes", "price": 0.90}]},
            {"cache_id": "m2", "title": "B", "source": "poly", "outcomes": [{"name": "Yes", "price": 0.50}]},
        ]
        snaps = [
            {"cache_id": "m1", "ts": "2026-06-06T10:00:00Z", "primary_price": 0.88},
            {"cache_id": "m1", "ts": "2026-06-06T08:00:00Z", "primary_price": 0.70},  # earliest = baseline
            {"cache_id": "m2", "ts": "2026-06-06T09:00:00Z", "primary_price": 0.49},
        ]
        r = compute_market_movers({"params": {"markets": markets, "snapshots": snaps, "limit": 10}})["data"]
        assert r["movers"][0]["cache_id"] == "m1"
        assert r["movers"][0]["price_then"] == 0.70
        assert r["movers"][0]["delta"] == 0.2
        assert r["movers"][1]["cache_id"] == "m2"
        assert r["movers"][1]["delta"] == 0.01

    def test_movers_skips_markets_without_baseline(self):
        markets = [{"cache_id": "new", "title": "N", "source": "kalshi", "outcomes": [{"name": "Yes", "price": 0.5}]}]
        r = compute_market_movers({"params": {"markets": markets, "snapshots": [], "limit": 10}})["data"]
        assert r["movers"] == []


class TestCoverageCadence:
    def _ev(self, urn, start, status="NS", fid=None):
        d = {"_id": urn, "schema:startDate": start, "sport:status": status}
        if fid:
            d["provider_ids"] = {"api_football": fid}
        return d

    def test_coverage_signals_phases(self):
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        iso = lambda dt: dt.isoformat()
        events = [
            self._ev("urn:live-window", iso(now - timedelta(minutes=30))),     # kicked off 30m ago → live
            self._ev("urn:live-status", iso(now - timedelta(minutes=160)), "ET"),  # explicit in-play → live
            self._ev("urn:upcoming", iso(now + timedelta(hours=2))),           # upcoming 24h
            self._ev("urn:done", iso(now - timedelta(hours=4))),               # finished window
            self._ev("urn:far", iso(now + timedelta(days=3))),                 # neither
        ]
        r = compute_coverage_signals({"params": {"events": events}})["data"]
        assert r["has_live"] is True
        assert set(r["live_event_urns"]) == {"urn:live-window", "urn:live-status"}
        assert r["live_count"] == 2
        assert r["upcoming_24h"] == 1
        assert r["recent_done"] == 1

    def test_coverage_signals_none_live(self):
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        events = [self._ev("urn:far", (now + timedelta(days=5)).isoformat())]
        r = compute_coverage_signals({"params": {"events": events}})["data"]
        assert r["has_live"] is False and r["live_event_urns"] == []

    def test_coverage_signals_demotes_stale_regular_time_status(self):
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        events = [
            {
                **self._ev("urn:stale", (now - timedelta(hours=5)).isoformat(), "2H"),
                "live_score": {"home": 1, "away": 1, "elapsed": 90},
            }
        ]
        r = compute_coverage_signals({"params": {"events": events}})["data"]
        assert r["has_live"] is False
        assert r["live_event_urns"] == []
        assert r["recent_done"] == 1

    def test_apply_live_status_merges_score(self):
        events = [
            self._ev("urn:machina:sport:soccer:event:brazil-vs-haiti:20260620:wor",
                     "2026-06-20T00:30:00+00:00", "NS", fid="1489389"),
            self._ev("urn:other", "2026-06-21T00:00:00+00:00", "NS", fid="999"),
        ]
        live = {"response": [{"fixture": {"id": 1489389, "status": {"short": "2H", "elapsed": 67}},
                              "goals": {"home": 2, "away": 0}}]}
        r = apply_live_status({"params": {"events": events, "live_fixtures": live}})["data"]
        assert r["count"] == 1
        d = r["normalized_items"][0]
        assert d["_id"].endswith("brazil-vs-haiti:20260620:wor")
        assert d["sport:status"] == "2H"
        assert d["live_score"] == {"home": 2, "away": 0, "elapsed": 67}
        assert d["metadata"]["event_urn"].endswith("brazil-vs-haiti:20260620:wor")

    def test_finalize_stale_live_events_marks_regular_time_docs_ft(self):
        assert callable(finalize_stale_live_events)
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        events = [
            {
                **self._ev("urn:stale", (now - timedelta(hours=5)).isoformat(), "2H", fid="1489389"),
                "live_score": {"home": 1, "away": 1, "elapsed": 90},
            },
            {
                **self._ev("urn:extra-time", (now - timedelta(minutes=160)).isoformat(), "ET", fid="1489390"),
                "live_score": {"home": 1, "away": 1, "elapsed": 105},
            },
        ]
        r = finalize_stale_live_events({"params": {"events": events}})["data"]
        assert r["count"] == 1
        d = r["normalized_items"][0]
        assert d["_id"] == "urn:stale"
        assert d["sport:status"] == "FT"
        assert d["live_score"] == {"home": 1, "away": 1}
        assert d["metadata"]["event_urn"] == "urn:stale"

    def test_live_writers_overwrite_stray_metadata(self):
        # Regression: a loaded value carrying a stray/empty `metadata` must be
        # overwritten with the canonical {event_urn}, else the (metadata, name)
        # upsert forks a duplicate event doc (observed: Colombia vs Portugal).
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        live_ev = self._ev("urn:machina:sport:soccer:event:brazil-vs-haiti:20260620:wor",
                            "2026-06-20T00:30:00+00:00", "NS", fid="1489389")
        live_ev["metadata"] = {}
        live = {"response": [{"fixture": {"id": 1489389, "status": {"short": "2H", "elapsed": 67}},
                              "goals": {"home": 2, "away": 0}}]}
        d = apply_live_status({"params": {"events": [live_ev], "live_fixtures": live}})["data"]["normalized_items"][0]
        assert d["metadata"] == {"event_urn": "urn:machina:sport:soccer:event:brazil-vs-haiti:20260620:wor"}

        stale_ev = {
            **self._ev("urn:stale", (now - timedelta(hours=5)).isoformat(), "2H", fid="1489389"),
            "live_score": {"home": 1, "away": 1, "elapsed": 90},
            "metadata": {},
        }
        d = finalize_stale_live_events({"params": {"events": [stale_ev]}})["data"]["normalized_items"][0]
        assert d["metadata"] == {"event_urn": "urn:stale"}


def _ranking(power, gpg=1.4, conf=0.8, source="results"):
    return {"power_score": power, "breakdown": {"attack_score": power, "defense_score": power},
            "metrics": {"goals_per_game": gpg}, "confidence": conf, "data_source": source}


class TestComputeMatchProbabilities:
    def test_probabilities_sum_to_one(self):
        r = compute_match_probabilities({"params": {
            "home_ranking": _ranking(0.6), "away_ranking": _ranking(0.6),
            "xg_params": {"home_advantage": 0.0}}})["data"]
        p = r["probabilities"]
        assert abs(p["home_win"] + p["draw"] + p["away_win"] - 1.0) < 1e-3
        assert abs(p["over_2_5"] + p["under_2_5"] - 1.0) < 1e-3
        assert r["disclaimer"]

    def test_symmetry_equal_rankings_no_home_adv(self):
        p = compute_match_probabilities({"params": {
            "home_ranking": _ranking(0.6), "away_ranking": _ranking(0.6),
            "xg_params": {"home_advantage": 0.0}}})["data"]["probabilities"]
        assert abs(p["home_win"] - p["away_win"]) < 1e-9

    def test_favorite_ordering(self):
        r = compute_match_probabilities({"params": {
            "home_ranking": _ranking(0.95, gpg=2.2, conf=1.0),
            "away_ranking": _ranking(0.1, gpg=0.6, conf=1.0)}})["data"]
        assert r["probabilities"]["home_win"] > r["probabilities"]["away_win"]
        assert r["home_expected_goals"] > r["away_expected_goals"]

    def test_rho_raises_draw_mass(self):
        base = {"home_ranking": _ranking(0.6), "away_ranking": _ranking(0.6),
                "xg_params": {"home_advantage": 0.0}}
        d0 = compute_match_probabilities({"params": dict(base, rho=0.0)})["data"]["probabilities"]["draw"]
        dn = compute_match_probabilities({"params": dict(base, rho=-0.15)})["data"]["probabilities"]["draw"]
        assert dn > d0

    def test_rho_clamped(self):
        r = compute_match_probabilities({"params": {
            "home_ranking": _ranking(0.6), "away_ranking": _ranking(0.6), "rho": -5.0}})["data"]
        assert r["correlation_rho"] == -0.20


class TestComputePowerRanking:
    FIX = [
        {"fixture": {"id": "1", "status": {"short": "FT"}},
         "teams": {"home": {"name": "Aland"}, "away": {"name": "Bland"}}, "goals": {"home": 3, "away": 0}},
        {"fixture": {"id": "2", "status": {"short": "FT"}},
         "teams": {"home": {"name": "Aland"}, "away": {"name": "Cland"}}, "goals": {"home": 2, "away": 1}},
        {"fixture": {"id": "3", "status": {"short": "FT"}},
         "teams": {"home": {"name": "Bland"}, "away": {"name": "Cland"}}, "goals": {"home": 0, "away": 2}},
    ]

    def test_winner_outranks_loser(self):
        rk = compute_power_ranking({"params": {"finished_fixtures": self.FIX,
                                               "min_games_full_confidence": 2}})["data"]["rankings"]
        order = [r["team_name"] for r in rk]
        assert order.index("Aland") < order.index("Bland")
        for r in rk:
            assert 0.0 <= r["power_score"] <= 1.0
        assert [r["rank"] for r in rk] == list(range(1, len(rk) + 1))

    def test_degenerate_single_team(self):
        one = [self.FIX[0]]
        rk = compute_power_ranking({"params": {"finished_fixtures": one}})["data"]["rankings"]
        for r in rk:
            assert 0.0 <= r["power_score"] <= 1.0  # no divide-by-zero

    def test_bootstrap_blend(self):
        seed = [{"team_urn": _module._machina_team_urn("Aland"), "team_name": "Aland", "seed_rating": 0.9}]
        rk = compute_power_ranking({"params": {"finished_fixtures": [self.FIX[0]],
                                               "min_games_full_confidence": 5, "seed_ratings": seed}})["data"]
        aland = [r for r in rk["rankings"] if r["team_name"] == "Aland"][0]
        assert aland["data_source"] == "blend"
        assert aland["confidence"] < 1.0

    def test_seed_only_team_when_no_games(self):
        seed = [{"team_urn": "urn:machina:sport:soccer:team:dland:dla", "team_name": "Dland", "seed_rating": 0.7}]
        rk = compute_power_ranking({"params": {"finished_fixtures": self.FIX, "seed_ratings": seed}})["data"]
        dland = [r for r in rk["rankings"] if r["team_name"] == "Dland"][0]
        assert dland["data_source"] == "seed"
        assert dland["power_score"] == 0.7

    def test_default_min_games_full_confidence_after_group_stage(self):
        # Default min_games is 3: a COMPLETED group stage (3 games) yields full
        # results confidence so the pre-tournament FIFA seed washes out
        # (data_source "results", blend_w = 1.0) for the knockout phase.
        fix = self.FIX + [
            {"fixture": {"id": "4", "status": {"short": "FT"}},
             "teams": {"home": {"name": "Aland"}, "away": {"name": "Dland"}}, "goals": {"home": 1, "away": 1}},
        ]  # Aland now has 3 games (fixtures 1, 2, 4) — a full group stage.
        seed = [{"team_urn": _module._machina_team_urn("Aland"), "team_name": "Aland", "seed_rating": 0.9}]
        rk = compute_power_ranking({"params": {"finished_fixtures": fix, "seed_ratings": seed}})["data"]
        assert rk["min_games_full_confidence"] == 3
        aland = [r for r in rk["rankings"] if r["team_name"] == "Aland"][0]
        assert aland["games"] == 3
        assert aland["data_source"] == "results"
        assert aland["confidence"] == 1.0


class TestForecastAudit:
    PERFECT = {"probabilities": {"home_win": 1, "draw": 0, "away_win": 0, "over_2_5": 1, "under_2_5": 0},
               "most_likely_score": "2-0", "_id": "e1"}
    WORST = {"probabilities": {"home_win": 0, "draw": 0, "away_win": 1}, "most_likely_score": "0-2", "_id": "e2"}

    def test_perfect_prediction(self):
        a = compute_forecast_audit({"params": {"mode": "single", "forecast": self.PERFECT,
                                               "actual_result": {"home_goals": 2, "away_goals": 0}}})["data"]["audit_result"]
        assert a["brier_scores"]["combined_1x2"] == 0.0
        assert a["calibration"]["prediction_correct"] is True
        assert a["exact_score_correct"] is True

    def test_worst_prediction(self):
        a = compute_forecast_audit({"params": {"mode": "single", "forecast": self.WORST,
                                               "actual_result": {"home_goals": 2, "away_goals": 0}}})["data"]["audit_result"]
        assert abs(a["brier_scores"]["combined_1x2"] - (1 + 0 + 1) / 3) < 1e-3
        assert a["calibration"]["prediction_correct"] is False

    def test_calibration_bin(self):
        fc = {"probabilities": {"home_win": 0.55, "draw": 0.25, "away_win": 0.20}, "most_likely_score": "1-0", "_id": "e3"}
        a = compute_forecast_audit({"params": {"mode": "single", "forecast": fc,
                                               "actual_result": {"home_goals": 1, "away_goals": 0}}})["data"]["audit_result"]
        assert a["calibration"]["calibration_bin"] == 5
        assert a["calibration"]["calibration_bin_label"] == "50-60%"

    def test_batch_matches_by_fixture_id(self):
        fc = dict(self.PERFECT, provider_ids={"api_football": "111"})
        fixtures = [{"fixture": {"id": 111, "status": {"short": "FT"}}, "goals": {"home": 2, "away": 0}}]
        r = compute_forecast_audit({"params": {"mode": "batch", "forecasts": [fc],
                                               "finished_fixtures": fixtures}})["data"]
        assert r["count"] == 1

    def test_aggregate_baseline_and_sample_gate(self):
        audits = []
        for _ in range(3):
            audits.append(compute_forecast_audit({"params": {"mode": "single", "forecast": self.PERFECT,
                                                             "actual_result": {"home_goals": 2, "away_goals": 0}}})["data"]["audit_result"])
        rep = compute_forecast_audit({"params": {"mode": "aggregate", "audit_results": audits}})["data"]["backtesting_report"]
        assert rep["brier_scores"]["is_better_than_random"] is True
        assert rep["sample_size_sufficient"] is False  # only 3 < 50


class TestModelVsMarketEdge:
    def test_gap_math(self):
        r = compute_model_vs_market_edge({"params": {
            "model_probabilities": {"home_win": 0.60, "draw": 0.25, "away_win": 0.15},
            "market_outcomes": [{"name": "Aland", "price": 0.50}, {"name": "Draw", "price": 0.25}],
            "home_team": "Aland", "away_team": "Bland", "min_gap_bps": 100}})["data"]
        hw = [g for g in r["gaps"] if g["outcome"] == "home_win"][0]
        assert hw["gap_bps"] == 1000
        assert hw["model_richer"] is True
        assert r["disclaimer"]

    def test_zero_price_skipped_and_threshold(self):
        r = compute_model_vs_market_edge({"params": {
            "model_probabilities": {"home_win": 0.51, "away_win": 0.49},
            "market_outcomes": [{"name": "Aland", "price": 0.0}, {"name": "Bland", "price": 0.50}],
            "home_team": "Aland", "away_team": "Bland", "min_gap_bps": 100}})["data"]
        # Aland skipped (price 0); Bland gap = |0.49-0.50| = 100 bps -> below threshold filtered
        assert all(g["outcome"] != "home_win" for g in r["gaps"])


class TestDetectMarketEdgesBackwardCompat:
    def test_no_forecasts_param_unchanged(self):
        r = detect_market_edges({"params": {"cached_markets": []}})["data"]
        assert "edge_candidates" in r and r["count"] == 0

    def test_forecasts_append_model_vs_market(self):
        cached = [{"cache_id": "kalshi:x", "event_urn": "urn:ev:1", "source": "kalshi",
                   "source_event_id": "x", "title": "Aland vs Bland",
                   "outcomes": [{"name": "Aland", "price": 0.50}]}]
        forecasts = [{"_id": "urn:ev:1", "probabilities": {"home_win": 0.70, "draw": 0.2, "away_win": 0.1},
                      "home_team": {"name": "Aland"}, "away_team": {"name": "Bland"}}]
        r = detect_market_edges({"params": {"cached_markets": cached, "forecasts": forecasts,
                                            "min_edge_bps": 100}})["data"]
        mvm = [c for c in r["edge_candidates"] if c["candidate_type"] == "model_vs_market"]
        assert len(mvm) == 1 and mvm[0]["edge_bps"] == 2000

    def test_model_vs_market_matches_by_team_pair_without_event_urn(self):
        # Market has NO event_urn, only related_team_urns -> still joins by pair.
        cached = [{"cache_id": "kalshi:y", "source": "kalshi", "source_event_id": "y",
                   "title": "Aland vs Bland", "related_team_urns": ["urn:t:bla", "urn:t:ala"],
                   "outcomes": [{"name": "Aland", "price": 0.50}]}]
        forecasts = [{"_id": "urn:ev:2", "probabilities": {"home_win": 0.70, "draw": 0.2, "away_win": 0.1},
                      "home_team": {"name": "Aland", "urn": "urn:t:ala"},
                      "away_team": {"name": "Bland", "urn": "urn:t:bla"}}]
        r = detect_market_edges({"params": {"cached_markets": cached, "forecasts": forecasts,
                                            "min_edge_bps": 100}})["data"]
        mvm = [c for c in r["edge_candidates"] if c["candidate_type"] == "model_vs_market"]
        assert len(mvm) == 1 and mvm[0]["edge_bps"] == 2000


def test_build_event_forecasts_from_index():
    event = {"_id": "urn:machina:sport:soccer:event:aland-vs-bland:20260612:wor",
             "schema:startDate": "2026-06-12T18:00:00+00:00",
             "provider_ids": {"api_football": "555"},
             "sport:competitors": [
                 {"@id": "urn:machina:sport:soccer:team:aland:ala", "name": "Aland", "sport:qualifier": "home"},
                 {"@id": "urn:machina:sport:soccer:team:bland:bla", "name": "Bland", "sport:qualifier": "away"}]}
    team_index = {"urn:machina:sport:soccer:team:aland:ala": _ranking(0.8, conf=1.0),
                  "urn:machina:sport:soccer:team:bland:bla": _ranking(0.3, conf=1.0)}
    r = build_event_forecasts({"params": {"events": [event], "team_index": team_index}})["data"]
    assert r["count"] == 1
    fc = r["forecasts"][0]
    assert fc["_id"] == event["_id"]
    assert fc["metadata"]["event_urn"] == event["_id"]
    assert abs(sum([fc["probabilities"]["home_win"], fc["probabilities"]["draw"],
                    fc["probabilities"]["away_win"]]) - 1.0) < 1e-3
    assert fc["disclaimer"]


def test_normalize_fifa_seed_band_and_order():
    r = normalize_fifa_seed({"params": {"rankings": [
        {"team_name": "Strongland", "points": 2000},
        {"team_name": "Midland", "points": 1500},
        {"team_name": "Weakland", "points": 1000}]}})["data"]
    seeds = {s["team_name"]: s["seed_rating"] for s in r["seed_ratings"]}
    assert seeds["Strongland"] == 0.8 and seeds["Weakland"] == 0.2  # [0.2, 0.8] band
    assert seeds["Strongland"] > seeds["Midland"] > seeds["Weakland"]
    assert r["count"] == 3
    assert r["basis"] == "points"


def test_normalize_fifa_seed_rank_fallback():
    # No points -> fall back to rank (1 = strongest -> top of band).
    r = normalize_fifa_seed({"params": {"rankings": [
        {"team_name": "Topland", "rank": 1},
        {"team_name": "Midland", "rank": 25},
        {"team_name": "Lowland", "rank": 50}]}})["data"]
    seeds = {s["team_name"]: s["seed_rating"] for s in r["seed_ratings"]}
    assert r["basis"] == "rank"
    assert seeds["Topland"] == 0.8 and seeds["Lowland"] == 0.2
    assert seeds["Topland"] > seeds["Midland"] > seeds["Lowland"]


def test_normalize_fifa_seed_resolves_canonical_urn_from_teams():
    # A name variant resolves to the canonical crosswalk URN, not a re-derived one.
    r = normalize_fifa_seed({"params": {
        "rankings": [{"team_name": "South Korea", "rank": 1}, {"team_name": "Japan", "rank": 2}],
        "teams": [{"team_name": "South Korea", "team_urn": "urn:machina:sport:soccer:team:korea-republic:kor"},
                  {"team_name": "Japan", "team_urn": "urn:machina:sport:soccer:team:japan:jpn"}]}})["data"]
    urns = {s["team_name"]: s["team_urn"] for s in r["seed_ratings"]}
    assert urns["South Korea"] == "urn:machina:sport:soccer:team:korea-republic:kor"


NOW = "2026-06-13T12:00:00Z"


def _ev_pm(urn, start, status="NS", enriched=None):
    d = {"_id": urn, "schema:startDate": start, "sport:status": status}
    if enriched:
        d["prematch_research_at"] = enriched
    return d


class TestSelectPrematchFixtures:
    def test_finished_and_long_past_excluded(self):
        events = [
            _ev_pm("a", "2026-06-13T14:00:00Z"),                 # +2h upcoming
            _ev_pm("b", "2026-06-12T12:00:00Z", status="FT"),   # finished
            _ev_pm("c", "2026-06-13T00:00:00Z"),                 # kicked off 12h ago
        ]
        r = select_prematch_fixtures({"params": {"events": events, "now_iso": NOW}})["data"]
        urns = [f["_id"] for f in r["fixtures"]]
        assert urns == ["a"]

    def test_nearest_kickoff_first(self):
        events = [
            _ev_pm("far", "2026-06-20T12:00:00Z"),
            _ev_pm("near", "2026-06-13T15:00:00Z"),
            _ev_pm("mid", "2026-06-15T12:00:00Z"),
        ]
        r = select_prematch_fixtures({"params": {"events": events, "now_iso": NOW}})["data"]
        assert [f["_id"] for f in r["fixtures"]] == ["near", "mid", "far"]

    def test_countdown_tier_staleness(self):
        # Imminent (+2h, <24h tier -> 2h interval): enriched 1h ago = not due; 3h ago = due.
        fresh = _ev_pm("fresh", "2026-06-13T14:00:00Z", enriched="2026-06-13T11:00:00Z")  # 1h ago
        stale = _ev_pm("stale", "2026-06-13T14:00:00Z", enriched="2026-06-13T08:00:00Z")  # 4h ago
        r = select_prematch_fixtures({"params": {"events": [fresh, stale], "now_iso": NOW}})["data"]
        assert [f["_id"] for f in r["fixtures"]] == ["stale"]

    def test_far_fixture_longer_interval(self):
        # +8d (>168h tier -> 72h interval): enriched 2 days ago = NOT due.
        ev = _ev_pm("x", "2026-06-21T12:00:00Z", enriched="2026-06-11T12:00:00Z")
        r = select_prematch_fixtures({"params": {"events": [ev], "now_iso": NOW}})["data"]
        assert r["count"] == 0

    def test_force_and_limit(self):
        events = [_ev_pm(str(i), "2026-06-1%dT12:00:00Z" % (4 + i), enriched=NOW) for i in range(5)]
        # All enriched "now" -> none due normally; force overrides; limit caps.
        r = select_prematch_fixtures({"params": {"events": events, "now_iso": NOW, "force": True, "limit": 2}})["data"]
        assert r["count"] == 2


class TestFuzzyTeamMatch:
    INDEX = [("brazil", "u:bra"), ("morocco", "u:mar"), ("iran", "u:irn"),
             ("iraq", "u:irq"), ("england", "u:eng"), ("croatia", "u:cro")]

    def test_exact_pair_unchanged(self):
        assert _match_team_urns("brazil-vs-morocco-winner", self.INDEX) == ["u:bra", "u:mar"]

    def test_iran_does_not_match_iraq(self):
        # Exact finds iran; fuzzy must NOT add iraq (ratio 0.75 < 0.88).
        assert _match_team_urns("iran-winner", self.INDEX) == ["u:irn"]

    def test_fuzzy_fills_typo(self):
        # "ngland" misses exact; fuzzy fills england alongside exact croatia.
        out = _match_team_urns("ngland-vs-croatia", self.INDEX)
        assert set(out) == {"u:eng", "u:cro"}


def test_build_event_forecasts_skips_unknown_team():
    event = {"_id": "urn:ev:z", "sport:competitors": [
        {"@id": "urn:unknown:a", "name": "A", "sport:qualifier": "home"},
        {"@id": "urn:unknown:b", "name": "B", "sport:qualifier": "away"}]}
    r = build_event_forecasts({"params": {"events": [event], "team_index": {}}})["data"]
    assert r["count"] == 0 and "urn:ev:z" in r["skipped"]


class TestMarketDataQuality:
    def test_degenerate_kalshi_outright_flagged(self):
        # Sparse outright payload (yes_bid 100c / no_bid 98c) -> Yes 1.0 / No 0.98 (sum 1.98).
        rec = {"ticker": "KXMENWORLDCUP-26-JP", "title": "Will the Japan win the 2026 Men's World Cup?",
               "event_ticker": "KXMENWORLDCUP-26", "yes_bid": 100, "no_bid": 98, "volume": 123}
        m = _module._normalize_record("kalshi", rec, "2026-06-06T00:00:00Z")
        assert m["price_quality"] == "unreliable"
        assert any("unreliable" in n.lower() for n in m["resolution_risk_notes"])

    def test_normal_binary_ok_and_spread_computed(self):
        rec = {"ticker": "KXWCGAME-X-ENG", "title": "England vs Croatia Winner?",
               "yes_sub_title": "England", "yes_bid_dollars": "0.56",
               "yes_ask_dollars": "0.57", "no_bid_dollars": "0.43"}
        m = _module._normalize_record("kalshi", rec, "2026-06-06T00:00:00Z")
        assert m["price_quality"] == "ok"
        assert m["spread"] == 0.01

    def test_movers_skips_unreliable(self):
        markets = [
            {"cache_id": "kalshi:JP", "source": "kalshi", "price_quality": "unreliable",
             "outcomes": [{"name": "Yes", "price": 1.0}], "title": "Japan win WC"},
            {"cache_id": "kalshi:G", "source": "kalshi", "price_quality": "ok",
             "outcomes": [{"name": "Brazil", "price": 0.6}], "title": "Brazil vs X"},
        ]
        snaps = [{"cache_id": "kalshi:JP", "ts": "2026-06-06T10:00:00", "primary_price": 0.02},
                 {"cache_id": "kalshi:G", "ts": "2026-06-06T10:00:00", "primary_price": 0.5}]
        r = compute_market_movers({"params": {"markets": markets, "snapshots": snaps, "limit": 10}})["data"]
        cids = [m["cache_id"] for m in r["movers"]]
        assert "kalshi:JP" not in cids and "kalshi:G" in cids

    def test_edges_exclude_unreliable(self):
        cached = [{"cache_id": "kalshi:JP", "source": "kalshi", "source_event_id": "KXMENWORLDCUP-26",
                   "price_quality": "unreliable", "title": "Japan win WC",
                   "outcomes": [{"name": "Yes", "price": 1.0}]}]
        r = detect_market_edges({"params": {"cached_markets": cached}})["data"]
        assert r["count"] == 0

    def test_snapshots_skip_unreliable(self):
        markets = [
            {"cache_id": "kalshi:JP", "source": "kalshi", "price_quality": "unreliable",
             "fetched_at": "2026-06-06T20:00:00Z", "outcomes": [{"name": "Yes", "price": 1.0}]},
            {"cache_id": "kalshi:G", "source": "kalshi", "price_quality": "ok",
             "fetched_at": "2026-06-06T20:00:00Z", "outcomes": [{"name": "Brazil", "price": 0.6}]},
        ]
        r = build_market_snapshots({"params": {"markets": markets}})["data"]
        cids = [s["cache_id"] for s in r["snapshots"]]
        assert cids == ["kalshi:G"]


def test_standings_separates_third_place_ranking():
    af = {"response": [{"league": {"standings": [
        [{"rank": 1, "group": "Group A", "team": {"id": 1, "name": "Mexico"}, "all": {}, "points": 0}],
        [{"rank": 1, "group": "Ranking of third-placed teams", "team": {"id": 2, "name": "Foo"}, "all": {}, "points": 0}],
    ]}}]}
    r = normalize_standings({"params": {"af": af, "league_id": "1", "season": "2026"}})["data"]
    assert r["group_count"] == 1
    assert len(r["groups"]) == 1 and r["groups"][0]["group"] == "Group A"
    assert len(r["third_place_ranking"]) == 1


def _sig_forecast(probs=None, confidence=0.8, data_source="results", flags=None):
    return {"_id": "urn:ev:1", "schema:startDate": "2026-06-13T22:00:00+00:00",
            "home_team": {"name": "Brazil", "urn": "u:bra"},
            "away_team": {"name": "Morocco", "urn": "u:mar"},
            "probabilities": probs or {"home_win": 0.60, "draw": 0.25, "away_win": 0.15},
            "confidence": confidence, "data_source": data_source, "flags": flags or []}


def _ok(source, name, price, liquidity=5000, spread=0.01):
    return {"source": source, "price_quality": "ok", "liquidity": liquidity, "spread": spread,
            "outcomes": [{"name": name, "price": price}]}


class TestComputeSignal:
    def test_value_pick_line_shop_devig_and_bankroll(self):
        markets = [_ok("kalshi", "Brazil", 0.55), _ok("polymarket", "Brazil", 0.50),
                   _ok("kalshi", "Draw", 0.30), _ok("kalshi", "Morocco", 0.22),
                   {"source": "kalshi", "price_quality": "unreliable", "outcomes": [{"name": "Brazil", "price": 0.01}]}]
        r = compute_signal({"params": {"forecast": _sig_forecast(), "markets": markets,
                                       "event_urn": "urn:ev:1", "bankroll": 1000}})["data"]
        sig = r["signal"]
        home = [l for l in sig["legs"] if l["outcome"] == "home_win"][0]
        assert home["best_price"] == 0.50 and home["best_venue"] == "polymarket"  # line-shop + unreliable ignored
        assert home["edge"] == 0.10 and home["ev_per_dollar"] == 0.20 and home["kelly_full"] == 0.20
        assert home["stake_pct"] == 5.0 and home["stake_amount"] == 50.0  # quarter-Kelly * 1000
        assert home["recommendation"] == "value"
        assert sig["vig_pct"] == 2.0  # 0.50+0.30+0.22 = 1.02
        assert r["top_pick"]["outcome"] == "home_win"
        assert "Value: back Brazil" in r["recommendation"]

    def test_no_edge(self):
        fc = _sig_forecast(probs={"home_win": 0.50, "draw": 0.27, "away_win": 0.23})
        r = compute_signal({"params": {"forecast": fc, "markets": [_ok("kalshi", "Brazil", 0.52)]}})["data"]
        leg = r["signal"]["legs"][0]
        assert leg["recommendation"] == "no_edge" and leg["kelly_full"] == 0.0
        assert r["top_pick"] is None

    def test_low_confidence_huge_edge_suppressed(self):
        fc = _sig_forecast(probs={"home_win": 0.90, "draw": 0.07, "away_win": 0.03},
                           confidence=0.15, data_source="seed")
        r = compute_signal({"params": {"forecast": fc, "markets": [_ok("kalshi", "Brazil", 0.50)]}})["data"]
        leg = r["signal"]["legs"][0]
        assert "edge_likely_model_noise" in leg["risk_flags"]
        assert "model_low_confidence" in leg["risk_flags"]
        assert r["top_pick"] is None  # noise leg never becomes the pick

    def test_empty_forecast_graceful(self):
        r = compute_signal({"params": {"forecast": {}, "markets": [_ok("kalshi", "Brazil", 0.5)]}})["data"]
        assert r["signal"] == {} and r["top_pick"] is None and r["warnings"]

    def test_kelly_matches_betting_formula(self):
        # (p - price)/(1 - price) — parity with the sports-skills betting skill.
        r = compute_signal({"params": {"forecast": _sig_forecast(), "markets": [_ok("kalshi", "Brazil", 0.50)]}})["data"]
        leg = r["signal"]["legs"][0]
        assert leg["kelly_full"] == round((0.60 - 0.50) / (1 - 0.50), 4)

    def test_signal_buckets_sparse_kalshi_legs(self):
        # End-to-end: sparse Kalshi legs (team in subtitle, "-TIE" ticker) normalize so
        # compute_signal buckets home/draw/away by the team-named YES outcome.
        recs = [
            {"ticker": "KXWCGAME-X-BRA", "title": "Brazil vs Morocco Winner?", "subtitle": "Brazil", "yes_bid": 50, "no_bid": 49},
            {"ticker": "KXWCGAME-X-MAR", "title": "Brazil vs Morocco Winner?", "subtitle": "Morocco", "yes_bid": 22, "no_bid": 77},
            {"ticker": "KXWCGAME-X-TIE", "title": "Brazil vs Morocco Winner?", "yes_bid": 28, "no_bid": 71},
        ]
        markets = [_module._normalize_record("kalshi", r, "2026-06-06T00:00:00Z") for r in recs]
        r = compute_signal({"params": {"forecast": _sig_forecast(), "markets": markets}})["data"]
        buckets = {l["outcome"]: l["best_price"] for l in r["signal"]["legs"]}
        assert buckets == {"home_win": 0.50, "away_win": 0.22, "draw": 0.28}
        assert r["top_pick"]["outcome"] == "home_win"


def test_kalshi_sparse_payload_names_team_from_subtitle():
    rec = {"ticker": "KXWCGAME-26JUN19SCOMAR-MAR", "title": "Scotland vs Morocco Winner?",
           "subtitle": "Morocco", "yes_bid": 49, "no_bid": 50}
    m = _module._normalize_record("kalshi", rec, "2026-06-06T00:00:00Z")
    assert "Morocco" in [o["name"] for o in m["outcomes"]]


def test_kalshi_tie_leg_named_tie():
    rec = {"ticker": "KXWCGAME-26JUN19SCOMAR-TIE", "title": "Scotland vs Morocco Winner?",
           "yes_bid": 28, "no_bid": 71}
    m = _module._normalize_record("kalshi", rec, "2026-06-06T00:00:00Z")
    assert m["outcomes"][0]["name"] == "Tie"


def test_signal_net_of_fees():
    fc, mk = _sig_forecast(), [_ok("kalshi", "Brazil", 0.50)]
    gross = compute_signal({"params": {"forecast": fc, "markets": mk}})["data"]["signal"]["legs"][0]
    net = compute_signal({"params": {"forecast": fc, "markets": mk, "fee_bps": 200}})["data"]["signal"]["legs"][0]
    assert gross["edge"] == 0.10 and net["gross_edge"] == 0.10        # gross unchanged
    assert net["edge"] == 0.08 and net["effective_price"] == 0.52     # net of 200bps fee
    assert net["ev_per_dollar"] < gross["ev_per_dollar"] and net["fee_bps"] == 200


def test_signal_confidence_tier_and_fair_odds():
    # ~1000bps edge, results-confidence -> medium; fair odds for p=0.60 -> -150 / 1.67.
    leg = compute_signal({"params": {"forecast": _sig_forecast(), "markets": [_ok("kalshi", "Brazil", 0.50)]}})["data"]["signal"]["legs"][0]
    assert leg["confidence_tier"] == "medium"
    assert leg["fair_american"] == -150 and leg["fair_decimal"] == 1.67


def test_signal_noise_edge_tier_low():
    fc = _sig_forecast(probs={"home_win": 0.90, "draw": 0.07, "away_win": 0.03}, confidence=0.15, data_source="seed")
    leg = compute_signal({"params": {"forecast": fc, "markets": [_ok("kalshi", "Brazil", 0.50)]}})["data"]["signal"]["legs"][0]
    assert "edge_likely_model_noise" in leg["risk_flags"] and leg["confidence_tier"] == "low"


# -- CLV tracker --------------------------------------------------------------

def _mkt(source, name, price, *, cache_id, event_urn="urn:ev:1"):
    m = _ok(source, name, price)
    m.update({"cache_id": cache_id, "event_urn": event_urn})
    return m


def _ledger_forecast():
    fc = _sig_forecast()
    fc["provider_ids"] = {"api_football": "100"}
    fc["schema:startDate"] = "2026-06-19T18:00:00+00:00"
    return fc


def _snap(cache_id, ts, name, price):
    return {"cache_id": cache_id, "ts": ts, "primary_name": name, "primary_price": price,
            "outcomes": [{"name": name, "price": price}]}


def _clv_row(bucket, won, tier="high"):
    clv = 3.0 if bucket == "CLV+" else (-3.0 if bucket == "CLV-" else 0.0)
    return {"clv_bucket": bucket, "won": won, "confidence_tier": tier, "clv_cents": clv}


class TestResultOutcome:
    def test_outcomes(self):
        assert _result_outcome(2, 0) == "home_win"
        assert _result_outcome(1, 1) == "draw"
        assert _result_outcome(0, 2) == "away_win"


class TestBuildSignalLedger:
    def test_value_legs_become_rows(self):
        markets = [_mkt("kalshi", "Brazil", 0.50, cache_id="c-bra"),
                   _mkt("kalshi", "Draw", 0.30, cache_id="c-tie"),
                   _mkt("kalshi", "Morocco", 0.22, cache_id="c-mar")]
        out = build_signal_ledger_rows({"params": {"forecasts": [_ledger_forecast()],
                                                    "markets": markets, "existing_ids": []}})["data"]
        rows = {r["_id"]: r for r in out["ledger_rows"]}
        assert "urn:ev:1:home_win" in rows  # model 0.60 vs 0.50 -> value
        row = rows["urn:ev:1:home_win"]
        assert row["entry_price"] == 0.50 and row["cache_id"] == "c-bra"
        assert row["outcome_name"] == "Brazil" and row["fixture_id"] == "100"
        assert row["kickoff"] == "2026-06-19T18:00:00+00:00" and row["status"] == "pending"
        assert row["metadata"] == {"event_urn": "urn:ev:1", "outcome": "home_win"}

    def test_insert_only_skips_existing(self):
        markets = [_mkt("kalshi", "Brazil", 0.50, cache_id="c-bra")]
        out = build_signal_ledger_rows({"params": {"forecasts": [_ledger_forecast()], "markets": markets,
                                                    "existing_ids": ["urn:ev:1:home_win"]}})["data"]
        assert out["ledger_rows"] == []  # already logged -> not re-emitted

    def test_no_markets_no_rows(self):
        out = build_signal_ledger_rows({"params": {"forecasts": [_ledger_forecast()], "markets": [],
                                                    "existing_ids": []}})["data"]
        assert out["ledger_rows"] == []


class TestComputeClv:
    def _row(self, **over):
        row = {"_id": "urn:ev:1:home_win", "event_urn": "urn:ev:1", "outcome": "home_win",
               "outcome_name": "Brazil", "cache_id": "c-bra", "entry_price": 0.28,
               "fixture_id": "100", "kickoff": "2026-06-19T18:00:00+00:00",
               "confidence_tier": "high", "status": "pending"}
        row.update(over)
        return row

    def _final(self, h, a):
        return [{"fixture": {"id": "100", "status": {"short": "FT"}}, "goals": {"home": h, "away": a}}]

    def test_clv_positive_and_won(self):
        snaps = [_snap("c-bra", "2026-06-19T17:00:00+00:00", "Brazil", 0.34),
                 _snap("c-bra", "2026-06-19T19:00:00+00:00", "Brazil", 0.40)]  # post-kickoff, ignored
        out = compute_clv({"params": {"ledger_rows": [self._row()], "snapshots": snaps,
                                      "finished_fixtures": self._final(2, 0)}})["data"]
        row = out["settled_rows"][0]
        assert row["closing_price"] == 0.34 and row["clv_cents"] == 6.0
        assert row["clv_bucket"] == "CLV+" and row["won"] == 1 and row["status"] == "settled"

    def test_clv_neutral_bucket(self):
        snaps = [_snap("c-bra", "2026-06-19T17:00:00+00:00", "Brazil", 0.498)]
        out = compute_clv({"params": {"ledger_rows": [self._row(entry_price=0.50)], "snapshots": snaps,
                                      "finished_fixtures": self._final(0, 1)}})["data"]
        row = out["settled_rows"][0]
        assert row["clv_cents"] == -0.2 and row["clv_bucket"] == "CLV="  # within +/-0.5c band
        assert row["won"] == 0  # home_win pick, away_win result

    def test_no_pre_kickoff_snapshot_stays_pending(self):
        snaps = [_snap("c-bra", "2026-06-19T19:00:00+00:00", "Brazil", 0.40)]  # only post-kickoff
        out = compute_clv({"params": {"ledger_rows": [self._row()], "snapshots": snaps,
                                      "finished_fixtures": self._final(2, 0)}})["data"]
        assert out["settled_rows"] == []
        assert out["ledger"][0].get("clv_bucket") is None and out["ledger"][0]["status"] == "pending"

    def test_fixture_not_final_stays_pending(self):
        snaps = [_snap("c-bra", "2026-06-19T17:00:00+00:00", "Brazil", 0.34)]
        out = compute_clv({"params": {"ledger_rows": [self._row()], "snapshots": snaps,
                                      "finished_fixtures": []}})["data"]
        assert out["settled_rows"] == [] and out["ledger"][0].get("clv_bucket") is None

    def test_already_settled_carried_forward(self):
        settled = self._row(clv_bucket="CLV+", clv_cents=6.0, won=1, closing_price=0.34, status="settled")
        out = compute_clv({"params": {"ledger_rows": [settled],
                                      "snapshots": [_snap("c-bra", "2026-06-19T17:00:00+00:00", "Brazil", 0.99)],
                                      "finished_fixtures": self._final(2, 0)}})["data"]
        assert out["settled_rows"] == []                 # not re-settled
        assert out["ledger"][0]["closing_price"] == 0.34  # first capture preserved


class TestComputeClvReport:
    def test_significant_gap_and_sufficiency(self):
        rows = ([_clv_row("CLV+", 1) for _ in range(27)] + [_clv_row("CLV+", 0) for _ in range(3)]
                + [_clv_row("CLV-", 1) for _ in range(3)] + [_clv_row("CLV-", 0) for _ in range(27)])
        rep = compute_clv_report({"params": {"clv_rows": rows}})["data"]["clv_report"]
        assert rep["sample_size"] == 60 and rep["sample_size_sufficient"] is True
        assert rep["win_rates"]["clv_positive"] == 90.0 and rep["win_rates"]["clv_negative"] == 10.0
        assert rep["win_rates"]["gap_pp"] == 80.0
        assert rep["z_test"]["z"] > 5 and rep["z_test"]["p_value"] < 0.001
        assert "high" in rep["by_confidence_tier"]

    def test_small_sample_insufficient(self):
        rows = [_clv_row("CLV+", 1) for _ in range(10)] + [_clv_row("CLV-", 0) for _ in range(10)]
        rep = compute_clv_report({"params": {"clv_rows": rows}})["data"]["clv_report"]
        assert rep["sample_size"] == 20 and rep["sample_size_sufficient"] is False
        assert "insufficient" in rep["recommendation"]

    def test_empty(self):
        rep = compute_clv_report({"params": {"clv_rows": []}})["data"]["clv_report"]
        assert rep["sample_size"] == 0 and rep["z_test"]["z"] is None
        assert rep["sample_size_sufficient"] is False

    def test_z_test_parity_small_sample(self):
        # CLV+ 8/10, CLV- 2/10: p1=.8 p2=.2 pooled=.5 se=sqrt(.05) -> z=0.6/0.223607=2.683
        rows = ([_clv_row("CLV+", 1) for _ in range(8)] + [_clv_row("CLV+", 0) for _ in range(2)]
                + [_clv_row("CLV-", 1) for _ in range(2)] + [_clv_row("CLV-", 0) for _ in range(8)])
        rep = compute_clv_report({"params": {"clv_rows": rows}})["data"]["clv_report"]
        assert rep["z_test"]["z"] == 2.683 and rep["win_rates"]["gap_pp"] == 60.0


class TestPairCrossSource:
    MEX = "urn:machina:sport:soccer:team:mexico:mex"
    ECU = "urn:machina:sport:soccer:team:ecuador:ecu"
    EV = "urn:machina:sport:soccer:event:mexico-vs-ecuador:20260701:wor"

    def _game_markets(self):
        rel = [MEX_ECU[0], MEX_ECU[1]]
        return [
            {"cache_id": "kalshi:MEX", "source": "kalshi", "title": "Mexico vs Ecuador Winner?",
             "event_urn": self.EV, "related_team_urns": rel, "price_quality": "ok",
             "outcomes": [{"name": "Reg Time: Mexico", "price": 0.43}, {"name": "No", "price": 0.56}]},
            {"cache_id": "kalshi:ECU", "source": "kalshi", "title": "Mexico vs Ecuador Winner?",
             "event_urn": self.EV, "related_team_urns": rel, "price_quality": "ok",
             "outcomes": [{"name": "Reg Time: Ecuador", "price": 0.23}, {"name": "No", "price": 0.76}]},
            {"cache_id": "kalshi:TIE", "source": "kalshi", "title": "Mexico vs Ecuador Winner?",
             "event_urn": self.EV, "related_team_urns": rel, "price_quality": "ok",
             "outcomes": [{"name": "Tie", "price": 0.33}, {"name": "No", "price": 0.66}]},
            {"cache_id": "polymarket:mex", "source": "polymarket", "title": "Will Mexico win on 2026-06-30?",
             "event_urn": self.EV, "related_team_urns": rel, "price_quality": "ok",
             "outcomes": [{"name": "Yes", "price": 0.435}, {"name": "No", "price": 0.565}]},
            {"cache_id": "polymarket:ecu", "source": "polymarket", "title": "Will Ecuador win on 2026-06-30?",
             "event_urn": self.EV, "related_team_urns": rel, "price_quality": "ok",
             "outcomes": [{"name": "Yes", "price": 0.225}, {"name": "No", "price": 0.775}]},
            {"cache_id": "polymarket:draw", "source": "polymarket", "title": "Will Mexico vs. Ecuador end in a draw?",
             "event_urn": self.EV, "related_team_urns": rel, "price_quality": "ok",
             "outcomes": [{"name": "Yes", "price": 0.335}, {"name": "No", "price": 0.665}]},
        ]

    def _rows_by_outcome(self, markets):
        r = pair_cross_source({"params": {"markets": markets}})["data"]
        return {row["outcome"]: row for row in r["pairs"]}, r

    def test_pairs_game_moneyline_three_outcomes(self):
        rows, r = self._rows_by_outcome(self._game_markets())
        assert set(rows) == {"mexico", "ecuador", "DRAW"}
        assert rows["mexico"]["kalshi_yes"] == 0.43 and rows["mexico"]["poly_yes"] == 0.435
        assert rows["ecuador"]["edge_bps"] == -62
        assert rows["mexico"]["edge_bps"] == 29
        assert rows["DRAW"]["edge_bps"] == 34
        # sorted by absolute edge, largest first
        assert abs(r["pairs"][0]["edge_bps"]) >= abs(r["pairs"][-1]["edge_bps"])

    def test_devig_fair_probs_sum_to_one_per_source(self):
        # De-vig normalizes each source's 3-way to sum to 1.0; displayed fair
        # values are rounded to 4dp, so allow sub-bps rounding drift.
        rows, _ = self._rows_by_outcome(self._game_markets())
        k = sum(rows[o]["kalshi_fair"] for o in rows)
        p = sum(rows[o]["poly_fair"] for o in rows)
        assert abs(k - 1.0) <= 0.001 and abs(p - 1.0) <= 0.001

    def test_cheaper_venue_marked(self):
        rows, _ = self._rows_by_outcome(self._game_markets())
        # Ecuador YES is cheaper on Polymarket (0.2261 fair) than Kalshi (0.2323)
        assert rows["ecuador"]["cheaper_venue"] == "polymarket"

    def test_single_source_yields_no_edge(self):
        kalshi_only = [m for m in self._game_markets() if m["source"] == "kalshi"]
        rows, _ = self._rows_by_outcome(kalshi_only)
        assert rows["mexico"]["poly_yes"] is None
        assert "edge_bps" not in rows["mexico"]

    def test_skips_unreliable_leg(self):
        markets = self._game_markets()
        markets[0]["price_quality"] = "unreliable"  # kalshi mexico
        rows, _ = self._rows_by_outcome(markets)
        # mexico bucket still present (poly side), but no kalshi price / edge
        assert rows["mexico"]["kalshi_yes"] is None
        assert "edge_bps" not in rows["mexico"]

    def test_advance_pairs_by_team_and_round(self):
        markets = [
            {"cache_id": "polymarket:adv-mex", "source": "polymarket", "market_type": "advance_r16",
             "title": "Will Mexico reach the Round of 16 at the 2026 FIFA World Cup?",
             "event_urn": None, "related_team_urns": [MEX_ECU[0]], "price_quality": "ok",
             "outcomes": [{"name": "Yes", "price": 0.63}, {"name": "No", "price": 0.37}]},
            {"cache_id": "kalshi:adv-mex", "source": "kalshi", "market_type": "advance_r16",
             "title": "Mexico to reach Round of 16?",
             "event_urn": None, "related_team_urns": [MEX_ECU[0]], "price_quality": "ok",
             "outcomes": [{"name": "Mexico", "price": 0.60}, {"name": "No", "price": 0.40}]},
        ]
        rows, _ = self._rows_by_outcome(markets)
        assert "mexico" in rows
        row = rows["mexico"]
        assert row["kind"] == "advance"
        # advance markets are independent binaries -> not de-vigged, fair == raw
        assert row["kalshi_yes"] == 0.60 and row["poly_yes"] == 0.63
        assert row["kalshi_fair"] == 0.60 and row["poly_fair"] == 0.63
        assert row["edge_bps"] == 300

    def test_outright_futures_unpairable_skipped(self):
        markets = [
            {"cache_id": "polymarket:win", "source": "polymarket", "title": "Will Mexico win the 2026 World Cup?",
             "event_urn": None, "related_team_urns": [MEX_ECU[0]], "price_quality": "ok",
             "outcomes": [{"name": "Yes", "price": 0.05}]},
        ]
        r = pair_cross_source({"params": {"markets": markets}})["data"]
        assert r["pairs"] == []


MEX_ECU = ("urn:machina:sport:soccer:team:mexico:mex",
           "urn:machina:sport:soccer:team:ecuador:ecu")
