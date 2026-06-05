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
normalize_identity_crosswalk = _module.normalize_identity_crosswalk
mint_event_identity = _module.mint_event_identity


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
        "provider_ids": {"api_football_fixture_id": fixture},
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
            "provider_ids": {"api_football_fixture_id": "1489417"},
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
        assert d["sport:competition"]["@id"] == "urn:machina:sport:soccer:competition:world-cup:wor"
        comps = {c["sport:qualifier"]: c["@id"] for c in d["sport:competitors"]}
        assert comps["home"] == "urn:machina:sport:soccer:team:uruguay:ury"
        assert comps["away"] == "urn:machina:sport:soccer:team:spain:esp"
        assert d["provider_ids"] == {
            "api_football_fixture_id": "1489417", "api_football_league_id": "1",
            "api_football_home_team_id": "7", "api_football_away_team_id": "9",
            "api_football_venue_id": "1076",
        }
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
        assert d["provider_ids"]["api_football_venue_id"] == ""

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
