"""Project the provider's pre-match forecast into a bounded expectation.

A forecast is a model output, not an observation, so the snapshot is never
fact-eligible. The provider's betting advice and its named winner are dropped
rather than carried: this is broadcast context, not a tip.
"""

from datetime import datetime, timedelta, timezone


def _params(request_data):
    if not isinstance(request_data, dict):
        return {}
    params = request_data.get("params")
    return params if isinstance(params, dict) else request_data


def _share(value):
    """A provider percentage string as a 0-1 number, or None when unusable."""
    if not isinstance(value, str) or not value.endswith("%"):
        return None
    try:
        share = float(value[:-1]) / 100.0
    except ValueError:
        return None
    return round(share, 4) if 0.0 <= share <= 1.0 else None


def build_forecast(forecast, event_code, source_event_id, observed_at):
    if not isinstance(forecast, dict):
        raise ValueError("forecast must be an object")
    if not isinstance(event_code, str) or not event_code.strip():
        raise ValueError("event_code is required")
    if not str(source_event_id or "").strip():
        raise ValueError("source_event_id is required")
    now = (datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
           if isinstance(observed_at, str) and observed_at else datetime.now(timezone.utc))

    predictions = forecast.get("predictions")
    percent = predictions.get("percent") if isinstance(predictions, dict) else None
    if not isinstance(percent, dict):
        raise ValueError("forecast carries no outcome percentages")
    shares = {key: _share(percent.get(key)) for key in ("home", "draw", "away")}
    if any(value is None for value in shares.values()):
        raise ValueError("incomplete outcome percentages")
    if not 0.95 <= sum(shares.values()) <= 1.05:
        raise ValueError("outcome percentages do not sum to one")

    comparison = forecast.get("comparison")
    strengths = {}
    if isinstance(comparison, dict):
        for key in ("form", "att", "def", "goals", "total"):
            block = comparison.get(key)
            if not isinstance(block, dict):
                continue
            home, away = _share(block.get("home")), _share(block.get("away"))
            if home is not None and away is not None:
                strengths[key] = {"home": home, "away": away}

    return {
        "schema_version": "broadcast-fixture-forecast/1",
        "event_urn": str(event_code),
        "source_event_id": str(source_event_id),
        "observed_at": now.isoformat(),
        "fresh_until": (now + timedelta(hours=6)).isoformat(),
        "provider": "api-football",
        "operation": "predictions",
        "fact_eligible": False,
        "outcome_shares": shares,
        "strength_comparison": strengths,
        "limitations": [
            "A provider forecast is a model expectation, not an observed fact or a Machina projection.",
            "Betting advice and the provider's named winner are not carried.",
        ],
    }


def invoke_build_forecast(request_data):
    params = _params(request_data)
    try:
        snapshot = build_forecast(params.get("forecast"), params.get("event_code"),
                                  params.get("source_event_id"), params.get("observed_at"))
        return {"status": True, "data": {"allowed": True, "snapshot": snapshot}}
    except Exception:
        # Never return provider exception text, credentials or a guessed share.
        return {"status": True, "data": {"allowed": False, "snapshot": {},
                                         "refusals": [{"code": "fixture-forecast-unavailable"}]}}
