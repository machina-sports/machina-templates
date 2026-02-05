import gzip
import json
import re
import time
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timedelta


# No-op lock for pyscript sandbox (single-threaded, no threading module)
class _NoOpLock:
    def __enter__(self): return self
    def __exit__(self, *a): pass


# ============================================================
# Configuration & League Mappings
# ============================================================

LEAGUES = {
    "premier-league": {
        "fd_id": 2021, "code": "PL", "espn": "eng.1", "understat": "EPL",
        "fpl": True, "transfermarkt": "premier-league",
        "name": "Premier League", "country": "England",
    },
    "la-liga": {
        "fd_id": 2014, "code": "PD", "espn": "esp.1", "understat": "La_Liga",
        "fpl": None, "transfermarkt": "laliga",
        "name": "La Liga", "country": "Spain",
    },
    "bundesliga": {
        "fd_id": 2002, "code": "BL1", "espn": "ger.1", "understat": "Bundesliga",
        "fpl": None, "transfermarkt": "1-bundesliga",
        "name": "Bundesliga", "country": "Germany",
    },
    "serie-a": {
        "fd_id": 2019, "code": "SA", "espn": "ita.1", "understat": "Serie_A",
        "fpl": None, "transfermarkt": "serie-a",
        "name": "Serie A", "country": "Italy",
    },
    "ligue-1": {
        "fd_id": 2015, "code": "FL1", "espn": "fra.1", "understat": "Ligue_1",
        "fpl": None, "transfermarkt": "ligue-1",
        "name": "Ligue 1", "country": "France",
    },
    "championship": {
        "fd_id": 2016, "code": "ELC", "espn": "eng.2", "understat": None,
        "fpl": None, "transfermarkt": "championship",
        "name": "Championship", "country": "England",
    },
    "eredivisie": {
        "fd_id": 2003, "code": "DED", "espn": "ned.1", "understat": None,
        "fpl": None, "transfermarkt": "eredivisie",
        "name": "Eredivisie", "country": "Netherlands",
    },
    "primeira-liga": {
        "fd_id": 2017, "code": "PPL", "espn": "por.1", "understat": None,
        "fpl": None, "transfermarkt": "primeira-liga",
        "name": "Primeira Liga", "country": "Portugal",
    },
    "serie-a-brazil": {
        "fd_id": 2013, "code": "BSA", "espn": "bra.1", "understat": None,
        "fpl": None, "transfermarkt": "campeonato-brasileiro-serie-a",
        "name": "Serie A Brazil", "country": "Brazil",
    },
    "champions-league": {
        "fd_id": 2001, "code": "CL", "espn": "uefa.champions", "understat": None,
        "fpl": None, "transfermarkt": None,
        "name": "Champions League", "country": "Europe",
    },
    "european-championship": {
        "fd_id": 2018, "code": "EC", "espn": None, "understat": None,
        "fpl": None, "transfermarkt": None,
        "name": "European Championship", "country": "Europe",
    },
    "world-cup": {
        "fd_id": 2000, "code": "WC", "espn": "fifa.world", "understat": None,
        "fpl": None, "transfermarkt": None,
        "name": "FIFA World Cup", "country": "International",
    },
}

FD_ID_TO_SLUG = {v["fd_id"]: k for k, v in LEAGUES.items()}
ESPN_TO_SLUG = {v["espn"]: k for k, v in LEAGUES.items() if v.get("espn")}

STATUS_MAP = {
    "SCHEDULED": "not_started",
    "TIMED": "not_started",
    "IN_PLAY": "live",
    "PAUSED": "halftime",
    "FINISHED": "closed",
    "POSTPONED": "postponed",
    "SUSPENDED": "suspended",
    "CANCELLED": "cancelled",
    "AWARDED": "closed",
    "LIVE": "live",
}

ESPN_STATUS_MAP = {
    "STATUS_SCHEDULED": "not_started",
    "STATUS_IN_PROGRESS": "live",
    "STATUS_HALFTIME": "halftime",
    "STATUS_FINAL": "closed",
    "STATUS_FULL_TIME": "closed",
    "STATUS_POSTPONED": "postponed",
    "STATUS_CANCELED": "cancelled",
    "STATUS_SUSPENDED": "suspended",
    "STATUS_FIRST_HALF": "1st_half",
    "STATUS_SECOND_HALF": "2nd_half",
    "STATUS_END_PERIOD": "halftime",
}


# ============================================================
# Module-Level Cache (TTL-based)
# ============================================================

_cache = {}
_cache_lock = _NoOpLock()


def _cache_get(key):
    with _cache_lock:
        entry = _cache.get(key)
        if entry is None:
            return None
        value, expiry = entry
        if time.monotonic() > expiry:
            del _cache[key]
            return None
        return value


def _cache_set(key, value, ttl=300):
    with _cache_lock:
        if len(_cache) > 500:
            now = time.monotonic()
            expired = [k for k, (_, exp) in _cache.items() if now > exp]
            for k in expired:
                del _cache[k]
        _cache[key] = (value, time.monotonic() + ttl)


# ============================================================
# Rate Limiters (Token Bucket)
# ============================================================

class _RateLimiter:
    def __init__(self, max_tokens=9, refill_rate=9.0 / 60.0):
        self.max_tokens = max_tokens
        self.tokens = max_tokens
        self.refill_rate = refill_rate
        self.last_refill = time.monotonic()
        self.lock = _NoOpLock()

    def acquire(self):
        with self.lock:
            now = time.monotonic()
            elapsed = now - self.last_refill
            self.tokens = min(self.max_tokens, self.tokens + elapsed * self.refill_rate)
            self.last_refill = now
            if self.tokens >= 1:
                self.tokens -= 1
                return
        time.sleep(max(0, (1 - self.tokens) / self.refill_rate))
        self.acquire()


_fd_rate_limiter = _RateLimiter(max_tokens=9, refill_rate=9.0 / 60.0)
_espn_rate_limiter = _RateLimiter(max_tokens=2, refill_rate=2.0)
_understat_rate_limiter = _RateLimiter(max_tokens=1, refill_rate=0.5)
_fpl_rate_limiter = _RateLimiter(max_tokens=10, refill_rate=10.0 / 60.0)
_tm_rate_limiter = _RateLimiter(max_tokens=2, refill_rate=2.0 / 60.0)


# ============================================================
# HTTP Helpers
# ============================================================

_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


def _fd_request(endpoint, api_key, params=None):
    """football-data.org API (rate-limited, requires API key)."""
    _fd_rate_limiter.acquire()
    url = f"https://api.football-data.org/v4{endpoint}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url)
    req.add_header("X-Auth-Token", api_key)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        return {"error": True, "status_code": e.code, "message": body}
    except Exception as e:
        return {"error": True, "message": str(e)}


def _espn_request(league_slug, resource="scoreboard", params=None):
    """ESPN public API (no auth required). Rate-limited, cached."""
    cache_key = f"espn:{league_slug}:{resource}:{json.dumps(params or {}, sort_keys=True)}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    _espn_rate_limiter.acquire()
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{league_slug}/{resource}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url)
    req.add_header("User-Agent", _USER_AGENT)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        _cache_set(cache_key, data, ttl=120)
        return data
    except Exception:
        return {"error": True}


def _espn_web_request(league_slug, resource, params=None):
    """ESPN web API (standings, season lists). Different host from site API."""
    cache_key = f"espn_web:{league_slug}:{resource}:{json.dumps(params or {}, sort_keys=True)}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    _espn_rate_limiter.acquire()
    url = f"https://site.web.api.espn.com/apis/v2/sports/soccer/{league_slug}/{resource}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url)
    req.add_header("User-Agent", _USER_AGENT)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        _cache_set(cache_key, data, ttl=300)
        return data
    except Exception:
        return {"error": True}


def _espn_summary(league_slug, event_id):
    """ESPN match summary endpoint (rich data: stats, lineups, player stats)."""
    if not league_slug or not event_id:
        return None
    cache_key = f"espn_summary:{league_slug}:{event_id}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached if cached else None
    _espn_rate_limiter.acquire()
    url = (
        f"https://site.web.api.espn.com/apis/site/v2/sports/soccer"
        f"/{league_slug}/summary?event={event_id}"
    )
    req = urllib.request.Request(url)
    req.add_header("User-Agent", _USER_AGENT)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        _cache_set(cache_key, data, ttl=300)
        return data
    except Exception:
        _cache_set(cache_key, {}, ttl=60)
        return None


def _understat_html(url):
    """Fetch Understat HTML page (for embedded match_info parsing)."""
    cache_key = f"ustat_html:{url}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached if cached else None
    _understat_rate_limiter.acquire()
    req = urllib.request.Request(url)
    req.add_header("User-Agent", _USER_AGENT)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode()
        _cache_set(cache_key, html, ttl=600)
        return html
    except Exception:
        _cache_set(cache_key, "", ttl=60)
        return None


def _understat_api(path, ttl=300):
    """Fetch JSON from Understat AJAX API (requires X-Requested-With header)."""
    cache_key = f"ustat_api:{path}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached if cached else None
    _understat_rate_limiter.acquire()
    url = f"https://understat.com{path}"
    req = urllib.request.Request(url)
    req.add_header("User-Agent", _USER_AGENT)
    req.add_header("X-Requested-With", "XMLHttpRequest")
    req.add_header("Accept-Encoding", "gzip, deflate")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            if resp.headers.get("Content-Encoding") == "gzip":
                raw = gzip.decompress(raw)
            data = json.loads(raw.decode())
        _cache_set(cache_key, data, ttl=ttl)
        return data
    except Exception:
        _cache_set(cache_key, "", ttl=60)
        return None


def _fpl_request(endpoint, ttl=300):
    """FPL API (fantasy.premierleague.com). No auth, cached, rate-limited."""
    cache_key = f"fpl:{endpoint}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached if cached else None
    _fpl_rate_limiter.acquire()
    url = f"https://fantasy.premierleague.com/api{endpoint}"
    req = urllib.request.Request(url)
    req.add_header("User-Agent", _USER_AGENT)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        _cache_set(cache_key, data, ttl=ttl)
        return data
    except Exception:
        _cache_set(cache_key, "", ttl=60)
        return None


def _tm_request(endpoint, ttl=3600):
    """Transfermarkt ceapi (no auth, JSON). Cached, conservative rate limit."""
    cache_key = f"tm:{endpoint}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached if cached else None
    _tm_rate_limiter.acquire()
    url = f"https://www.transfermarkt.com{endpoint}"
    req = urllib.request.Request(url)
    req.add_header("User-Agent", _USER_AGENT)
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        _cache_set(cache_key, data, ttl=ttl)
        return data
    except Exception:
        _cache_set(cache_key, "", ttl=60)
        return None


def _get_api_key(params):
    return (
        params.get("api_key")
        or params.get("headers", {}).get("api_key", "")
        or params.get("x-api-key")
        or params.get("headers", {}).get("x-api-key", "")
    )


def _has_fd_key(params):
    """Check if football-data.org API key is available."""
    return bool(_get_api_key(params))


# ============================================================
# Season Detection (ESPN-based)
# ============================================================

def _detect_current_season(slug, espn_slug):
    """Detect current season year/dates for a league using ESPN scoreboard."""
    if not espn_slug:
        return None
    cache_key = f"season_detect:{espn_slug}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached if cached else None
    data = _espn_request(espn_slug, "scoreboard")
    if data.get("error"):
        return None
    leagues = data.get("leagues", [])
    if not leagues:
        return None
    league_info = leagues[0]
    season = league_info.get("season", {})
    if not season:
        return None
    result = {
        "year": season.get("year"),
        "start_date": season.get("startDate", ""),
        "end_date": season.get("endDate", ""),
        "display_name": season.get("displayName", ""),
        "calendar": league_info.get("calendar", []),
        "slug": slug,
    }
    _cache_set(cache_key, result, ttl=3600)
    return result


def _resolve_espn_event(event_id, params):
    """Resolve event ID to (espn_league_slug, espn_event_id) tuple.

    Tries multiple strategies to determine which ESPN league the event belongs to.
    """
    eid = _resolve_event_id(event_id)
    # 1. Explicit league hint
    league_slug = (
        params.get("league_slug")
        or params.get("command_attribute", {}).get("league_slug", "")
        or params.get("competition_id")
        or params.get("command_attribute", {}).get("competition_id", "")
    )
    if league_slug:
        league, slug = _resolve_competition(league_slug)
        if league and league.get("espn"):
            return league["espn"], eid
    # 2. Extract from season_id
    season_id = params.get("season_id") or params.get("command_attribute", {}).get("season_id", "")
    if season_id:
        league, slug, year = _resolve_season(season_id)
        if league and league.get("espn"):
            return league["espn"], eid
    # 3. From event_value context (workflow pipelines pass this)
    event_value = params.get("event_value", {})
    comp_id = event_value.get("sport:competition", {}).get("@id", "")
    if comp_id:
        comp_slug = comp_id.replace("urn:machina:competition:", "")
        league = LEAGUES.get(comp_slug)
        if league and league.get("espn"):
            return league["espn"], eid
    # 4. Try all leagues as last resort (check scoreboard for the event)
    for slug, league in LEAGUES.items():
        espn_slug = league.get("espn")
        if not espn_slug:
            continue
        summary = _espn_summary(espn_slug, eid)
        if summary and summary.get("header"):
            return espn_slug, eid
    return None, eid


# ============================================================
# Understat HTML Parsing
# ============================================================

def _decode_understat_json(raw):
    """Decode Understat's hex-escaped JSON (\\xNN sequences)."""
    try:
        decoded = re.sub(
            r'\\x([0-9a-fA-F]{2})',
            lambda m: chr(int(m.group(1), 16)),
            raw,
        )
        return json.loads(decoded)
    except (json.JSONDecodeError, ValueError):
        return None


def _extract_understat_var(html, var_name):
    """Extract a JSON.parse('...') variable from Understat HTML."""
    pattern = r"var\s+" + re.escape(var_name) + r"\s*=\s*JSON\.parse\('(.+?)'\)"
    match = re.search(pattern, html, re.DOTALL)
    if not match:
        return None
    return _decode_understat_json(match.group(1))


# ============================================================
# Team Name Matching (fuzzy cross-source)
# ============================================================

def _normalize_name(name):
    """Normalize team name for comparison."""
    n = name.lower().strip()
    n = n.replace("-", " ")
    n = n.replace(".", "")
    for token in [" fc", " cf", " sc", " ac", "fc ", "sc ", " afc", " ssc"]:
        n = n.replace(token, " ")
    for old, new in [
        ("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u"),
        ("ü", "u"), ("ñ", "n"), ("ö", "o"), ("ä", "a"), ("ß", "ss"),
    ]:
        n = n.replace(old, new)
    return " ".join(n.split())


_ABBREV = {
    "man": "manchester", "utd": "united", "spurs": "tottenham",
    "wolves": "wolverhampton", "nottm": "nottingham", "sheff": "sheffield",
    "inter": "internazionale", "barca": "barcelona", "psg": "paris",
    "gladbach": "monchengladbach", "atletico": "atletico",
}


def _expand_abbrev(words):
    """Expand common abbreviations in a word set."""
    expanded = set()
    for w in words:
        expanded.add(w)
        if w in _ABBREV:
            expanded.add(_ABBREV[w])
    return expanded


def _teams_match(name1, name2):
    """Check if two team names likely refer to the same team."""
    if not name1 or not name2:
        return False
    n1 = _normalize_name(name1)
    n2 = _normalize_name(name2)
    if n1 == n2:
        return True
    if n1 in n2 or n2 in n1:
        return True
    words1 = _expand_abbrev(set(w for w in n1.split() if len(w) > 2))
    words2 = _expand_abbrev(set(w for w in n2.split() if len(w) > 2))
    if words1 and words2:
        overlap = words1 & words2
        min_size = min(
            len(set(w for w in n1.split() if len(w) > 2)),
            len(set(w for w in n2.split() if len(w) > 2)),
        )
        if min_size > 0 and len(overlap) >= min_size:
            return True
    return False


# ============================================================
# Cross-Source Event Resolution
# ============================================================

def _get_match_info(fd_event_id, api_key):
    """Fetch and cache match metadata from football-data.org."""
    cache_key = f"fd_match:{fd_event_id}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached if cached else None
    data = _fd_request(f"/matches/{fd_event_id}", api_key)
    if data.get("error"):
        return None
    comp_id = data.get("competition", {}).get("id")
    slug = FD_ID_TO_SLUG.get(comp_id)
    league = LEAGUES.get(slug) if slug else None
    info = {
        "fd_id": fd_event_id,
        "slug": slug or "",
        "espn_league": league.get("espn") if league else None,
        "understat_league": league.get("understat") if league else None,
        "date": data.get("utcDate", "")[:10],
        "home_team": data.get("homeTeam", {}).get("name", ""),
        "away_team": data.get("awayTeam", {}).get("name", ""),
        "status": data.get("status", ""),
        "season_year": data.get("season", {}).get("startDate", "")[:4],
        "raw": data,
    }
    _cache_set(cache_key, info, ttl=300)
    return info


def _find_espn_event_id(match_info):
    """Find ESPN event ID by matching date + home team name."""
    espn_league = match_info.get("espn_league")
    if not espn_league:
        return None
    date_str = match_info.get("date", "")
    home_team = match_info.get("home_team", "")
    if not date_str or not home_team:
        return None
    cache_key = f"espn_eid:{espn_league}:{date_str}:{_normalize_name(home_team)}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached if cached else None
    espn_data = _espn_request(
        espn_league, "scoreboard", {"dates": date_str.replace("-", "")}
    )
    if espn_data.get("error"):
        return None
    for ev in espn_data.get("events", []):
        comp = ev.get("competitions", [{}])[0]
        for c in comp.get("competitors", []):
            if c.get("homeAway") == "home":
                espn_home = c.get("team", {}).get("displayName", "")
                if _teams_match(home_team, espn_home):
                    eid = ev.get("id", "")
                    _cache_set(cache_key, eid, ttl=3600)
                    return eid
    _cache_set(cache_key, "", ttl=600)
    return None


def _find_understat_match_id(match_info):
    """Find Understat match ID by matching date + home team name via AJAX API."""
    understat_league = match_info.get("understat_league")
    if not understat_league:
        return None
    date_str = match_info.get("date", "")
    home_team = match_info.get("home_team", "")
    season_year = match_info.get("season_year", "")
    if not date_str or not home_team or not season_year:
        return None
    cache_key = f"ustat_mid:{understat_league}:{date_str}:{_normalize_name(home_team)}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached if cached else None
    # Fetch season match index via Understat AJAX API
    season_key = f"ustat_dates:{understat_league}:{season_year}"
    matches = _cache_get(season_key)
    if matches is None:
        league_data = _understat_api(
            f"/getLeagueData/{understat_league}/{season_year}", ttl=3600
        )
        matches = league_data.get("dates", []) if league_data else []
        _cache_set(season_key, matches, ttl=3600)
    for m in matches:
        m_date = m.get("datetime", "")[:10]
        m_home = m.get("h", {}).get("title", "")
        if m_date == date_str and _teams_match(home_team, m_home):
            mid = str(m.get("id", ""))
            _cache_set(cache_key, mid, ttl=86400)
            return mid
    _cache_set(cache_key, "", ttl=3600)
    return None


def _get_understat_match(match_id):
    """Fetch Understat match data (shots, rosters, match_info) via AJAX API."""
    if not match_id:
        return None
    cache_key = f"ustat_match:{match_id}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached if cached else None
    # Fetch shots + rosters via AJAX API
    api_data = _understat_api(f"/getMatchData/{match_id}", ttl=300)
    shots = api_data.get("shots", {"h": [], "a": []}) if api_data else {"h": [], "a": []}
    rosters = api_data.get("rosters", {"h": {}, "a": {}}) if api_data else {"h": {}, "a": {}}
    # Fetch match_info from HTML page (still embedded as JSON.parse)
    match_info = None
    html = _understat_html(f"https://understat.com/match/{match_id}")
    if html:
        match_info = _extract_understat_var(html, "match_info")
    data = {
        "shots": shots,
        "rosters": rosters,
        "match_info": match_info or {},
    }
    is_finished = match_info.get("isResult", False) if match_info else False
    _cache_set(cache_key, data, ttl=86400 if is_finished else 300)
    return data


# ============================================================
# ID Resolvers
# ============================================================

def _resolve_competition(competition_id):
    if not competition_id:
        return None, None
    cid = str(competition_id)
    if cid.startswith("urn:machina:competition:"):
        slug = cid.replace("urn:machina:competition:", "")
        return LEAGUES.get(slug), slug
    if cid in LEAGUES:
        return LEAGUES[cid], cid
    for slug, league in LEAGUES.items():
        if str(league["fd_id"]) == cid or league["code"] == cid:
            return league, slug
    return None, cid


def _resolve_season(season_id):
    if not season_id:
        return None, None, None
    sid = str(season_id)
    if sid.startswith("urn:machina:season:"):
        sid = sid.replace("urn:machina:season:", "")
    parts = sid.rsplit("-", 1)
    if len(parts) == 2 and parts[1].isdigit():
        slug = parts[0]
        year = int(parts[1])
        league = LEAGUES.get(slug)
        if league:
            return league, slug, year
    for slug, league in LEAGUES.items():
        if sid.startswith(slug):
            remainder = sid[len(slug):].lstrip("-")
            if remainder.isdigit():
                return league, slug, int(remainder)
    return None, sid, None


def _resolve_team_id(team_id):
    if not team_id:
        return None
    tid = str(team_id)
    if tid.startswith("urn:machina:team:"):
        tid = tid.replace("urn:machina:team:", "")
    return tid


def _resolve_event_id(event_id):
    if not event_id:
        return None
    eid = str(event_id)
    if eid.startswith("urn:machina:event:"):
        eid = eid.replace("urn:machina:event:", "")
    if eid.startswith("urn:machina:sport_event:"):
        eid = eid.replace("urn:machina:sport_event:", "")
    return eid


def _resolve_player_id(player_id):
    if not player_id:
        return None
    pid = str(player_id)
    if pid.startswith("urn:machina:player:"):
        pid = pid.replace("urn:machina:player:", "")
    return pid


# ============================================================
# Data Normalizers (football-data.org → Machina format)
# ============================================================

def _slugify(name):
    return name.lower().replace(" ", "-").replace(".", "").replace("'", "")


def _normalize_competition(fd_comp):
    slug = _slugify(fd_comp.get("name", ""))
    for s, league in LEAGUES.items():
        if league["fd_id"] == fd_comp.get("id"):
            slug = s
            break
    return {
        "id": slug,
        "name": fd_comp.get("name", ""),
        "code": fd_comp.get("code", ""),
        "category": {
            "id": _slugify(fd_comp.get("area", {}).get("name", "")),
            "name": fd_comp.get("area", {}).get("name", ""),
        },
        "type": fd_comp.get("type", "LEAGUE"),
    }


def _normalize_season(fd_season, competition_slug=""):
    year = fd_season.get("startDate", "")[:4]
    return {
        "id": f"{competition_slug}-{year}" if competition_slug else str(fd_season.get("id", "")),
        "name": f"{year}/{str(int(year)+1)[-2:]}" if year else "",
        "year": year,
        "start_date": fd_season.get("startDate", ""),
        "end_date": fd_season.get("endDate", ""),
        "current_matchday": fd_season.get("currentMatchday"),
    }


def _normalize_team(fd_team):
    return {
        "id": str(fd_team.get("id", "")),
        "name": fd_team.get("name", fd_team.get("shortName", "")),
        "short_name": fd_team.get("shortName", fd_team.get("tla", "")),
        "abbreviation": fd_team.get("tla", ""),
        "crest": fd_team.get("crest", ""),
        "country": fd_team.get("area", {}).get("name", ""),
        "country_code": fd_team.get("area", {}).get("code", ""),
        "venue": fd_team.get("venue", ""),
        "founded": fd_team.get("founded"),
        "colors": fd_team.get("clubColors", ""),
        "website": fd_team.get("website", ""),
    }


def _normalize_match(fd_match, competition_slug=None):
    comp = fd_match.get("competition", {})
    if not competition_slug:
        competition_slug = FD_ID_TO_SLUG.get(comp.get("id"), _slugify(comp.get("name", "")))
    season = fd_match.get("season", {})
    season_year = season.get("startDate", "")[:4] if season.get("startDate") else ""
    home = fd_match.get("homeTeam", {})
    away = fd_match.get("awayTeam", {})
    score = fd_match.get("score", {})
    full_time = score.get("fullTime", {})
    half_time = score.get("halfTime", {})
    return {
        "id": str(fd_match.get("id", "")),
        "status": STATUS_MAP.get(fd_match.get("status", ""), fd_match.get("status", "not_started")),
        "start_time": fd_match.get("utcDate", ""),
        "matchday": fd_match.get("matchday"),
        "round": fd_match.get("matchday", ""),
        "round_name": (
            f"Matchday {fd_match.get('matchday', '')}"
            if fd_match.get("matchday")
            else fd_match.get("stage", "")
        ),
        "competition": {"id": competition_slug, "name": comp.get("name", "")},
        "season": {
            "id": f"{competition_slug}-{season_year}" if season_year else "",
            "name": f"{season_year}/{str(int(season_year)+1)[-2:]}" if season_year else "",
            "year": season_year,
        },
        "venue": {
            "id": str(fd_match.get("id", "")),
            "name": fd_match.get("venue", home.get("venue", "")),
            "city": "",
            "country": "",
        },
        "competitors": [
            {
                "team": {
                    "id": str(home.get("id", "")),
                    "name": home.get("name", home.get("shortName", "")),
                    "short_name": home.get("shortName", home.get("tla", "")),
                    "abbreviation": home.get("tla", ""),
                },
                "qualifier": "home",
                "score": full_time.get("home", 0) if full_time.get("home") is not None else 0,
            },
            {
                "team": {
                    "id": str(away.get("id", "")),
                    "name": away.get("name", away.get("shortName", "")),
                    "short_name": away.get("shortName", away.get("tla", "")),
                    "abbreviation": away.get("tla", ""),
                },
                "qualifier": "away",
                "score": full_time.get("away", 0) if full_time.get("away") is not None else 0,
            },
        ],
        "scores": {
            "home": full_time.get("home", 0) if full_time.get("home") is not None else 0,
            "away": full_time.get("away", 0) if full_time.get("away") is not None else 0,
            **({"half_time": {"home": half_time.get("home"), "away": half_time.get("away")}}
               if half_time.get("home") is not None else {}),
        },
        "referees": [
            {"id": str(r.get("id", "")), "name": r.get("name", ""), "type": r.get("type", "")}
            for r in fd_match.get("referees", [])
        ],
    }


def _normalize_standings_group(fd_standing, competition_slug=""):
    return {
        "name": fd_standing.get("group") or fd_standing.get("type", "TOTAL"),
        "type": fd_standing.get("type", "TOTAL"),
        "entries": [
            {
                "position": entry.get("position"),
                "team": {
                    "id": str(entry.get("team", {}).get("id", "")),
                    "name": entry.get("team", {}).get("name", ""),
                    "short_name": entry.get("team", {}).get("shortName", ""),
                    "abbreviation": entry.get("team", {}).get("tla", ""),
                    "crest": entry.get("team", {}).get("crest", ""),
                },
                "played": entry.get("playedGames", 0),
                "won": entry.get("won", 0),
                "drawn": entry.get("draw", 0),
                "lost": entry.get("lost", 0),
                "goals_for": entry.get("goalsFor", 0),
                "goals_against": entry.get("goalsAgainst", 0),
                "goal_difference": entry.get("goalDifference", 0),
                "points": entry.get("points", 0),
                "form": entry.get("form", ""),
            }
            for entry in fd_standing.get("table", [])
        ],
    }


def _normalize_player(fd_player, team_info=None):
    return {
        "id": str(fd_player.get("id", "")),
        "name": fd_player.get("name", ""),
        "first_name": fd_player.get("firstName", ""),
        "last_name": fd_player.get("lastName", ""),
        "date_of_birth": fd_player.get("dateOfBirth", ""),
        "nationality": fd_player.get("nationality", ""),
        "position": fd_player.get("position", ""),
        "shirt_number": fd_player.get("shirtNumber"),
        "team": {
            "id": str(team_info.get("id", "")) if team_info else "",
            "name": team_info.get("name", "") if team_info else "",
        } if team_info else fd_player.get("currentTeam", {}),
    }


def _normalize_scorer(fd_scorer, competition_slug=""):
    player = fd_scorer.get("player", {})
    team = fd_scorer.get("team", {})
    return {
        "player": {
            "id": str(player.get("id", "")),
            "name": player.get("name", ""),
            "first_name": player.get("firstName", ""),
            "last_name": player.get("lastName", ""),
            "nationality": player.get("nationality", ""),
            "position": player.get("position", ""),
            "date_of_birth": player.get("dateOfBirth", ""),
        },
        "team": {
            "id": str(team.get("id", "")),
            "name": team.get("name", ""),
            "short_name": team.get("shortName", ""),
            "abbreviation": team.get("tla", ""),
            "crest": team.get("crest", ""),
        },
        "goals": fd_scorer.get("goals", 0),
        "assists": fd_scorer.get("assists", 0),
        "penalties": fd_scorer.get("penalties", 0),
        "played_matches": fd_scorer.get("playedMatches", 0),
    }


# ============================================================
# ESPN Summary Normalizers
# ============================================================

def _espn_home_away_map(summary):
    """Build team_id → homeAway mapping from ESPN summary header."""
    header = summary.get("header", {})
    comps = header.get("competitions", [{}])
    competitors = comps[0].get("competitors", []) if comps else []
    return {c.get("id", ""): c.get("homeAway", "") for c in competitors}


def _map_espn_event_type(text):
    """Map ESPN event type text to normalized type."""
    t = text.lower()
    if "own goal" in t:
        return "own_goal"
    if "penalty" in t and "goal" in t:
        return "penalty_goal"
    if "penalty" in t and ("miss" in t or "saved" in t):
        return "penalty_missed"
    if "goal" in t:
        return "goal"
    if "yellow" in t and "red" in t:
        return "yellow_red_card"
    if "red" in t:
        return "red_card"
    if "yellow" in t:
        return "yellow_card"
    if "substitution" in t:
        return "substitution"
    return t or "unknown"


def _normalize_espn_summary_statistics(summary):
    """Extract team statistics from ESPN summary boxscore."""
    ha_map = _espn_home_away_map(summary)
    teams = []
    for team_data in summary.get("boxscore", {}).get("teams", []):
        team = team_data.get("team", {})
        team_id = team.get("id", "")
        stats_raw = team_data.get("statistics", [])
        sd = {s.get("name", ""): s.get("displayValue", "0") for s in stats_raw}
        teams.append({
            "team": {
                "id": team_id,
                "name": team.get("displayName", ""),
                "abbreviation": team.get("abbreviation", ""),
            },
            "qualifier": ha_map.get(team_id, ""),
            "statistics": {
                "ball_possession": sd.get("possessionPct", "0"),
                "shots_total": sd.get("shotsTotal", "0"),
                "shots_on_target": sd.get("shotsOnTarget", "0"),
                "shots_off_target": sd.get("shotsOffTarget", "0"),
                "shots_blocked": sd.get("shotsBlocked", "0"),
                "corner_kicks": sd.get("wonCorners", "0"),
                "free_kicks": "0",
                "fouls": sd.get("foulsCommitted", "0"),
                "offsides": sd.get("offsides", "0"),
                "yellow_cards": sd.get("yellowCards", "0"),
                "red_cards": sd.get("redCards", "0"),
                "passes_total": sd.get("totalPasses", "0"),
                "passes_accurate": sd.get("completedPasses", "0"),
                "tackles": sd.get("tackles", "0"),
                "crosses": "0",
                "goalkeeper_saves": sd.get("saves", "0"),
            },
        })
    return teams


def _normalize_espn_summary_timeline(summary):
    """Extract timeline events from ESPN summary."""
    timeline = []
    events = summary.get("keyEvents", [])
    if not events:
        header = summary.get("header", {})
        comps = header.get("competitions", [{}])
        events = comps[0].get("details", []) if comps else []
    for ev in events:
        type_obj = ev.get("type", {})
        type_text = type_obj.get("text", "") if isinstance(type_obj, dict) else str(type_obj)
        mapped_type = _map_espn_event_type(type_text)
        clock = ev.get("clock", {})
        minute_raw = clock.get("displayValue", "0'").replace("'", "").replace("+", " ")
        try:
            minute = int(minute_raw.split()[0]) if minute_raw.strip() else 0
        except ValueError:
            minute = 0
        team_data = ev.get("team", {})
        athletes = ev.get("athletesInvolved", [])
        entry = {
            "id": str(ev.get("id", ev.get("sequenceNumber", ""))),
            "type": mapped_type,
            "minute": minute,
            "period": "",
            "datetime": "",
            "team": {
                "id": team_data.get("id", ""),
                "name": team_data.get("displayName", team_data.get("name", "")),
            } if team_data else None,
            "player": {
                "id": athletes[0].get("id", "") if athletes else "",
                "name": athletes[0].get("displayName", "") if athletes else "",
            } if athletes else None,
        }
        if mapped_type == "substitution" and len(athletes) > 1:
            entry["player_in"] = {
                "id": athletes[0].get("id", ""),
                "name": athletes[0].get("displayName", ""),
            }
            entry["player_out"] = {
                "id": athletes[1].get("id", ""),
                "name": athletes[1].get("displayName", ""),
            }
        timeline.append(entry)
    timeline.sort(key=lambda e: e["minute"])
    return timeline


def _normalize_espn_summary_lineups(summary):
    """Extract lineup/formation data from ESPN summary."""
    ha_map = _espn_home_away_map(summary)
    formations = {}
    for f in summary.get("boxscore", {}).get("form", []):
        tid = f.get("team", {}).get("id", "")
        formations[tid] = f.get("formationSummary", "")
    lineups = []
    for roster in summary.get("rosters", []):
        team = roster.get("team", {})
        team_id = team.get("id", "")
        starting, bench = [], []
        for p in roster.get("roster", []):
            athlete = p.get("athlete", {})
            pos = p.get("position", {})
            jersey = p.get("jersey", "")
            info = {
                "id": athlete.get("id", ""),
                "name": athlete.get("displayName", ""),
                "position": pos.get("name", ""),
                "shirt_number": int(jersey) if jersey and jersey.isdigit() else None,
            }
            (starting if p.get("starter") else bench).append(info)
        if starting or bench:
            lineups.append({
                "team": {
                    "id": team_id,
                    "name": team.get("displayName", ""),
                    "abbreviation": team.get("abbreviation", ""),
                },
                "qualifier": ha_map.get(team_id, ""),
                "formation": formations.get(team_id, ""),
                "starting": starting,
                "bench": bench,
            })
    return lineups


def _normalize_espn_summary_players(summary):
    """Extract player-level statistics from ESPN summary rosters."""
    ha_map = _espn_home_away_map(summary)
    teams = []
    for roster in summary.get("rosters", []):
        team = roster.get("team", {})
        team_id = team.get("id", "")
        players = []
        for p in roster.get("roster", []):
            athlete = p.get("athlete", {})
            pos = p.get("position", {})
            stats = p.get("stats", [])
            jersey = p.get("jersey", "")
            stat_dict = {}
            for s in stats:
                stat_dict[s.get("name", "")] = s.get("value", s.get("displayValue", "0"))
            players.append({
                "id": athlete.get("id", ""),
                "name": athlete.get("displayName", ""),
                "short_name": athlete.get("shortName", ""),
                "position": pos.get("name", ""),
                "position_abbreviation": pos.get("abbreviation", ""),
                "shirt_number": jersey,
                "starter": p.get("starter", False),
                "subbed_in": p.get("subbedIn", False),
                "subbed_out": p.get("subbedOut", False),
                "sub_minute": p.get("subMinute"),
                "statistics": stat_dict,
            })
        if players:
            teams.append({
                "team": {
                    "id": team_id,
                    "name": team.get("displayName", ""),
                    "abbreviation": team.get("abbreviation", ""),
                },
                "qualifier": ha_map.get(team_id, ""),
                "players": players,
            })
    return teams


# ============================================================
# Understat Normalizers
# ============================================================

def _normalize_understat_xg(shots_data, match_info_data):
    """Normalize Understat shot-level xG data."""
    home_shots = shots_data.get("h", [])
    away_shots = shots_data.get("a", [])
    home_xg = sum(float(s.get("xG", 0)) for s in home_shots)
    away_xg = sum(float(s.get("xG", 0)) for s in away_shots)
    # Fallback to match_info xG totals when no shot-level data
    if not home_shots and not away_shots and match_info_data:
        home_xg = float(match_info_data.get("h_xg", 0))
        away_xg = float(match_info_data.get("a_xg", 0))
    teams = []
    if match_info_data:
        # match_info uses flat keys: team_h/team_a for names, h/a for team IDs
        for side, qualifier in [("h", "home"), ("a", "away")]:
            teams.append({
                "team": {
                    "id": str(match_info_data.get(side, "")),
                    "name": match_info_data.get(f"team_{side}", ""),
                },
                "qualifier": qualifier,
                "xg": round(home_xg if side == "h" else away_xg, 3),
            })
    shots = []
    for shot in sorted(home_shots + away_shots, key=lambda s: int(s.get("minute", 0))):
        shots.append({
            "id": shot.get("id", ""),
            "minute": int(shot.get("minute", 0)),
            "result": shot.get("result", ""),
            "xg": round(float(shot.get("xG", 0)), 4),
            "player": {"id": shot.get("player_id", ""), "name": shot.get("player", "")},
            "assist": shot.get("player_assisted", ""),
            "situation": shot.get("situation", ""),
            "shot_type": shot.get("shotType", ""),
            "last_action": shot.get("lastAction", ""),
            "coordinates": {
                "x": float(shot.get("X", 0)),
                "y": float(shot.get("Y", 0)),
            },
            "qualifier": "home" if shot.get("h_a") == "h" else "away",
        })
    return {"teams": teams, "shots": shots}


def _normalize_understat_players(rosters_data, match_info_data):
    """Normalize Understat player-level xG data."""
    teams = []
    for side, qualifier in [("h", "home"), ("a", "away")]:
        # match_info uses flat keys: h/a for team IDs, team_h/team_a for names
        team_id = str(match_info_data.get(side, "")) if match_info_data else ""
        team_name = match_info_data.get(f"team_{side}", "") if match_info_data else ""
        roster = rosters_data.get(side, {})
        players = []
        for pid, p in roster.items():
            players.append({
                "id": p.get("player_id", pid),
                "name": p.get("player", ""),
                "position_order": int(p.get("positionOrder", 99)),
                "minutes": int(p.get("time", 0)),
                "goals": int(p.get("goals", 0)),
                "own_goals": int(p.get("own_goals", 0)),
                "assists": int(p.get("assists", 0)),
                "shots": int(p.get("shots", 0)),
                "key_passes": int(p.get("key_passes", 0)),
                "xg": round(float(p.get("xG", 0)), 3),
                "xa": round(float(p.get("xA", 0)), 3),
                "xg_chain": round(float(p.get("xGChain", 0)), 3),
                "xg_buildup": round(float(p.get("xGBuildup", 0)), 3),
                "yellow_card": int(p.get("yellow_card", 0)),
                "red_card": int(p.get("red_card", 0)),
            })
        players.sort(key=lambda x: x["position_order"])
        if players:
            teams.append({
                "team": {
                    "id": team_id,
                    "name": team_name,
                },
                "qualifier": qualifier,
                "players": players,
            })
    return teams


# ============================================================
# ESPN Event & Standings Normalizers
# ============================================================

def _parse_espn_score(score):
    """Parse ESPN score (can be string, int, or $ref dict)."""
    if isinstance(score, dict):
        return int(float(score.get("value", score.get("displayValue", 0))))
    try:
        return int(score) if score is not None else 0
    except (ValueError, TypeError):
        return 0


def _normalize_espn_event(espn_event, league_slug=""):
    """Normalize ESPN scoreboard event to Machina format (same shape as _normalize_match)."""
    comp = espn_event.get("competitions", [{}])[0]
    competitors = comp.get("competitors", [])
    home = next((c for c in competitors if c.get("homeAway") == "home"), {})
    away = next((c for c in competitors if c.get("homeAway") == "away"), {})
    status_type = comp.get("status", {}).get("type", {}).get("name", "")
    season = espn_event.get("season", {})
    season_year = str(season.get("year", ""))
    hs = _parse_espn_score(home.get("score"))
    as_ = _parse_espn_score(away.get("score"))
    venue = comp.get("venue", {})
    return {
        "id": str(espn_event.get("id", "")),
        "status": ESPN_STATUS_MAP.get(status_type, "not_started"),
        "start_time": comp.get("date", espn_event.get("date", "")),
        "matchday": None,
        "round": "",
        "round_name": espn_event.get("week", {}).get("text", ""),
        "competition": {
            "id": league_slug,
            "name": LEAGUES.get(league_slug, {}).get("name", ""),
        },
        "season": {
            "id": f"{league_slug}-{season_year}" if season_year else "",
            "name": season_year,
            "year": season_year,
        },
        "venue": {
            "id": str(venue.get("id", "")),
            "name": venue.get("fullName", ""),
            "city": venue.get("address", {}).get("city", ""),
            "country": venue.get("address", {}).get("country", ""),
        },
        "competitors": [
            {
                "team": {
                    "id": str(home.get("team", {}).get("id", "")),
                    "name": home.get("team", {}).get("displayName", ""),
                    "short_name": home.get("team", {}).get("shortDisplayName", ""),
                    "abbreviation": home.get("team", {}).get("abbreviation", ""),
                },
                "qualifier": "home",
                "score": hs,
            },
            {
                "team": {
                    "id": str(away.get("team", {}).get("id", "")),
                    "name": away.get("team", {}).get("displayName", ""),
                    "short_name": away.get("team", {}).get("shortDisplayName", ""),
                    "abbreviation": away.get("team", {}).get("abbreviation", ""),
                },
                "qualifier": "away",
                "score": as_,
            },
        ],
        "scores": {
            "home": hs,
            "away": as_,
        },
        "referees": [],
    }


def _normalize_espn_standings(espn_data, league_slug=""):
    """Normalize ESPN standings response to Machina format."""
    groups = []
    for child in espn_data.get("children", []):
        standings = child.get("standings", {})
        entries = []
        for entry in standings.get("entries", []):
            team = entry.get("team", {})
            sd = {s.get("name", ""): s.get("value", 0) for s in entry.get("stats", [])}
            entries.append({
                "position": int(sd.get("rank", 0)),
                "team": {
                    "id": str(team.get("id", "")),
                    "name": team.get("displayName", ""),
                    "short_name": team.get("shortDisplayName", ""),
                    "abbreviation": team.get("abbreviation", ""),
                    "crest": team.get("logos", [{}])[0].get("href", "") if team.get("logos") else "",
                },
                "played": int(sd.get("gamesPlayed", 0)),
                "won": int(sd.get("wins", 0)),
                "drawn": int(sd.get("ties", 0)),
                "lost": int(sd.get("losses", 0)),
                "goals_for": int(sd.get("pointsFor", 0)),
                "goals_against": int(sd.get("pointsAgainst", 0)),
                "goal_difference": int(sd.get("pointDifferential", 0)),
                "points": int(sd.get("points", 0)),
                "form": "",
            })
        groups.append({
            "name": child.get("name", "TOTAL"),
            "type": "TOTAL",
            "entries": entries,
        })
    return groups


def _normalize_espn_team(espn_team):
    """Normalize ESPN team object to Machina format."""
    return {
        "id": str(espn_team.get("id", "")),
        "name": espn_team.get("displayName", ""),
        "short_name": espn_team.get("shortDisplayName", ""),
        "abbreviation": espn_team.get("abbreviation", ""),
        "crest": espn_team.get("logos", [{}])[0].get("href", "") if espn_team.get("logos") else "",
        "country": "",
        "country_code": "",
        "venue": "",
        "founded": None,
        "colors": "",
        "website": "",
    }



# ============================================================
# Match Context (ESPN-based, for cross-source resolution)
# ============================================================

def _get_match_context(espn_league, espn_event_id, summary=None):
    """Build match context from ESPN for cross-source resolution (no fd needed)."""
    if not summary:
        summary = _espn_summary(espn_league, espn_event_id)
    if not summary:
        return None
    header = summary.get("header", {})
    comps = header.get("competitions", [{}])
    comp = comps[0] if comps else {}
    competitors = comp.get("competitors", [])
    home = next((c for c in competitors if c.get("homeAway") == "home"), {})
    away = next((c for c in competitors if c.get("homeAway") == "away"), {})
    slug = ESPN_TO_SLUG.get(espn_league, "")
    league_info = LEAGUES.get(slug, {})
    return {
        "slug": slug,
        "espn_league": espn_league,
        "understat_league": league_info.get("understat"),
        "date": comp.get("date", "")[:10],
        "home_team": home.get("team", {}).get("displayName", ""),
        "away_team": away.get("team", {}).get("displayName", ""),
        "season_year": str(header.get("season", {}).get("year", "")),
    }


# ============================================================
# FPL Helpers (Fantasy Premier League API)
# ============================================================

_FPL_POSITION_MAP = {1: "Goalkeeper", 2: "Defender", 3: "Midfielder", 4: "Forward"}
_FPL_STATUS_MAP = {
    "a": "available", "d": "doubtful", "i": "injured",
    "s": "suspended", "u": "unavailable", "n": "not_in_squad",
}


def _map_fpl_position(element_type):
    return _FPL_POSITION_MAP.get(element_type, "Unknown")


def _map_fpl_injury_status(fpl_status):
    return _FPL_STATUS_MAP.get(fpl_status, fpl_status)


def _get_fpl_bootstrap():
    """Fetch FPL bootstrap-static (all players/teams/gameweeks). Cached 15min."""
    return _fpl_request("/bootstrap-static/", ttl=900)


def _build_fpl_team_map(bootstrap):
    """Build {team_id: team_data} from FPL bootstrap teams array."""
    if not bootstrap:
        return {}
    return {t["id"]: t for t in bootstrap.get("teams", [])}


def _normalize_fpl_player_enrichment(fpl_player):
    """Extract enrichment fields from FPL player data."""
    return {
        "fpl_id": fpl_player.get("id"),
        "code": fpl_player.get("code"),
        "web_name": fpl_player.get("web_name", ""),
        "status": _map_fpl_injury_status(fpl_player.get("status", "a")),
        "news": fpl_player.get("news", ""),
        "chance_of_playing_this_round": fpl_player.get("chance_of_playing_this_round"),
        "chance_of_playing_next_round": fpl_player.get("chance_of_playing_next_round"),
        "form": fpl_player.get("form", "0.0"),
        "now_cost": fpl_player.get("now_cost"),
        "selected_by_percent": fpl_player.get("selected_by_percent", "0.0"),
        "total_points": fpl_player.get("total_points", 0),
        "points_per_game": fpl_player.get("points_per_game", "0.0"),
        "expected_goals": fpl_player.get("expected_goals", "0.00"),
        "expected_assists": fpl_player.get("expected_assists", "0.00"),
        "expected_goal_involvements": fpl_player.get("expected_goal_involvements", "0.00"),
        "expected_goals_conceded": fpl_player.get("expected_goals_conceded", "0.00"),
        "ict_index": fpl_player.get("ict_index", "0.0"),
        "influence": fpl_player.get("influence", "0.0"),
        "creativity": fpl_player.get("creativity", "0.0"),
        "threat": fpl_player.get("threat", "0.0"),
        "minutes": fpl_player.get("minutes", 0),
        "goals_scored": fpl_player.get("goals_scored", 0),
        "assists": fpl_player.get("assists", 0),
        "clean_sheets": fpl_player.get("clean_sheets", 0),
        "penalties_order": fpl_player.get("penalties_order"),
        "corners_and_indirect_freekicks_order": fpl_player.get("corners_and_indirect_freekicks_order"),
        "direct_freekicks_order": fpl_player.get("direct_freekicks_order"),
    }


def _normalize_fpl_player_as_profile(fpl_player, team_map=None):
    """Convert FPL player to same shape as _normalize_player() output."""
    if team_map is None:
        bootstrap = _get_fpl_bootstrap()
        team_map = _build_fpl_team_map(bootstrap) if bootstrap else {}
    team = team_map.get(fpl_player.get("team"), {})
    return {
        "id": str(fpl_player.get("code", fpl_player.get("id", ""))),
        "name": f"{fpl_player.get('first_name', '')} {fpl_player.get('second_name', '')}".strip(),
        "first_name": fpl_player.get("first_name", ""),
        "last_name": fpl_player.get("second_name", ""),
        "date_of_birth": "",
        "nationality": "",
        "position": _map_fpl_position(fpl_player.get("element_type")),
        "shirt_number": fpl_player.get("squad_number"),
        "team": {
            "id": str(team.get("code", team.get("id", ""))),
            "name": team.get("name", ""),
        },
    }


def _enrich_team_players_fpl(players):
    """Enrich player list with FPL data (in-place). Matches by name."""
    bootstrap = _get_fpl_bootstrap()
    if not bootstrap:
        return
    fpl_by_name = {}
    for p in bootstrap.get("elements", []):
        full_name = f"{p.get('first_name', '')} {p.get('second_name', '')}".strip()
        web_name = p.get("web_name", "")
        if full_name:
            fpl_by_name[full_name.lower()] = p
        if web_name:
            fpl_by_name[web_name.lower()] = p
    for player in players:
        pname = player.get("name", "").lower()
        fpl_p = fpl_by_name.get(pname)
        if not fpl_p:
            for fname, fp in fpl_by_name.items():
                if _teams_match(pname, fname):
                    fpl_p = fp
                    break
        if fpl_p:
            player["fpl_data"] = _normalize_fpl_player_enrichment(fpl_p)


def _build_missing_players_from_fpl(bootstrap, season_id):
    """Build missing players list from FPL bootstrap data grouped by team."""
    team_map = _build_fpl_team_map(bootstrap)
    missing_by_team = {}
    for player in bootstrap.get("elements", []):
        status = player.get("status", "a")
        if status in ("d", "i", "s", "u", "n"):
            team_id = player.get("team")
            team_info = team_map.get(team_id, {})
            team_name = team_info.get("name", "Unknown")
            if team_name not in missing_by_team:
                missing_by_team[team_name] = {
                    "team": {
                        "id": str(team_info.get("code", team_id)),
                        "name": team_name,
                        "short_name": team_info.get("short_name", ""),
                    },
                    "players": [],
                }
            missing_by_team[team_name]["players"].append({
                "id": str(player.get("code", player.get("id", ""))),
                "name": f"{player.get('first_name', '')} {player.get('second_name', '')}".strip(),
                "web_name": player.get("web_name", ""),
                "position": _map_fpl_position(player.get("element_type")),
                "status": _map_fpl_injury_status(status),
                "news": player.get("news", ""),
                "chance_of_playing_this_round": player.get("chance_of_playing_this_round"),
                "chance_of_playing_next_round": player.get("chance_of_playing_next_round"),
                "news_added": player.get("news_added", ""),
            })
    teams = sorted(missing_by_team.values(), key=lambda t: t["team"]["name"])
    return {"season_id": season_id, "teams": teams}


def _build_leaders_from_fpl(bootstrap):
    """Build top scorers list from FPL bootstrap (sorted by goals desc)."""
    team_map = _build_fpl_team_map(bootstrap)
    scorers = []
    for p in bootstrap.get("elements", []):
        goals = p.get("goals_scored", 0)
        if goals > 0:
            team = team_map.get(p.get("team"), {})
            scorers.append({
                "player": {
                    "id": str(p.get("code", p.get("id", ""))),
                    "name": f"{p.get('first_name', '')} {p.get('second_name', '')}".strip(),
                    "first_name": p.get("first_name", ""),
                    "last_name": p.get("second_name", ""),
                    "nationality": "",
                    "position": _map_fpl_position(p.get("element_type")),
                    "date_of_birth": "",
                },
                "team": {
                    "id": str(team.get("code", team.get("id", ""))),
                    "name": team.get("name", ""),
                    "short_name": team.get("short_name", ""),
                    "abbreviation": team.get("short_name", ""),
                    "crest": "",
                },
                "goals": goals,
                "assists": p.get("assists", 0),
                "penalties": 0,
                "played_matches": p.get("starts", 0),
            })
    scorers.sort(key=lambda s: (-s["goals"], -s["assists"]))
    return scorers[:30]


# ============================================================
# Transfermarkt Helpers (ceapi)
# ============================================================

def _tm_market_value(tm_player_id):
    """Fetch market value development for a Transfermarkt player ID. Cached 24hr."""
    if not tm_player_id:
        return None
    return _tm_request(f"/ceapi/marketValueDevelopment/graph/{tm_player_id}", ttl=86400)


def _tm_transfer_history(tm_player_id):
    """Fetch transfer history for a Transfermarkt player ID. Cached 24hr."""
    if not tm_player_id:
        return None
    return _tm_request(f"/ceapi/transferHistory/list/{tm_player_id}", ttl=86400)


def _resolve_tm_player_id(params):
    """Resolve Transfermarkt player ID from explicit params."""
    return str(
        params.get("tm_player_id")
        or params.get("command_attribute", {}).get("tm_player_id", "")
    ) or None


def _normalize_tm_market_value(entry):
    """Normalize a single Transfermarkt market value data point."""
    return {
        "value": entry.get("y", 0),
        "currency": "EUR",
        "date": entry.get("datum_mw", ""),
        "formatted": entry.get("mw", ""),
        "age": entry.get("age", ""),
        "club": entry.get("verein", ""),
    }


def _normalize_tm_transfer(transfer, tm_player_id=""):
    """Normalize a Transfermarkt transfer record."""
    from_club = transfer.get("from", {}) if isinstance(transfer.get("from"), dict) else {}
    to_club = transfer.get("to", {}) if isinstance(transfer.get("to"), dict) else {}
    return {
        "player_tm_id": tm_player_id,
        "date": transfer.get("dateUnformatted", transfer.get("date", "")),
        "season": transfer.get("season", ""),
        "from_team": {
            "name": from_club.get("clubName", ""),
            "image": from_club.get("clubImage", from_club.get("clubEmblem-1x", "")),
        },
        "to_team": {
            "name": to_club.get("clubName", ""),
            "image": to_club.get("clubImage", to_club.get("clubEmblem-1x", "")),
        },
        "fee": transfer.get("fee", ""),
        "market_value": transfer.get("marketValue", ""),
    }


# ============================================================
# Command Functions (20 total)
# ESPN primary, football-data.org optional enrichment
# ============================================================

def get_current_season(params):
    """Detect current season for a competition using ESPN."""
    competition_id = (
        params.get("competition_id")
        or params.get("command_attribute", {}).get("competition_id", "")
    )
    league, slug = _resolve_competition(competition_id)
    if not league:
        return {"error": True, "message": f"Unknown competition: {competition_id}"}
    espn_slug = league.get("espn")
    if not espn_slug:
        return {"error": True, "message": f"No ESPN coverage for {slug}"}
    season = _detect_current_season(slug, espn_slug)
    if not season:
        return {"error": True, "message": "Could not detect current season"}
    return {
        "competition": {"id": slug, "name": league["name"]},
        "season": {
            "id": f"{slug}-{season['year']}",
            "name": season["display_name"],
            "year": str(season["year"]),
            "start_date": season["start_date"],
            "end_date": season["end_date"],
        },
        "calendar_dates": len(season.get("calendar", [])),
    }


def get_competitions(params):
    """List available competitions with current season info."""
    if _has_fd_key(params):
        data = _fd_request("/competitions", _get_api_key(params))
        if not data.get("error"):
            competitions = [
                _normalize_competition(c)
                for c in data.get("competitions", [])
                if c.get("id") in FD_ID_TO_SLUG
            ]
            return {"competitions": competitions}
    # ESPN path: build from LEAGUES config + season detection
    competitions = []
    for slug, league in LEAGUES.items():
        comp = {
            "id": slug,
            "name": league["name"],
            "code": league["code"],
            "category": {"id": _slugify(league["country"]), "name": league["country"]},
            "type": "LEAGUE",
        }
        espn_slug = league.get("espn")
        if espn_slug:
            season_info = _detect_current_season(slug, espn_slug)
            if season_info:
                comp["current_season"] = {
                    "year": str(season_info["year"]),
                    "start_date": season_info["start_date"],
                    "end_date": season_info["end_date"],
                }
        competitions.append(comp)
    return {"competitions": competitions}


def get_competition_seasons(params):
    """Get available seasons for a competition."""
    competition_id = (
        params.get("competition_id")
        or params.get("command_attribute", {}).get("competition_id", "")
    )
    league, slug = _resolve_competition(competition_id)
    if not league:
        return {"competition": {}, "seasons": [], "error": True,
                "message": f"Unknown competition: {competition_id}"}
    comp_info = {
        "id": slug, "name": league["name"], "code": league["code"],
        "category": {"id": _slugify(league["country"]), "name": league["country"]},
        "type": "LEAGUE",
    }
    if _has_fd_key(params):
        data = _fd_request(f"/competitions/{league['fd_id']}", _get_api_key(params))
        if not data.get("error"):
            return {
                "competition": _normalize_competition(data),
                "seasons": [_normalize_season(s, slug) for s in data.get("seasons", [])],
            }
    # ESPN path: standings endpoint has seasons list
    espn_slug = league.get("espn")
    if not espn_slug:
        return {"competition": comp_info, "seasons": [],
                "message": "No ESPN coverage for this competition"}
    data = _espn_web_request(espn_slug, "standings")
    if data.get("error"):
        season = _detect_current_season(slug, espn_slug)
        if season:
            return {"competition": comp_info, "seasons": [{
                "id": f"{slug}-{season['year']}", "name": season["display_name"],
                "year": str(season["year"]), "start_date": season["start_date"],
                "end_date": season["end_date"], "current_matchday": None,
            }]}
        return {"competition": comp_info, "seasons": []}
    seasons = []
    for s in data.get("seasons", []):
        year = str(s.get("year", ""))
        seasons.append({
            "id": f"{slug}-{year}",
            "name": s.get("displayName", year),
            "year": year,
            "start_date": s.get("startDate", ""),
            "end_date": s.get("endDate", ""),
            "current_matchday": None,
        })
    return {"competition": comp_info, "seasons": seasons}


def get_season_schedule(params):
    """Get full season match schedule."""
    season_id = (
        params.get("season_id")
        or params.get("command_attribute", {}).get("season_id", "")
    )
    league, slug, year = _resolve_season(season_id)
    if not league or not year:
        return {"schedules": [], "error": True, "message": f"Unknown season: {season_id}"}
    if _has_fd_key(params):
        data = _fd_request(
            f"/competitions/{league['fd_id']}/matches",
            _get_api_key(params), {"season": year},
        )
        if not data.get("error"):
            return {"schedules": [_normalize_match(m, slug) for m in data.get("matches", [])]}
    # ESPN path: aggregate team schedules from standings
    espn_slug = league.get("espn")
    if not espn_slug:
        return {"schedules": [], "message": "No ESPN coverage for this competition"}
    standings_data = _espn_web_request(espn_slug, "standings", {"season": str(year)})
    team_ids = []
    if not standings_data.get("error"):
        for child in standings_data.get("children", []):
            for entry in child.get("standings", {}).get("entries", []):
                tid = entry.get("team", {}).get("id")
                if tid:
                    team_ids.append(str(tid))
    if not team_ids:
        data = _espn_request(espn_slug, "scoreboard")
        return {"schedules": [_normalize_espn_event(e, slug) for e in data.get("events", [])]}
    all_events = {}
    expected_total = len(team_ids) * (len(team_ids) - 1)
    for tid in team_ids:
        data = _espn_request(espn_slug, f"teams/{tid}/schedule", {"season": str(year)})
        if not data.get("error"):
            for e in data.get("events", []):
                eid = e.get("id", "")
                if eid and eid not in all_events:
                    all_events[eid] = _normalize_espn_event(e, slug)
        if len(all_events) >= expected_total:
            break
    return {"schedules": sorted(all_events.values(), key=lambda e: e.get("start_time", ""))}


def get_season_standings(params):
    """Get season standings."""
    season_id = (
        params.get("season_id")
        or params.get("command_attribute", {}).get("season_id", "")
    )
    league, slug, year = _resolve_season(season_id)
    if not league:
        return {"standings": [], "error": True, "message": f"Unknown season: {season_id}"}
    if _has_fd_key(params):
        fd_params = {"season": year} if year else {}
        data = _fd_request(
            f"/competitions/{league['fd_id']}/standings",
            _get_api_key(params), fd_params,
        )
        if not data.get("error"):
            return {"standings": [_normalize_standings_group(s, slug) for s in data.get("standings", [])]}
    # ESPN path
    espn_slug = league.get("espn")
    if not espn_slug:
        return {"standings": [], "message": "No ESPN coverage for this competition"}
    espn_params = {"season": str(year)} if year else {}
    data = _espn_web_request(espn_slug, "standings", espn_params)
    if data.get("error"):
        return {"standings": []}
    return {"standings": _normalize_espn_standings(data, slug)}


def get_season_leaders(params):
    """Get top scorers/leaders. fd primary, FPL fallback for PL."""
    season_id = (
        params.get("season_id")
        or params.get("command_attribute", {}).get("season_id", "")
    )
    league, slug, year = _resolve_season(season_id)
    if not league:
        return {"leaders": [], "error": True, "message": f"Unknown season: {season_id}"}
    if _has_fd_key(params):
        fd_params = {"season": year} if year else {}
        data = _fd_request(
            f"/competitions/{league['fd_id']}/scorers",
            _get_api_key(params), fd_params,
        )
        if not data.get("error"):
            return {"leaders": [_normalize_scorer(s, slug) for s in data.get("scorers", [])]}
    # FPL fallback (PL only)
    if league.get("fpl"):
        bootstrap = _get_fpl_bootstrap()
        if bootstrap:
            leaders = _build_leaders_from_fpl(bootstrap)
            if leaders:
                return {"leaders": leaders}
    return {"leaders": [], "message": "Season leaders require football-data.org API key (or FPL for PL)"}


def get_season_teams(params):
    """Get teams in a season."""
    season_id = (
        params.get("season_id")
        or params.get("command_attribute", {}).get("season_id", "")
    )
    league, slug, year = _resolve_season(season_id)
    if not league:
        return {"teams": [], "error": True, "message": f"Unknown season: {season_id}"}
    if _has_fd_key(params):
        fd_params = {"season": year} if year else {}
        data = _fd_request(
            f"/competitions/{league['fd_id']}/teams",
            _get_api_key(params), fd_params,
        )
        if not data.get("error"):
            return {"teams": [_normalize_team(t) for t in data.get("teams", [])]}
    # ESPN path: extract teams from standings
    espn_slug = league.get("espn")
    if not espn_slug:
        return {"teams": [], "message": "No ESPN coverage for this competition"}
    data = _espn_web_request(espn_slug, "standings", {"season": str(year)} if year else {})
    if data.get("error"):
        return {"teams": []}
    teams = []
    seen = set()
    for child in data.get("children", []):
        for entry in child.get("standings", {}).get("entries", []):
            team = entry.get("team", {})
            tid = str(team.get("id", ""))
            if tid and tid not in seen:
                seen.add(tid)
                teams.append(_normalize_espn_team(team))
    return {"teams": teams}


def get_team_profile(params):
    """Get team profile with squad/roster. FPL enrichment for PL teams."""
    team_id = (
        params.get("team_id")
        or params.get("command_attribute", {}).get("team_id", "")
    )
    tid = _resolve_team_id(team_id)
    if not tid:
        return {"team": {}, "players": [], "error": True, "message": "Missing team_id"}
    league_slug = (
        params.get("league_slug")
        or params.get("command_attribute", {}).get("league_slug", "")
    )
    result = None
    if _has_fd_key(params):
        data = _fd_request(f"/teams/{tid}", _get_api_key(params))
        if not data.get("error"):
            team = _normalize_team(data)
            team_info = {"id": data.get("id", ""), "name": data.get("name", "")}
            players = [_normalize_player(p, team_info) for p in data.get("squad", [])]
            coach = data.get("coach", {})
            manager = {
                "id": str(coach.get("id", "")), "name": coach.get("name", ""),
                "nationality": coach.get("nationality", ""),
                "date_of_birth": coach.get("dateOfBirth", ""),
            } if coach else {}
            venue = {"id": str(data.get("id", "")), "name": data.get("venue", "")}
            result = {"team": team, "players": players, "manager": manager, "venue": venue}
    if not result:
        # ESPN path: try with league hint first, then search all leagues
        leagues_to_try = []
        if league_slug:
            league, _ = _resolve_competition(league_slug)
            if league and league.get("espn"):
                leagues_to_try.append(league["espn"])
        if not leagues_to_try:
            leagues_to_try = [lg["espn"] for lg in LEAGUES.values() if lg.get("espn")]
        for espn_slug in leagues_to_try:
            data = _espn_request(espn_slug, f"teams/{tid}")
            if data.get("error"):
                continue
            team_data = data.get("team", data)
            if team_data.get("id") or team_data.get("displayName"):
                result = {
                    "team": _normalize_espn_team(team_data),
                    "players": [],
                    "manager": {},
                    "venue": {
                        "id": "",
                        "name": team_data.get("venue", {}).get("fullName", "")
                        if isinstance(team_data.get("venue"), dict) else "",
                    },
                }
                break
    if not result:
        return {"team": {}, "players": [], "error": True, "message": "Team not found"}
    # FPL enrichment for PL teams
    if league_slug == "premier-league" and result.get("players"):
        _enrich_team_players_fpl(result["players"])
    elif not league_slug and result.get("players"):
        # Auto-detect PL by checking team name against FPL bootstrap
        bootstrap = _get_fpl_bootstrap()
        if bootstrap:
            team_name = result.get("team", {}).get("name", "")
            for fpl_team in bootstrap.get("teams", []):
                if _teams_match(team_name, fpl_team.get("name", "")):
                    _enrich_team_players_fpl(result["players"])
                    break
    return result


def get_daily_schedule(params):
    """Get all matches for a specific date across all leagues."""
    date = (
        params.get("date")
        or params.get("command_attribute", {}).get("date", "")
    )
    if not date:
        date = datetime.utcnow().strftime("%Y-%m-%d")
    date_key = date.replace("-", "")
    if _has_fd_key(params):
        data = _fd_request("/matches", _get_api_key(params), {"dateFrom": date, "dateTo": date})
        if not data.get("error"):
            return {"date": date, "events": [_normalize_match(m) for m in data.get("matches", [])]}
    # ESPN path: fetch scoreboard for each league on this date
    events = []
    seen = set()
    for slug, league in LEAGUES.items():
        espn_slug = league.get("espn")
        if not espn_slug:
            continue
        data = _espn_request(espn_slug, "scoreboard", {"dates": date_key})
        if data.get("error"):
            continue
        for e in data.get("events", []):
            eid = e.get("id", "")
            if eid and eid not in seen:
                seen.add(eid)
                events.append(_normalize_espn_event(e, slug))
    return {"date": date, "events": events}


# --- Event Details (ESPN summary primary) ---

def get_event_summary(params):
    """Get match summary with basic info and scores."""
    event_id = (
        params.get("event_id")
        or params.get("command_attribute", {}).get("event_id", "")
    )
    eid = _resolve_event_id(event_id)
    if not eid:
        return {"event": {}, "statistics": {}, "error": True, "message": "Missing event_id"}
    # ESPN primary
    espn_league, espn_eid = _resolve_espn_event(eid, params)
    if espn_league:
        summary = _espn_summary(espn_league, espn_eid)
        if summary and summary.get("header"):
            slug = ESPN_TO_SLUG.get(espn_league, "")
            header = summary["header"]
            comps = header.get("competitions", [{}])
            comp = comps[0] if comps else {}
            event_data = {
                "id": espn_eid,
                "competitions": [comp],
                "season": header.get("season", {}),
                "date": comp.get("date", ""),
                "week": header.get("week", {}),
            }
            event = _normalize_espn_event(event_data, slug)
            return {"event": event, "statistics": {}}
    # Fallback to fd
    if _has_fd_key(params):
        match_info = _get_match_info(eid, _get_api_key(params))
        if match_info:
            return {"event": _normalize_match(match_info["raw"]), "statistics": {}}
    return {"event": {}, "statistics": {}, "error": True, "message": "Could not resolve event"}


def get_event_lineups(params):
    """Get match lineups from ESPN summary."""
    event_id = (
        params.get("event_id")
        or params.get("command_attribute", {}).get("event_id", "")
    )
    eid = _resolve_event_id(event_id)
    if not eid:
        return {"lineups": [], "error": True, "message": "Missing event_id"}
    # ESPN primary
    espn_league, espn_eid = _resolve_espn_event(eid, params)
    if espn_league:
        summary = _espn_summary(espn_league, espn_eid)
        if summary:
            lineups = _normalize_espn_summary_lineups(summary)
            if lineups:
                return {"lineups": lineups}
    # Fallback: fd lineups
    if _has_fd_key(params):
        match_info = _get_match_info(eid, _get_api_key(params))
        if match_info:
            data = match_info["raw"]
            lineups = []
            for side, team_data in [("home", data.get("homeTeam", {})),
                                    ("away", data.get("awayTeam", {}))]:
                lineup = team_data.get("lineup", [])
                bench_list = team_data.get("bench", [])
                if lineup or bench_list:
                    lineups.append({
                        "team": {
                            "id": str(team_data.get("id", "")),
                            "name": team_data.get("name", team_data.get("shortName", "")),
                            "abbreviation": team_data.get("tla", ""),
                        },
                        "qualifier": side,
                        "formation": team_data.get("formation", ""),
                        "starting": [
                            {"id": str(p.get("id", "")), "name": p.get("name", ""),
                             "position": p.get("position", ""), "shirt_number": p.get("shirtNumber")}
                            for p in lineup
                        ],
                        "bench": [
                            {"id": str(p.get("id", "")), "name": p.get("name", ""),
                             "position": p.get("position", ""), "shirt_number": p.get("shirtNumber")}
                            for p in bench_list
                        ],
                    })
            if lineups:
                return {"lineups": lineups}
    return {"lineups": []}


def get_event_statistics(params):
    """Get match team statistics from ESPN summary."""
    event_id = (
        params.get("event_id")
        or params.get("command_attribute", {}).get("event_id", "")
    )
    eid = _resolve_event_id(event_id)
    if not eid:
        return {"teams": [], "error": True, "message": "Missing event_id"}
    espn_league, espn_eid = _resolve_espn_event(eid, params)
    if espn_league:
        summary = _espn_summary(espn_league, espn_eid)
        if summary:
            teams = _normalize_espn_summary_statistics(summary)
            if teams:
                return {"teams": teams}
    return {"teams": []}


def get_event_timeline(params):
    """Get match timeline/key events from ESPN summary."""
    event_id = (
        params.get("event_id")
        or params.get("command_attribute", {}).get("event_id", "")
    )
    eid = _resolve_event_id(event_id)
    if not eid:
        return {"timeline": [], "error": True, "message": "Missing event_id"}
    espn_league, espn_eid = _resolve_espn_event(eid, params)
    if espn_league:
        summary = _espn_summary(espn_league, espn_eid)
        if summary:
            timeline = _normalize_espn_summary_timeline(summary)
            if timeline:
                return {"timeline": timeline}
    return {"timeline": []}


def get_team_schedule(params):
    """Get schedule for a specific team."""
    team_id = (
        params.get("team_id")
        or params.get("command_attribute", {}).get("team_id", "")
    )
    tid = _resolve_team_id(team_id)
    if not tid:
        return {"team": {}, "events": [], "error": True, "message": "Missing team_id"}
    if _has_fd_key(params):
        data = _fd_request(f"/teams/{tid}/matches", _get_api_key(params), {"limit": 50})
        if not data.get("error"):
            events = [_normalize_match(m) for m in data.get("matches", [])]
            team_data = {}
            if events and events[0].get("competitors"):
                for comp in events[0]["competitors"]:
                    if comp.get("team", {}).get("id") == tid:
                        team_data = comp["team"]
                        break
            return {"team": team_data, "events": events}
    # ESPN path: try with league hint first
    league_slug = (
        params.get("league_slug")
        or params.get("command_attribute", {}).get("league_slug", "")
    )
    season_year = (
        params.get("season_year")
        or params.get("command_attribute", {}).get("season_year", "")
    )
    leagues_to_try = []
    if league_slug:
        league, _ = _resolve_competition(league_slug)
        if league and league.get("espn"):
            leagues_to_try.append((_, league))
    if not leagues_to_try:
        leagues_to_try = [(s, lg) for s, lg in LEAGUES.items() if lg.get("espn")]
    for slug, league in leagues_to_try:
        espn_slug = league["espn"]
        espn_params = {"season": str(season_year)} if season_year else {}
        data = _espn_request(espn_slug, f"teams/{tid}/schedule", espn_params)
        if data.get("error"):
            continue
        events_raw = data.get("events", [])
        if not events_raw:
            continue
        events = [_normalize_espn_event(e, slug) for e in events_raw]
        team_data = {}
        if events and events[0].get("competitors"):
            for comp in events[0]["competitors"]:
                if comp.get("team", {}).get("id") == tid:
                    team_data = comp["team"]
                    break
        return {"team": team_data, "events": events}
    return {"team": {}, "events": [], "message": "Team schedule not found"}


def get_head_to_head(params):
    """Get head-to-head history. Requires football-data.org API key."""
    team_id = (
        params.get("team_id")
        or params.get("command_attribute", {}).get("team_id", "")
    )
    team_id_2 = (
        params.get("team_id_2")
        or params.get("command_attribute", {}).get("team_id_2", "")
    )
    tid1 = _resolve_team_id(team_id)
    tid2 = _resolve_team_id(team_id_2)
    if not tid1 or not tid2:
        return {"teams": [], "events": [], "error": True, "message": "Missing team IDs"}
    if not _has_fd_key(params):
        return {"teams": [], "events": [],
                "message": "Head-to-head history requires football-data.org API key"}
    data = _fd_request(f"/teams/{tid1}/matches", _get_api_key(params), {"limit": 100})
    if data.get("error"):
        return {"teams": [], "events": [], "error": True, "message": data.get("message", "API error")}
    h2h_matches = []
    for m in data.get("matches", []):
        home_id = str(m.get("homeTeam", {}).get("id", ""))
        away_id = str(m.get("awayTeam", {}).get("id", ""))
        if (home_id == tid1 and away_id == tid2) or (home_id == tid2 and away_id == tid1):
            h2h_matches.append(_normalize_match(m))
    teams = []
    if h2h_matches:
        for comp in h2h_matches[0].get("competitors", []):
            teams.append(comp.get("team", {}))
    return {"teams": teams, "events": h2h_matches}


# --- Enrichment (Understat + ESPN) ---

def get_event_xg(params):
    """Get expected goals (xG) data from Understat (5 top leagues)."""
    event_id = (
        params.get("event_id")
        or params.get("command_attribute", {}).get("event_id", "")
    )
    eid = _resolve_event_id(event_id)
    if not eid:
        return {"event_id": event_id, "teams": [], "shots": [], "error": True,
                "message": "Missing event_id"}
    # Build match context (ESPN-first, fd fallback)
    match_ctx = None
    espn_league, espn_eid = _resolve_espn_event(eid, params)
    if espn_league:
        summary = _espn_summary(espn_league, espn_eid)
        if summary:
            match_ctx = _get_match_context(espn_league, espn_eid, summary)
    if not match_ctx and _has_fd_key(params):
        match_ctx = _get_match_info(eid, _get_api_key(params))
    if not match_ctx:
        return {"event_id": event_id, "teams": [], "shots": [],
                "message": "Could not resolve match"}
    if not match_ctx.get("understat_league"):
        return {
            "event_id": event_id, "teams": [], "shots": [],
            "message": (
                f"xG data not available for {match_ctx.get('slug', 'this league')}. "
                "Understat covers: EPL, La Liga, Bundesliga, Serie A, Ligue 1"
            ),
        }
    understat_id = _find_understat_match_id(match_ctx)
    if not understat_id:
        return {"event_id": event_id, "teams": [], "shots": [],
                "message": "Match not found on Understat"}
    udata = _get_understat_match(understat_id)
    if not udata:
        return {"event_id": event_id, "teams": [], "shots": [],
                "message": "Could not fetch Understat data"}
    result = _normalize_understat_xg(udata["shots"], udata["match_info"])
    result["event_id"] = event_id
    result["source"] = "understat"
    return result


def get_event_players_statistics(params):
    """Get player-level match statistics from ESPN + Understat xG."""
    event_id = (
        params.get("event_id")
        or params.get("command_attribute", {}).get("event_id", "")
    )
    eid = _resolve_event_id(event_id)
    if not eid:
        return {"event_id": event_id, "teams": [], "error": True, "message": "Missing event_id"}
    # ESPN primary for player stats
    espn_league, espn_eid = _resolve_espn_event(eid, params)
    summary = None
    if espn_league:
        summary = _espn_summary(espn_league, espn_eid)
    if summary:
        teams = _normalize_espn_summary_players(summary)
        if teams:
            # Enrich with Understat xG if available
            match_ctx = _get_match_context(espn_league, espn_eid, summary)
            if match_ctx and match_ctx.get("understat_league"):
                understat_id = _find_understat_match_id(match_ctx)
                if understat_id:
                    udata = _get_understat_match(understat_id)
                    if udata:
                        uteams = _normalize_understat_players(
                            udata["rosters"], udata["match_info"]
                        )
                        _merge_understat_player_xg(teams, uteams)
            return {"event_id": event_id, "teams": teams}
    # Fallback: fd-based match info for Understat-only
    if _has_fd_key(params):
        mi = _get_match_info(eid, _get_api_key(params))
        if mi and mi.get("understat_league"):
            understat_id = _find_understat_match_id(mi)
            if understat_id:
                udata = _get_understat_match(understat_id)
                if udata:
                    uteams = _normalize_understat_players(
                        udata["rosters"], udata["match_info"]
                    )
                    if uteams:
                        return {"event_id": event_id, "teams": uteams, "source": "understat"}
    return {"event_id": event_id, "teams": [], "message": "Player statistics not available"}


def _merge_understat_player_xg(espn_teams, ustat_teams):
    """Merge Understat xG data into ESPN player statistics (in-place)."""
    for espn_t in espn_teams:
        qualifier = espn_t.get("qualifier", "")
        ustat_t = next((u for u in ustat_teams if u.get("qualifier") == qualifier), None)
        if not ustat_t:
            continue
        ustat_players = {p["name"].lower(): p for p in ustat_t.get("players", [])}
        for ep in espn_t.get("players", []):
            ep_name = ep.get("name", "").lower()
            up = ustat_players.get(ep_name)
            if not up:
                for uname, upl in ustat_players.items():
                    if _teams_match(ep_name, uname):
                        up = upl
                        break
            if up:
                ep["statistics"]["xg"] = str(up.get("xg", 0))
                ep["statistics"]["xa"] = str(up.get("xa", 0))
                ep["statistics"]["xg_chain"] = str(up.get("xg_chain", 0))
                ep["statistics"]["xg_buildup"] = str(up.get("xg_buildup", 0))
                ep["statistics"]["key_passes"] = str(up.get("key_passes", 0))


def get_missing_players(params):
    """Get injured/missing/doubtful players. FPL source for PL."""
    season_id = (
        params.get("season_id")
        or params.get("command_attribute", {}).get("season_id", "")
    )
    league, slug, year = _resolve_season(season_id)
    if not league:
        return {"season_id": season_id, "teams": [],
                "error": True, "message": f"Unknown season: {season_id}"}
    # FPL path (PL only)
    if league.get("fpl"):
        bootstrap = _get_fpl_bootstrap()
        if bootstrap:
            return _build_missing_players_from_fpl(bootstrap, season_id)
    return {
        "season_id": season_id, "teams": [],
        "message": "Missing player data only available for Premier League (via FPL)",
    }


def get_season_transfers(params):
    """Get season transfers. Transfermarkt ceapi when tm_player_ids provided."""
    season_id = (
        params.get("season_id")
        or params.get("command_attribute", {}).get("season_id", "")
    )
    tm_player_ids = (
        params.get("tm_player_ids")
        or params.get("command_attribute", {}).get("tm_player_ids", [])
    )
    if not tm_player_ids:
        return {
            "season_id": season_id, "transfers": [],
            "message": "Transfers require tm_player_ids parameter (list of Transfermarkt player IDs)",
        }
    league, slug, year = _resolve_season(season_id)
    all_transfers = []
    for tm_id in tm_player_ids[:50]:
        history = _tm_transfer_history(str(tm_id))
        if not history:
            continue
        transfers_raw = history.get("transfers", history.get("transferHistory", []))
        if isinstance(transfers_raw, list):
            for t in transfers_raw:
                normalized = _normalize_tm_transfer(t, str(tm_id))
                if year and normalized.get("date"):
                    try:
                        t_year = int(normalized["date"][:4])
                        if abs(t_year - year) > 1:
                            continue
                    except (ValueError, TypeError):
                        pass
                all_transfers.append(normalized)
    return {"season_id": season_id, "transfers": all_transfers}


def get_player_profile(params):
    """Get player profile. fd primary, FPL fallback for PL, TM enrichment."""
    player_id = (
        params.get("player_id")
        or params.get("command_attribute", {}).get("player_id", "")
    )
    fpl_id = (
        params.get("fpl_id")
        or params.get("command_attribute", {}).get("fpl_id", "")
    )
    pid = _resolve_player_id(player_id)
    player = {}
    # fd path
    if pid and _has_fd_key(params):
        data = _fd_request(f"/persons/{pid}", _get_api_key(params))
        if not data.get("error"):
            player = _normalize_player(data)
    # FPL fallback/enrichment
    if fpl_id:
        bootstrap = _get_fpl_bootstrap()
        if bootstrap:
            for fp in bootstrap.get("elements", []):
                if str(fp.get("id")) == str(fpl_id) or str(fp.get("code")) == str(fpl_id):
                    if not player:
                        player = _normalize_fpl_player_as_profile(fp)
                    player["fpl_data"] = _normalize_fpl_player_enrichment(fp)
                    break
    elif not player and pid:
        # Try to find in FPL by matching code (FPL code == PL player code)
        bootstrap = _get_fpl_bootstrap()
        if bootstrap:
            for fp in bootstrap.get("elements", []):
                if str(fp.get("code")) == str(pid):
                    player = _normalize_fpl_player_as_profile(fp)
                    player["fpl_data"] = _normalize_fpl_player_enrichment(fp)
                    break
    # Transfermarkt enrichment
    tm_id = _resolve_tm_player_id(params)
    if tm_id:
        mv_data = _tm_market_value(tm_id)
        if mv_data and isinstance(mv_data, dict):
            mv_list = mv_data.get("list", mv_data.get("marketValueDevelopment", []))
            if isinstance(mv_list, list) and mv_list:
                player["market_value"] = _normalize_tm_market_value(mv_list[-1])
                player["market_value_history"] = [
                    _normalize_tm_market_value(entry) for entry in mv_list
                ]
        th_data = _tm_transfer_history(tm_id)
        if th_data and isinstance(th_data, dict):
            th_list = th_data.get("transfers", th_data.get("transferHistory", []))
            if isinstance(th_list, list) and th_list:
                player["transfer_history"] = [
                    _normalize_tm_transfer(t, tm_id) for t in th_list
                ]
    if not player:
        return {"player": {}, "message": "Player not found. Provide player_id, fpl_id, or tm_player_id."}
    return {"player": player}
