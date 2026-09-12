"""Project the provider's unavailable-player list for one fixture.

The provider reports two different states and they must not be flattened into
each other: "Missing Fixture" is ruled out, "Questionable" is a doubt. A
broadcaster reading a doubt as an absence is exactly the error this guards.
Entries are kept only when they name a player, a team that is in this fixture,
and this fixture's own id.
"""

from datetime import datetime, timedelta, timezone

RULED_OUT = "Missing Fixture"
DOUBTFUL = "Questionable"


def _params(request_data):
    if not isinstance(request_data, dict):
        return {}
    params = request_data.get("params")
    return params if isinstance(params, dict) else request_data


def _text(value, limit=160):
    return value.strip()[:limit] if isinstance(value, str) and value.strip() else None


def build_availability(rows, fixture_id, teams, event_code, source_event_id, observed_at):
    if not isinstance(rows, list):
        raise ValueError("injury rows must be a list")
    if not isinstance(teams, dict) or not teams.get("home") or not teams.get("away"):
        raise ValueError("both fixture teams are required")
    if not str(event_code or "").strip() or not str(source_event_id or "").strip():
        raise ValueError("event_code and source_event_id are required")
    expected_fixture = str(fixture_id or "").strip()
    if not expected_fixture:
        raise ValueError("fixture id is required")

    by_team_id = {}
    for side in ("home", "away"):
        team = teams.get(side) or {}
        team_id = str(team.get("id") or "").strip()
        name = _text(team.get("name"))
        if not team_id or not name:
            raise ValueError("each fixture team needs an id and a name")
        by_team_id[team_id] = {"side": side, "name": name, "ruled_out": [], "doubtful": []}

    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        player, team, fixture = row.get("player") or {}, row.get("team") or {}, row.get("fixture") or {}
        if str(fixture.get("id") or "").strip() != expected_fixture:
            continue
        entry = by_team_id.get(str(team.get("id") or "").strip())
        name = _text(player.get("name"))
        if entry is None or not name:
            continue
        state = _text(player.get("type"))
        key = (entry["side"], name)
        if key in seen:
            continue
        seen.add(key)
        record = {"name": name}
        reason = _text(player.get("reason"), 80)
        if reason:
            record["reason"] = reason
        if state == RULED_OUT:
            entry["ruled_out"].append(record)
        elif state == DOUBTFUL:
            entry["doubtful"].append(record)
        # An unrecognised state is dropped rather than guessed at.

    if not any(entry["ruled_out"] or entry["doubtful"] for entry in by_team_id.values()):
        raise ValueError("no usable availability rows for this fixture")

    now = (datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
           if isinstance(observed_at, str) and observed_at else datetime.now(timezone.utc))
    return {
        "schema_version": "broadcast-fixture-availability/1",
        "event_urn": str(event_code),
        "source_event_id": str(source_event_id),
        "fixture_id": expected_fixture,
        "observed_at": now.isoformat(),
        "fresh_until": (now + timedelta(hours=6)).isoformat(),
        "provider": "api-football",
        "operation": "injuries",
        "teams": [
            {"side": entry["side"], "team_name": entry["name"],
             "ruled_out": entry["ruled_out"][:12], "doubtful": entry["doubtful"][:12]}
            for entry in by_team_id.values()
        ],
        "limitations": [
            "Ruled out and doubtful are the provider's own two states and are never merged.",
            "A provider availability list is not a confirmed team sheet.",
        ],
    }


def invoke_build_availability(request_data):
    params = _params(request_data)
    try:
        snapshot = build_availability(params.get("rows"), params.get("fixture_id"), params.get("teams"),
                                      params.get("event_code"), params.get("source_event_id"),
                                      params.get("observed_at"))
        return {"status": True, "data": {"allowed": True, "snapshot": snapshot}}
    except Exception:
        # Never return provider exception text, credentials or a guessed absence.
        return {"status": True, "data": {"allowed": False, "snapshot": {},
                                         "refusals": [{"code": "fixture-availability-unavailable"}]}}
