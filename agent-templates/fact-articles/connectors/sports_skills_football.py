"""Fetch one competition's round from sports-skills (ESPN open data) into the dataset the core reads.

Dataset shape (feed objects are kept as sports-skills returns them):
    {"competition": {"id", "name"}, "season_id", "as_of": "YYYY-MM-DD",
     "events": [upcoming events in the local date range],
     "results": [closed events of the season, oldest first],
     "standings": [table entries]}
"""
from datetime import date, datetime, timedelta, timezone


# Previews are only for games not yet played; a postponed/cancelled/suspended game still gets a page saying so.
UPCOMING = {"not_started", "scheduled", "postponed", "cancelled", "suspended"}


class ConnectorError(RuntimeError):
    """The feed did not return what the core needs; no article is written."""


def _data(resp, what):
    if hasattr(resp, "model_dump"):
        resp = resp.model_dump()
    if not resp or not resp.get("status"):
        raise ConnectorError(f"sports-skills {what} failed: {(resp or {}).get('message') or 'empty response'}")
    return resp["data"]


def local_date(start_time, offset_hours):
    return (datetime.strptime(start_time, "%Y-%m-%dT%H:%MZ") + timedelta(hours=offset_hours)).date()


def fetch_round(competition_id, date_from, date_to, timezone_offset_hours=0, football=None, as_of=None):
    """Not-yet-played events (UPCOMING) of `competition_id` whose LOCAL date is in [date_from, date_to], plus season context."""
    if football is None:
        import sports_skills.football as football  # imported here so the core and tests load without the package
    d0, d1 = date.fromisoformat(date_from), date.fromisoformat(date_to)
    season = _data(football.get_current_season(competition_id=competition_id), "get_current_season")
    season_id = season.get("season", {}).get("id") or season.get("id")
    if not season_id:
        raise ConnectorError(f"no current season for {competition_id}")

    # Feed days are UTC; a 21h local kickoff west of UTC lands on the next UTC day, so read one extra day each side.
    events = {}
    day = d0 - timedelta(days=1)
    while day <= d1 + timedelta(days=1):
        for e in _data(football.get_daily_schedule(date=day.isoformat()), f"get_daily_schedule {day}").get("events", []):
            if e["competition"]["id"] == competition_id and e.get("status") in UPCOMING and d0 <= local_date(e["start_time"], timezone_offset_hours) <= d1:
                events[e["id"]] = e
        day += timedelta(days=1)
    if not events:
        raise ConnectorError(f"no {competition_id} events between {date_from} and {date_to}")

    schedule = _data(football.get_season_schedule(season_id=season_id), "get_season_schedule")["schedules"]
    tables = _data(football.get_season_standings(season_id=season_id), "get_season_standings")["standings"]
    if not tables or not tables[0].get("entries"):
        raise ConnectorError(f"empty standings for {season_id}")
    return {
        "competition": season.get("competition") or {"id": competition_id, "name": competition_id},
        "season_id": season_id,
        "as_of": as_of or datetime.now(timezone.utc).date().isoformat(),
        "events": sorted(events.values(), key=lambda e: e["start_time"]),
        "results": sorted((e for e in schedule if e["status"] == "closed"), key=lambda e: e["start_time"]),
        "standings": tables[0]["entries"],
    }


def invoke_fetch_round(request_data):
    p = request_data.get("params") or {}
    try:
        data = fetch_round(p["competition_id"], p["date_from"], p["date_to"], int(p.get("timezone_offset_hours", 0)))
    except (ConnectorError, KeyError, ValueError) as e:
        return {"status": False, "message": f"connector error: {e}"}
    return {"status": True, "data": data}
