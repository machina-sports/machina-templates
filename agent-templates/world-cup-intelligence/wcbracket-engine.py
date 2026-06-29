"""
World Cup bracket-simulation engine (additive / exploration).

Two commands:
  build_bracket    -- construct the knockout tree (R32 -> Final) from cached
                      knockout events, resolving completed matches.
  simulate_bracket -- Monte Carlo the tree forward using analytic Dixon-Coles
                      pairwise advance probabilities, anchored to per-match
                      Kalshi/Polymarket moneyline where available. Emits per-team
                      advancement probabilities, a champion leaderboard, and the
                      single most-likely ("perfect") bracket.

Pure stdlib (numpy optional). Standard pyscript envelope: {status, data, message}.
Informational only -- not betting advice.
"""

import json
import math
import random
import re
import unicodedata

DISCLAIMER = ("Informational tournament simulation built from public model + "
              "market data. Probabilities are estimates, not betting advice.")

ROUND_NAMES = ["R32", "R16", "QF", "SF", "F"]
# What a winner in round i has *reached* (the next round / title).
REACHED_BY_WINNING = {"R32": "R16", "R16": "QF", "QF": "SF", "SF": "F", "F": "champion"}

_DEFAULT_XG = {
    "base": 1.45,          # league-average goals per team
    "attack_pivot": 0.5,   # attack_score that maps to a 1.0 multiplier
    "def_factor": 0.5,     # opponent-defense suppression strength
    "xg_min": 0.25,
    "xg_max": 3.2,
    "home_adv": 0.0,       # neutral venues in the knockout stage
}

# Official FIFA World Cup 2026 knockout topology. R32 winners do NOT pair
# sequentially -- the bracket is a fixed cross-over (e.g. the Brazil/Japan winner
# meets the Ivory Coast/Norway winner in the R16, not the South Africa/Canada
# winner). We encode the bracket by IDENTITY (each R32 matchup as a frozenset of
# its two team slugs) in *in-order leaf* sequence, so that once R32 is reordered
# to this layout the plain binary feeder tree [2j, 2j+1] reproduces every
# official R16/QF/SF pairing. Source: FIFA / Wikipedia 2026 knockout bracket
# (match numbers 73-88 -> R16 89-96 -> QF 97-100 -> SF 101-102 -> Final 104).
WC2026_BRACKET_ORDER = [
    frozenset(("germany", "paraguay")),          # M75  -> R16 M89 (top half, SF101)
    frozenset(("france", "sweden")),             # M78  -> R16 M89
    frozenset(("south-africa", "canada")),       # M73  -> R16 M90
    frozenset(("netherlands", "morocco")),       # M76  -> R16 M90
    frozenset(("portugal", "croatia")),          # M84  -> R16 M93
    frozenset(("spain", "austria")),             # M83  -> R16 M93
    frozenset(("usa", "bosnia-herzegovina")),    # M82  -> R16 M94
    frozenset(("belgium", "senegal")),           # M81  -> R16 M94
    frozenset(("brazil", "japan")),              # M74  -> R16 M91 (bottom half, SF102)
    frozenset(("ivory-coast", "norway")),        # M77  -> R16 M91
    frozenset(("mexico", "ecuador")),            # M79  -> R16 M92
    frozenset(("england", "congo-dr")),          # M80  -> R16 M92
    frozenset(("argentina", "cape-verde-islands")),  # M87 -> R16 M95
    frozenset(("australia", "egypt")),           # M86  -> R16 M95
    frozenset(("switzerland", "algeria")),       # M85  -> R16 M96
    frozenset(("colombia", "ghana")),            # M88  -> R16 M96
]


def _apply_bracket_order(r32, order, warnings):
    """Reorder R32 matches into the official bracket (in-order leaf) sequence,
    matching by team-slug pair so it is robust to the input ordering. Falls back
    to the given order (kickoff) if the matchups don't match the map."""
    by_pair = {frozenset((m["home_slug"], m["away_slug"])): m for m in r32}
    if not all(pair in by_pair for pair in order):
        warnings.append(
            "R32 matchups don't match the WC2026 bracket map; keeping kickoff "
            "order with sequential pairing (bracket cross-overs NOT applied)")
        return r32
    reordered = [by_pair[pair] for pair in order]
    for i, m in enumerate(reordered):
        m["match_idx"] = i
    return reordered


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _params(request_data):
    if isinstance(request_data, str):
        try:
            request_data = json.loads(request_data)
        except Exception:
            request_data = {}
    if not isinstance(request_data, dict):
        return {}
    p = request_data.get("params", request_data)
    return p if isinstance(p, dict) else {}


def _num(v, default=0.0):
    try:
        if v is None:
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _slug(name):
    # Strip accents (Côte->Cote, Türkiye->Turkiye) so names slug consistently.
    s = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^a-z0-9]+", "-", s.strip().lower())
    return s.strip("-")


# Canonicalize common national-team name variants to the api-football slug used in
# the bracket, so LLM-enrichment names (e.g. "United States", "Côte d'Ivoire") match.
_TEAM_SLUG_ALIASES = {
    "united-states": "usa", "usmnt": "usa", "united-states-of-america": "usa",
    "cote-d-ivoire": "ivory-coast", "cote-divoire": "ivory-coast", "ivory-coast-civ": "ivory-coast",
    "korea-republic": "south-korea", "republic-of-korea": "south-korea",
    "ir-iran": "iran", "iran-islamic-republic": "iran",
    "czechia": "czech-republic", "turkey": "turkiye",
    "bosnia-and-herzegovina": "bosnia-herzegovina", "bosnia": "bosnia-herzegovina",
    "cape-verde": "cape-verde-islands",
    "dr-congo": "congo-dr", "democratic-republic-of-the-congo": "congo-dr",
    "congo-democratic-republic": "congo-dr", "dr-congo-cod": "congo-dr",
    "the-netherlands": "netherlands", "holland": "netherlands",
}


def _canon(name):
    s = _slug(name)
    return _TEAM_SLUG_ALIASES.get(s, s)


def _poisson_pmf(k, lam):
    return (lam ** k) * math.exp(-lam) / math.factorial(k)


def _dc_tau(h, a, lam_h, lam_a, rho):
    if rho == 0:
        return 1.0
    if h == 0 and a == 0:
        return 1.0 - lam_h * lam_a * rho
    if h == 0 and a == 1:
        return 1.0 + lam_h * rho
    if h == 1 and a == 0:
        return 1.0 + lam_a * rho
    if h == 1 and a == 1:
        return 1.0 - rho
    return 1.0


def _ranking_fields(rank):
    """Pull (power, attack, defense) from a compute_power_ranking entry."""
    if not isinstance(rank, dict):
        return 0.5, 0.5, 0.5
    power = _num(rank.get("power_score"), 0.5)
    bd = rank.get("breakdown") or {}
    attack = _num(bd.get("attack_score"), power)
    defense = _num(bd.get("defense_score"), power)
    return power, attack, defense


def _expected_goals(home_rank, away_rank, xg):
    hp, h_att, h_def = _ranking_fields(home_rank)
    ap, a_att, a_def = _ranking_fields(away_rank)
    base, pivot, deff = xg["base"], xg["attack_pivot"], xg["def_factor"]
    home_xg = base * (max(h_att, 0.15) / pivot) * (1 - a_def * deff) + xg["home_adv"]
    away_xg = base * (max(a_att, 0.15) / pivot) * (1 - h_def * deff)
    home_xg = max(xg["xg_min"], min(xg["xg_max"], home_xg))
    away_xg = max(xg["xg_min"], min(xg["xg_max"], away_xg))
    return home_xg, away_xg


def _sharpen_1x2(probs, gamma):
    """Power-sharpen a 1X2 dict toward the favourite and renormalize. gamma>1
    sharpens (favourites stronger), gamma==1 is a no-op. Calibrated to gamma~1.3
    on 74 group games: the raw Dixon-Coles model under-rates favourites (teams it
    gives 60-80% actually win ~85%), so a mild sharpen lowers Brier 0.1794->~0.176."""
    if not gamma or gamma == 1.0:
        return probs
    keys = ("home_win", "draw", "away_win")
    num = {k: max(_num(probs.get(k)), 1e-9) ** gamma for k in keys}
    s = sum(num.values()) or 1.0
    out = dict(probs)
    for k in keys:
        out[k] = num[k] / s
    return out


def _regulation_1x2(home_rank, away_rank, xg, rho=-0.12, max_goals=10, sharpen=1.0):
    """Analytic Dixon-Coles regulation 1X2 (optionally calibration-sharpened)."""
    lam_h, lam_a = _expected_goals(home_rank, away_rank, xg)
    hp = [_poisson_pmf(k, lam_h) for k in range(max_goals + 1)]
    ap = [_poisson_pmf(k, lam_a) for k in range(max_goals + 1)]
    hw = dw = aw = 0.0
    total = 0.0
    for h in range(max_goals + 1):
        for a in range(max_goals + 1):
            p = hp[h] * ap[a] * _dc_tau(h, a, lam_h, lam_a, rho)
            total += p
            if h > a:
                hw += p
            elif h == a:
                dw += p
            else:
                aw += p
    if total > 0:
        hw, dw, aw = hw / total, dw / total, aw / total
    reg = {"home_win": hw, "draw": dw, "away_win": aw}
    reg = _sharpen_1x2(reg, sharpen)
    reg["home_xg"] = round(lam_h, 3)
    reg["away_xg"] = round(lam_a, 3)
    return reg


def _advance_prob(home_rank, away_rank, xg, rho, tie_scale, sharpen=1.0):
    """P(home advances) in a knockout: regulation win + tied games resolved by a
    power-weighted coin (ET + penalties), clamped near 50/50."""
    reg = _regulation_1x2(home_rank, away_rank, xg, rho, sharpen=sharpen)
    hp = _num(home_rank.get("power_score") if isinstance(home_rank, dict) else None, 0.5)
    ap = _num(away_rank.get("power_score") if isinstance(away_rank, dict) else None, 0.5)
    edge = max(-0.15, min(0.15, (hp - ap) * tie_scale))
    tie_break_home = 0.5 + edge
    p_home = reg["home_win"] + reg["draw"] * tie_break_home
    p_home = max(0.02, min(0.98, p_home))
    return p_home, reg


def _blend_market(reg, market_1x2, market_weight):
    """Blend model regulation 1X2 with a market 1X2 (normalized)."""
    if not market_1x2:
        return reg, False
    mw = max(0.0, min(1.0, market_weight))
    keys = ("home_win", "draw", "away_win")
    msum = sum(_num(market_1x2.get(k)) for k in keys)
    if msum <= 0:
        return reg, False
    blended = {}
    for k in keys:
        m = _num(market_1x2.get(k)) / msum
        blended[k] = mw * m + (1 - mw) * reg[k]
    bsum = sum(blended.values()) or 1.0
    for k in keys:
        blended[k] /= bsum
    blended["home_xg"] = reg.get("home_xg")
    blended["away_xg"] = reg.get("away_xg")
    return blended, True


# --------------------------------------------------------------------------- #
# build_bracket
# --------------------------------------------------------------------------- #
def _team_pair(ev):
    home = away = None
    for t in ev.get("teams") or []:
        q = str(t.get("qualifier") or "").lower()
        if q == "home":
            home = t.get("name")
        elif q == "away":
            away = t.get("name")
    if home is None or away is None:  # fall back to listed order
        names = [t.get("name") for t in (ev.get("teams") or []) if t.get("name")]
        if len(names) == 2:
            home, away = names[0], names[1]
    return home, away


_FINAL_STATUS = {"FT", "AET", "PEN"}


def _winner_by_pair_from_fixtures(finished_fixtures):
    """Map frozenset({home_slug, away_slug}) -> winner_slug from api-football
    finished fixtures (uses final goals; penalty shootout breaks ties)."""
    out = {}
    for f in finished_fixtures or []:
        if not isinstance(f, dict):
            continue
        status = str(((f.get("fixture") or {}).get("status") or {}).get("short") or "").upper()
        if status not in _FINAL_STATUS:
            continue
        teams = f.get("teams") or {}
        hn = ((teams.get("home") or {}).get("name"))
        an = ((teams.get("away") or {}).get("name"))
        if not hn or not an:
            continue
        goals = f.get("goals") or {}
        hg, ag = goals.get("home"), goals.get("away")
        if hg is None or ag is None:
            continue
        hs, as_ = _slug(hn), _slug(an)
        win = None
        if hg > ag:
            win = hs
        elif ag > hg:
            win = as_
        else:  # tie in regulation/ET -> penalty shootout
            pen = (f.get("score") or {}).get("penalty") or {}
            ph, pa = pen.get("home"), pen.get("away")
            if ph is not None and pa is not None and ph != pa:
                win = hs if ph > pa else as_
        if win:
            out[frozenset((hs, as_))] = win
    return out


def _knockout_fixture_ids(fixtures):
    """api-football fixture ids whose round is a knockout (NOT a group stage).

    The schedule mixes the final group-stage games (often kicking off the same
    calendar day the knockouts begin) with the real Round-of-32 fixtures, so a
    date cutoff alone leaks group games into the bracket. api-football tags every
    fixture with league.round ("Group Stage - 3" vs "Round of 32"/"8th Finals"/
    "Quarter-finals"/...); anything that isn't a group round is a knockout."""
    out = set()
    for f in fixtures or []:
        if not isinstance(f, dict):
            continue
        _fid = (f.get("fixture") or {}).get("id")
        fid = str(_fid) if _fid is not None else ""
        rnd = str(((f.get("league") or {}).get("round")) or "").lower()
        if fid and rnd and "group" not in rnd:
            out.add(fid)
    return out


def build_bracket(request_data):
    try:
        p = _params(request_data)
        events = p.get("knockout_events") or []
        results = {}  # event_urn -> winner_slug (explicit override)
        for r in p.get("finished_results") or []:
            eu = r.get("event_urn")
            wn = r.get("winner_name")
            if eu and wn:
                results[eu] = _slug(wn)
        # Auto-resolve completed knockout matches from finished fixtures.
        pair_winner = _winner_by_pair_from_fixtures(p.get("finished_fixtures"))

        warnings = []
        # Filter to knockout cutoff here (NOT in the workflow): the engine eval
        # exposes `$` as a local, so a `$.get('from_date')` reference inside a
        # workflow list-comprehension's if-clause runs in a scope that can't see
        # it and silently yields zero events. Doing it in Python is robust.
        from_date = str(p.get("from_date") or "")
        evs = [e for e in events if isinstance(e, dict)]
        # Prefer the authoritative knockout-round filter (drops leaked group
        # games regardless of date); fall back to the date cutoff if the
        # fixtures/round data isn't available or doesn't resolve enough matches.
        ko_ids = _knockout_fixture_ids(p.get("fixtures"))
        if ko_ids:
            by_round = [e for e in evs if str(e.get("af_id") or "") in ko_ids]
            if len(by_round) >= 2:
                evs = by_round
            else:
                warnings.append(
                    f"knockout-round filter matched {len(by_round)} events; using date cutoff instead")
                if from_date:
                    evs = [e for e in evs if str(e.get("start_date") or "") >= from_date]
        elif from_date:
            evs = [e for e in evs if str(e.get("start_date") or "") >= from_date]
        # Order R32 matches by kickoff; allow explicit override.
        order = p.get("bracket_order")
        if order:
            by_urn = {e.get("event_urn"): e for e in evs}
            evs = [by_urn[u] for u in order if u in by_urn]
        else:
            evs = sorted(evs, key=lambda e: str(e.get("start_date") or ""))

        # Dedup: each team appears once in R32.
        seen_teams = set()
        r32 = []
        for ev in evs:
            home, away = _team_pair(ev)
            if not home or not away:
                warnings.append(f"event {ev.get('event_urn')} missing a team; skipped")
                continue
            hs, as_ = _slug(home), _slug(away)
            if hs in seen_teams or as_ in seen_teams:
                warnings.append(f"duplicate team in {ev.get('event_urn')} ({home}/{away}); skipped")
                continue
            seen_teams.update((hs, as_))
            eu = ev.get("event_urn")
            status = str(ev.get("status") or "ns").lower()
            # Prefer explicit result, then auto-resolved from finished fixtures.
            winner = results.get(eu) or pair_winner.get(frozenset((hs, as_)))
            if status in ("ft", "aet", "pen") and not winner:
                warnings.append(f"completed match {eu} has no result available; will be simulated")
                status = "ns"
            r32.append({
                "match_idx": len(r32), "event_urn": eu,
                "home_name": home, "away_name": away,
                "home_slug": hs, "away_slug": as_,
                "status": "ft" if winner else "ns",
                "winner_slug": winner,
                "kickoff": ev.get("start_date"),
            })

        # Apply the official FIFA 2026 cross-over topology (R32 winners do not
        # pair sequentially). Identity-based, so it only fires when the 16 R32
        # matchups are the real 2026 field; otherwise the sequential tree stands.
        if len(r32) == 16:
            r32 = _apply_bracket_order(r32, WC2026_BRACKET_ORDER, warnings)

        n = len(r32)
        if n < 2:
            return {"status": False, "data": {"bracket": {}},
                    "message": f"Not enough knockout matches to build a bracket ({n})."}
        # Pad to a power of two if needed (byes carry the home slot forward).
        pow2 = 1 << (n - 1).bit_length()
        if n != pow2:
            warnings.append(f"{n} R32 matches is not a power of two; padding to {pow2} with byes")

        rounds = [{"name": ROUND_NAMES[0] if pow2 >= 16 else "K1", "matches": r32}]
        # Build forward feeder tree.
        prev_count = pow2
        ri = 1
        cur = pow2 // 2
        while cur >= 1:
            matches = []
            for j in range(cur):
                matches.append({"match_idx": j, "feeders": [2 * j, 2 * j + 1]})
            name = ROUND_NAMES[ri] if ri < len(ROUND_NAMES) else f"R{cur}"
            rounds.append({"name": name, "matches": matches})
            ri += 1
            cur //= 2

        bracket = {
            "field_size": n, "padded_size": pow2,
            "field_slugs": sorted(seen_teams),
            "name_by_slug": {m["home_slug"]: m["home_name"] for m in r32}
            | {m["away_slug"]: m["away_name"] for m in r32},
            "rounds": rounds,
            "warnings": warnings,
            "disclaimer": DISCLAIMER,
        }
        return {"status": True, "data": {"bracket": bracket},
                "message": f"Bracket built: {n} R32 matches, {len(rounds)} rounds."}
    except Exception as e:
        return {"status": False, "data": {"bracket": {}}, "message": f"build_bracket error: {e}"}


# --------------------------------------------------------------------------- #
# simulate_bracket
# --------------------------------------------------------------------------- #
# Kalshi/FIFA/IOC 3-letter team codes (used in the KXWCGAME market id suffix)
# differ from the ISO-3166 alpha-3 codes our team URNs carry. Without this map a
# fixture like South Africa (urn ...:zaf) vs a Kalshi "-RSA" market never anchors.
_FIFA_TO_ISO3 = {
    "ger": "deu", "ned": "nld", "por": "prt", "sui": "che", "cro": "hrv",
    "rsa": "zaf", "alg": "dza", "den": "dnk", "uru": "ury", "par": "pry",
    "ksa": "sau", "iri": "irn", "uae": "are", "chi": "chl", "tah": "pyf",
    "bah": "bhr", "eng": "eng", "wal": "wal", "sco": "sco",
}


def _iso3_to_slug(related_team_urns):
    """team-URN list -> {iso3: name_slug}. URN: urn:...:team:{slug}:{iso3}."""
    out = {}
    for u in related_team_urns or []:
        parts = str(u).split(":")
        if len(parts) >= 2 and parts[-1] and parts[-2]:
            out[parts[-1].lower()] = parts[-2].lower()
    return out


def _affirmative_outcome(outcomes, home_slug, away_slug):
    """The 'this side happens' price + which side it names, if the outcome name
    carries it (old team-named shape). Returns (price|None, 'home'|'away'|'draw'|None)."""
    price = None
    named = None
    for o in outcomes or []:
        if o.get("price") is None:
            continue
        nm = _slug(o.get("name") or o.get("outcome_name"))
        p = _num(o.get("price"))
        if nm in ("no",):
            continue
        if nm in ("tie", "draw"):
            return p, "draw"
        if nm in ("yes",):
            price = p  # affirmative, side comes from the market id suffix
        elif home_slug and (home_slug in nm or nm in home_slug):
            return p, "home"
        elif away_slug and (away_slug in nm or nm in away_slug):
            return p, "away"
    return price, named


def _market_1x2_for(market_list, event_urn, home_slug, away_slug):
    """Map cached per-match moneyline markets to {home_win, draw, away_win}.

    Kalshi posts one binary per outcome of a fixture (KXWCGAME-<date><HOMEAWY>-<XXX>
    where XXX is a team iso3 or TIE). The outcome name is generic ("Yes"/"Tie"),
    so the side is taken from the id suffix resolved through related_team_urns;
    older markets that name the outcome after the team are still honored."""
    home = draw = away = None
    for m in market_list:
        if not isinstance(m, dict):
            continue
        iso3 = _iso3_to_slug(m.get("related_team_urns"))
        # Match by event_urn (primary) or the related team pair (event_urn-link lag).
        matches = bool(event_urn) and m.get("event_urn") == event_urn
        if not matches:
            pair = set(iso3.values())
            matches = home_slug in pair and away_slug in pair
        if not matches:
            continue
        price, side = _affirmative_outcome(m.get("outcomes"), home_slug, away_slug)
        if price is None:
            continue
        if side is None:  # resolve side from the market id suffix (team code / TIE)
            suffix = str(m.get("id") or "").rsplit("-", 1)[-1].lower()
            suffix = _FIFA_TO_ISO3.get(suffix, suffix)  # FIFA/IOC -> ISO-3166
            if suffix == "tie":
                side = "draw"
            elif iso3.get(suffix) == home_slug:
                side = "home"
            elif iso3.get(suffix) == away_slug:
                side = "away"
        if side == "home" and home is None:
            home = price
        elif side == "away" and away is None:
            away = price
        elif side == "draw" and draw is None:
            draw = price
    # Require BOTH win sides; draw inferred from the overround when absent.
    if home is None or away is None:
        return None
    out = {"home_win": home, "draw": draw if draw is not None else 0.0, "away_win": away}
    if draw is None:
        out["draw"] = max(0.0, 1.0 - home - away)
    return out


def simulate_bracket(request_data):
    try:
        p = _params(request_data)
        bracket = p.get("bracket") or {}
        rounds = bracket.get("rounds") or []
        if not rounds:
            return {"status": False, "data": {"simulation": {}}, "message": "No bracket supplied."}

        team_index = p.get("team_index") or {}
        markets = [m for m in (p.get("markets") or []) if isinstance(m, dict)]
        cfg = p.get("config") or {}
        n_sims = int(cfg.get("n_sims") or 20000)
        market_weight = _num(cfg.get("market_weight"), 0.65)
        rho = _num(cfg.get("rho"), -0.12)
        tie_scale = _num(cfg.get("tie_break_scale"), 0.6)
        prob_sharpen = _num(cfg.get("prob_sharpen"), 1.3)  # calibrated favourite-sharpen
        seed = int(cfg.get("seed") or 42)
        xg = dict(_DEFAULT_XG)
        xg.update(cfg.get("xg_params") or {})

        # Per-team strength multipliers from web-enrichment (injuries/news), bounded.
        adj_by_slug = {}
        for a in (p.get("team_adjustments") or []):
            if not isinstance(a, dict):
                continue
            s = _canon(a.get("team_name") or a.get("team_slug") or "")
            inj = max(0.80, min(1.15, _num(a.get("strength_multiplier"), 1.0)))    # injuries/news ±15%
            coach = max(0.95, min(1.10, _num(a.get("coach_multiplier"), 1.0)))     # coach traits ±~5-10%
            mult = max(0.78, min(1.18, inj * coach))
            if s and mult != 1.0:
                adj_by_slug[s] = {"mult": mult, "inj": round(inj, 3), "coach": round(coach, 3),
                                  "reason": a.get("reason") or "",
                                  "coach_reason": a.get("coach_reason") or "",
                                  "key_absences": a.get("key_absences") or []}

        # Rankings indexed by slugified team name (robust to URN scheme), with the
        # bounded enrichment multiplier applied to power/attack/defense.
        rank_by_slug = {}
        adjustments_applied = []
        for r in team_index.values():
            if not (isinstance(r, dict) and r.get("team_name")):
                continue
            s = _slug(r["team_name"])
            adj = adj_by_slug.get(_canon(r["team_name"]))
            if adj:
                r = dict(r)
                m = adj["mult"]
                r["power_score"] = max(0.02, min(0.99, _num(r.get("power_score"), 0.5) * m))
                bd = dict(r.get("breakdown") or {})
                for k in ("attack_score", "defense_score"):
                    if bd.get(k) is not None:
                        bd[k] = max(0.02, min(0.99, _num(bd.get(k)) * m))
                r["breakdown"] = bd
                adjustments_applied.append({"team": r["team_name"], "multiplier": round(m, 3),
                                            "injury_mult": adj.get("inj"), "coach_mult": adj.get("coach"),
                                            "reason": adj["reason"], "coach_reason": adj.get("coach_reason", ""),
                                            "key_absences": adj["key_absences"]})
            rank_by_slug[s] = r

        def rank(slug):
            return rank_by_slug.get(slug, {"power_score": 0.5})

        def pair_adv(a, b):
            """P(a advances vs b), memoized, model-only (neutral)."""
            key = (a, b)
            cached = _adv_memo.get(key)
            if cached is not None:
                return cached
            ph, _reg = _advance_prob(rank(a), rank(b), xg, rho, tie_scale, prob_sharpen)
            _adv_memo[key] = ph
            _adv_memo[(b, a)] = 1.0 - ph
            return ph

        _adv_memo = {}
        name_by_slug = bracket.get("name_by_slug") or {}

        # --- R32: model + market-blended per-match probabilities (reported) ---
        r32 = rounds[0]["matches"]
        r32_probs = []   # P(home advances) per match
        r32_report = []
        for m in r32:
            hs, as_ = m["home_slug"], m["away_slug"]
            if m.get("winner_slug"):
                p_home = 1.0 if m["winner_slug"] == hs else 0.0
                r32_probs.append(p_home)
                r32_report.append({
                    "event_urn": m.get("event_urn"),
                    "home": m["home_name"], "away": m["away_name"],
                    "status": "completed", "winner": name_by_slug.get(m["winner_slug"]),
                    "home_advance_prob": p_home, "source": "result"})
                continue
            reg = _regulation_1x2(rank(hs), rank(as_), xg, rho, sharpen=prob_sharpen)
            mkt = _market_1x2_for(markets, m.get("event_urn"), hs, as_)
            blended, used_mkt = _blend_market(reg, mkt, market_weight)
            php = _num(rank(hs).get("power_score"), 0.5)
            pap = _num(rank(as_).get("power_score"), 0.5)
            edge = max(-0.15, min(0.15, (php - pap) * tie_scale))
            p_home = blended["home_win"] + blended["draw"] * (0.5 + edge)
            p_home = max(0.02, min(0.98, p_home))
            r32_probs.append(p_home)
            r32_report.append({
                "event_urn": m.get("event_urn"),
                "home": m["home_name"], "away": m["away_name"], "status": "scheduled",
                "model_1x2": {k: round(reg[k], 4) for k in ("home_win", "draw", "away_win")},
                "market_1x2": ({k: round(_num(mkt.get(k)), 4) for k in ("home_win", "draw", "away_win")}
                               if used_mkt else None),
                "blended_home_advance_prob": round(p_home, 4),
                "source": "model+market" if used_mkt else "model"})

        # --- Monte Carlo ---
        rng = random.Random(seed)
        n_rounds = len(rounds)
        # Positional reach labels: winning round ri "reaches" the next round's
        # name, and the last round's winner reaches "champion". Robust to any
        # field size / round naming.
        round_names = [rnd["name"] for rnd in rounds]

        def reached_label(ri):
            return "champion" if ri == n_rounds - 1 else round_names[ri + 1]

        # reach[slug][label] and winner_counts[round_idx][match_idx][slug]
        reach = {}
        winner_counts = [[{} for _ in rnd["matches"]] for rnd in rounds]

        def bump_reach(slug, rname):
            d = reach.setdefault(slug, {})
            d[rname] = d.get(rname, 0) + 1

        first_round = round_names[0]
        for _ in range(n_sims):
            # Round 0
            prev = []
            for j, m in enumerate(r32):
                hs, as_ = m["home_slug"], m["away_slug"]
                bump_reach(hs, first_round)
                bump_reach(as_, first_round)
                w = hs if rng.random() < r32_probs[j] else as_
                prev.append(w)
                winner_counts[0][j][w] = winner_counts[0][j].get(w, 0) + 1
                bump_reach(w, reached_label(0))
            # Subsequent rounds
            for ri in range(1, n_rounds):
                cur = []
                for j, m in enumerate(rounds[ri]["matches"]):
                    f0, f1 = m["feeders"]
                    a = prev[f0] if f0 < len(prev) else None
                    b = prev[f1] if f1 < len(prev) else None
                    if a is None and b is None:
                        w = None
                    elif a is None:
                        w = b
                    elif b is None:
                        w = a
                    else:
                        w = a if rng.random() < pair_adv(a, b) else b
                    cur.append(w)
                    if w is not None:
                        winner_counts[ri][j][w] = winner_counts[ri][j].get(w, 0) + 1
                        bump_reach(w, reached_label(ri))
                prev = cur

        # --- Advancement matrix ---
        adv_rounds = round_names + ["champion"]
        final_round = round_names[-1]  # round whose winner is champion
        advancement = []
        for slug, counts in reach.items():
            row = {"team": name_by_slug.get(slug, slug)}
            for rn in adv_rounds:
                row[rn] = round(counts.get(rn, 0) / n_sims, 4)
            advancement.append(row)
        advancement.sort(
            key=lambda r: tuple(r.get(rn, 0) for rn in (["champion", final_round] + round_names[::-1])),
            reverse=True)

        champion_leaderboard = [
            {"team": r["team"], "champion_prob": r["champion"],
             "reach_final_prob": r.get(final_round, 0)}
            for r in advancement if r["champion"] > 0][:16]

        # --- Most-likely ("perfect") bracket: modal winner per match ---
        def modal(counts):
            if not counts:
                return None
            slug = max(counts, key=counts.get)
            return {"team": name_by_slug.get(slug, slug),
                    "win_share": round(counts[slug] / n_sims, 4)}

        perfect = []
        for ri, rnd in enumerate(rounds):
            picks = [modal(winner_counts[ri][j]) for j in range(len(rnd["matches"]))]
            perfect.append({"round": rnd["name"], "winners": picks})
        champion = perfect[-1]["winners"][0] if perfect and perfect[-1]["winners"] else None

        # --- Decision trace: the single most-likely path with each H2H prob. ---
        # R32 uses the reported model+market advance probs; deeper rounds pair the
        # modal winners of the two feeder slots and show pair_adv between them.
        def modal_slug(counts):
            return max(counts, key=counts.get) if counts else None

        reach_share = {}  # slug -> P(reach this round), for matchup-likelihood context
        for slug, counts in reach.items():
            reach_share[slug] = counts

        bracket_trace = []
        for ri, rnd in enumerate(rounds):
            matches = []
            for j, mt in enumerate(rnd["matches"]):
                if ri == 0:
                    a_slug, b_slug = mt["home_slug"], mt["away_slug"]
                    p_a = r32_probs[j]
                    decided = bool(mt.get("winner_slug"))
                else:
                    f0, f1 = mt["feeders"]
                    a_slug = modal_slug(winner_counts[ri - 1][f0]) if f0 < len(winner_counts[ri - 1]) else None
                    b_slug = modal_slug(winner_counts[ri - 1][f1]) if f1 < len(winner_counts[ri - 1]) else None
                    if not a_slug or not b_slug:
                        continue
                    p_a = pair_adv(a_slug, b_slug)
                    decided = False
                win_slug = a_slug if p_a >= 0.5 else b_slug
                entry = {
                    "match": j + 1,
                    "team_a": name_by_slug.get(a_slug, a_slug),
                    "team_b": name_by_slug.get(b_slug, b_slug),
                    "p_a_advance": round(p_a, 4),
                    "p_b_advance": round(1.0 - p_a, 4),
                    "pick": name_by_slug.get(win_slug, win_slug),
                    "pick_advance_prob": round(max(p_a, 1.0 - p_a), 4),
                    "status": "completed" if decided else "projected",
                }
                if ri > 0:  # how likely this exact matchup is to occur
                    entry["matchup_likelihood"] = round(
                        (reach_share.get(a_slug, {}).get(rnd["name"], 0) / n_sims)
                        * (reach_share.get(b_slug, {}).get(rnd["name"], 0) / n_sims), 4)
                matches.append(entry)
            bracket_trace.append({"round": rnd["name"], "matches": matches})

        simulation = {
            "n_sims": n_sims,
            "config": {"market_weight": market_weight, "rho": rho,
                       "tie_break_scale": tie_scale, "prob_sharpen": prob_sharpen,
                       "seed": seed, "xg_params": xg},
            "champion": champion,
            "champion_leaderboard": champion_leaderboard,
            "advancement": advancement,
            "perfect_bracket": perfect,
            "bracket_trace": bracket_trace,
            "team_ratings": sorted(
                [{
                    "team": r.get("team_name"),
                    "power_score": round(_num(r.get("power_score"), 0.5), 4),
                    "attack_score": round(_num((r.get("breakdown") or {}).get("attack_score"), 0), 4),
                    "defense_score": round(_num((r.get("breakdown") or {}).get("defense_score"), 0), 4),
                    "goals_per_game": round(_num((r.get("metrics") or {}).get("goals_per_game"), 0), 3),
                    "games": r.get("games"),
                    "data_source": r.get("data_source"),
                    "confidence": r.get("confidence"),
                } for r in team_index.values()
                    if isinstance(r, dict) and r.get("team_name")
                    and _slug(r["team_name"]) in set(bracket.get("field_slugs") or [])],
                key=lambda x: x["power_score"], reverse=True),
            "r32_matches": r32_report,
            "team_adjustments_applied": adjustments_applied,
            "bracket_warnings": bracket.get("warnings", []),
            "disclaimer": DISCLAIMER,
        }
        msg = (f"Simulated {n_sims} tournaments over {n_rounds} rounds. "
               f"Champion: {champion['team'] if champion else 'n/a'} "
               f"({champion['win_share'] if champion else 0:.1%}).")
        return {"status": True, "data": {"simulation": simulation}, "message": msg}
    except Exception as e:
        import traceback
        return {"status": False, "data": {"simulation": {}},
                "message": f"simulate_bracket error: {e} | {traceback.format_exc()[-400:]}"}


def main(request_data):
    return build_bracket(request_data)
