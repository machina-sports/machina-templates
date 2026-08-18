"""Credential-safe Fight Analytics contract smoke connector."""

from __future__ import annotations

import math
from typing import Any

import requests


_AUTH_API = "https://auth-api.fightanalytics.cc"
_METADATA_API = "https://api.fightanalytics.cc"
_STATISTICS_API = "https://mike-goldberg-v2.fightanalytics.cc"
_TIMEOUT = (5, 30)
_FANTASY_SAMPLE_LIMIT = 10
_FANTASY_METRICS = (
    "score",
    "significantStrikes",
    "totalStrikes",
    "takedowns",
    "takedownAttempts",
    "submissionAttempts",
    "knockdowns",
    "elapsedControlTime",
)
_SAFE_FAILURE_CODES = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    409: "CONFLICT",
    422: "INVALID_REQUEST",
    429: "RATE_LIMITED",
}


def _inputs(request_data: Any) -> dict:
    if not isinstance(request_data, dict):
        return {}
    value = request_data.get("params") or request_data.get("inputs") or request_data
    return value if isinstance(value, dict) else {}


def _shape(payload: Any) -> tuple[str, int]:
    if payload is None:
        return "empty", 0
    if isinstance(payload, list):
        return "array", len(payload)
    if isinstance(payload, dict):
        return "object", len(payload)
    return "scalar", 1


def _failure_code(status: int) -> str:
    if status in _SAFE_FAILURE_CODES:
        return _SAFE_FAILURE_CODES[status]
    if 500 <= status <= 599:
        return "SERVER_ERROR"
    return "UNEXPECTED_STATUS"


def _receipt(
    operation: str,
    status: Any,
    shape: str,
    count: int,
    failure_code: str | None = None,
) -> dict:
    result = {
        "operation": operation,
        "status": status,
        "shape": shape,
        "count": count,
    }
    if failure_code:
        result["failureCode"] = failure_code
    return result


def _request(
    operation: str,
    method: str,
    path: str,
    *,
    base_url: str = _METADATA_API,
    access_token: str | None = None,
    body: dict | None = None,
    query: dict | None = None,
    per_page: int = 1,
    accepted_statuses: set[int] | None = None,
) -> tuple[dict, Any, bool]:
    headers = {"Accept": "application/json"}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    if method == "GET" and path in {
        "/promotions", "/venues", "/teams", "/events", "/fighters",
        "/fights", "/actions",
    }:
        headers["per_page"] = str(per_page)

    try:
        request_kwargs = {
            "headers": headers,
            "json": body,
            "timeout": _TIMEOUT,
        }
        if query is not None:
            request_kwargs["params"] = query
        response = requests.request(method, f"{base_url}{path}", **request_kwargs)
    except Exception:
        return _receipt(operation, "network_error", "none", 0, "NETWORK_ERROR"), None, False

    try:
        payload = response.json()
    except Exception:
        return (
            _receipt(operation, response.status_code, "invalid", 0, "INVALID_RESPONSE"),
            None,
            False,
        )

    shape, count = _shape(payload)
    accepted = accepted_statuses or {200}
    if response.status_code not in accepted:
        return (
            _receipt(
                operation,
                response.status_code,
                shape,
                count,
                _failure_code(response.status_code),
            ),
            payload,
            False,
        )
    return _receipt(operation, response.status_code, shape, count), payload, True


def _first_id(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    if not isinstance(data, list) or not data or not isinstance(data[0], dict):
        return None
    value = data[0].get("id")
    return value if isinstance(value, str) and value else None


def _not_executed(operation: str, code: str = "MISSING_REQUIRED_ID") -> dict:
    return _receipt(operation, "not_executed", "none", 0, code)


def _safe_text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _safe_number(value: Any) -> int | float | None:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _safe_finite_number_or_text(value: Any) -> int | float | str | None:
    text = _safe_text(value)
    if text is not None:
        return text
    number = _safe_number(value)
    if isinstance(number, int):
        return number
    return number if number is not None and math.isfinite(number) else None


def _safe_winner_id(value: Any) -> int | str | None:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return _safe_text(value)


def _fantasy_receipt(
    endpoint: str,
    classification: str,
    http_status: Any,
    shape: str,
    count: int,
    failure_code: str | None = None,
    *,
    event_id: str | None = None,
    fight_id: str | None = None,
    fighter_id: str | None = None,
) -> dict:
    return {
        "endpoint": endpoint,
        "classification": classification,
        "httpStatus": http_status,
        "shape": shape,
        "count": count,
        "failureCode": failure_code,
        "providerEventId": event_id,
        "providerFightId": fight_id,
        "providerFighterId": fighter_id,
    }


def _classify_payload(
    endpoint: str,
    request_receipt: dict,
    payload: Any,
    request_ok: bool,
    expected: str,
    *,
    event_id: str | None = None,
    fight_id: str | None = None,
    fighter_id: str | None = None,
) -> tuple[dict, Any]:
    status = request_receipt.get("status")
    common = {
        "event_id": event_id,
        "fight_id": fight_id,
        "fighter_id": fighter_id,
    }
    if not request_ok:
        classification = "unavailable" if status == 404 else "failed"
        return _fantasy_receipt(
            endpoint,
            classification,
            status,
            request_receipt.get("shape", "none"),
            request_receipt.get("count", 0),
            request_receipt.get("failureCode", "REQUEST_FAILED"),
            **common,
        ), None

    value = payload
    if expected in {"collection", "actions"}:
        if (
            not isinstance(payload, dict)
            or not isinstance(payload.get("data"), list)
            or not isinstance(payload.get("pagination"), dict)
        ):
            return _fantasy_receipt(
                endpoint, "failed", status, "invalid", 0, "INVALID_SHAPE", **common
            ), None
        value = payload["data"]
    elif expected == "array" and not isinstance(payload, list):
        return _fantasy_receipt(
            endpoint, "failed", status, "invalid", 0, "INVALID_SHAPE", **common
        ), None
    elif expected == "object" and not isinstance(payload, dict):
        return _fantasy_receipt(
            endpoint, "failed", status, "invalid", 0, "INVALID_SHAPE", **common
        ), None

    if expected in {"array", "actions"} and any(
        not isinstance(item, dict) for item in value
    ):
        return _fantasy_receipt(
            endpoint, "failed", status, "invalid", 0, "INVALID_SHAPE", **common
        ), None

    count = len(value)
    shape = "array" if isinstance(value, list) else "object"
    classification = "data_success" if count else "provider_empty"
    failure_code = None if count else "PROVIDER_EMPTY"
    return _fantasy_receipt(
        endpoint,
        classification,
        status,
        shape,
        count,
        failure_code,
        **common,
    ), value


def _empty_coverage_counts() -> dict:
    return {
        "dataSuccess": 0,
        "providerEmpty": 0,
        "unavailable": 0,
        "failed": 0,
        "classification": "provider_empty",
    }


def _empty_fantasy_packet() -> dict:
    return {
        "packetType": "prototype_canary",
        "verdict": "failed",
        "fullPathExecuted": False,
        "sourceHosts": ["api.fightanalytics.cc", "mike-goldberg-v2.fightanalytics.cc"],
        "limitations": [
            "prototype_only",
            "provider_scoped_ids",
            "bounded_statistics_sample",
            "no_canonical_mapping",
        ],
        "sampleLimit": _FANTASY_SAMPLE_LIMIT,
        "event": {"providerEventId": None, "label": None, "date": None},
        "fight": {
            "providerFightId": None,
            "providerEventId": None,
            "label": None,
            "redFighterId": None,
            "blueFighterId": None,
        },
        "fighters": [],
        "fighterStats": [],
        "fightStats": {
            "providerFightId": None,
            "status": None,
            "currentRound": None,
            "currentStance": None,
            "finish": {"type": None, "round": None, "time": None, "winnerId": None},
            "fightersOutcomeCount": 0,
        },
        "scenarios": [],
        "coverage": {
            "sampledFights": 0,
            "classification": "provider_empty",
            "fightSummary": _empty_coverage_counts(),
            "totals": _empty_coverage_counts(),
            "rounds": _empty_coverage_counts(),
            "actions": _empty_coverage_counts(),
        },
    }


def _failed_fantasy(packet: dict, endpoint: str, code: str) -> dict:
    packet["scenarios"].append(
        _fantasy_receipt(endpoint, "failed", "not_executed", "none", 0, code)
    )
    return {"status": False, "data": packet}


def _failed_fantasy_request(
    packet: dict,
    endpoint: str,
    request_receipt: dict,
    failure_code: str | None = None,
) -> dict:
    packet["scenarios"].append(
        _fantasy_receipt(
            endpoint,
            "failed",
            request_receipt.get("status", "not_executed"),
            request_receipt.get("shape", "none"),
            request_receipt.get("count", 0),
            failure_code or request_receipt.get("failureCode", "AUTH_FAILED"),
        )
    )
    return {"status": False, "data": packet}


def _replace_with_shape_failure(receipt: dict, code: str = "INVALID_SHAPE") -> dict:
    return _fantasy_receipt(
        receipt["endpoint"],
        "failed",
        receipt["httpStatus"],
        "invalid",
        0,
        code,
        event_id=receipt["providerEventId"],
        fight_id=receipt["providerFightId"],
        fighter_id=receipt["providerFighterId"],
    )


def _fighter_identity(payload: Any, corner: str, expected_id: str) -> dict | None:
    if not isinstance(payload, dict) or _safe_text(payload.get("id")) != expected_id:
        return None
    first_name = _safe_text(payload.get("firstName"))
    last_name = _safe_text(payload.get("lastName"))
    record = {
        "wins": _safe_number(payload.get("wins")),
        "losses": _safe_number(payload.get("losses")),
        "draws": _safe_number(payload.get("draws")),
    }
    if not first_name or not last_name or any(value is None for value in record.values()):
        return None
    return {
        "corner": corner,
        "providerFighterId": expected_id,
        "label": f"{first_name} {last_name}",
        "country": _safe_text(payload.get("country")),
        "weightClass": _safe_text(payload.get("weightClass")),
        "record": record,
    }


def _fighter_statistics(payload: Any, corner: str, fighter_id: str) -> dict | None:
    if not isinstance(payload, dict):
        return None
    values = {
        key: _safe_number(payload.get(key))
        for key in ("wins", "losses", "draws", "score", "elapsedFightTime", "totalRounds")
    }
    metrics = {}
    for stance in ("standing", "ground", "fence", "riding"):
        source = payload.get(stance)
        if not isinstance(source, dict):
            return None
        metrics[stance] = {key: _safe_number(source.get(key)) for key in _FANTASY_METRICS}
        if any(value is None for value in metrics[stance].values()):
            return None
    if any(value is None for value in values.values()):
        return None
    return {
        "corner": corner,
        "providerFighterId": fighter_id,
        "record": {
            "wins": values["wins"],
            "losses": values["losses"],
            "draws": values["draws"],
        },
        "score": values["score"],
        "elapsedFightTime": values["elapsedFightTime"],
        "totalRounds": values["totalRounds"],
        "metrics": metrics,
    }


def _fight_statistics(payload: Any, fight_id: str) -> dict | None:
    if not isinstance(payload, dict) or not payload:
        return None
    if _safe_text(payload.get("fightNewId")) != fight_id:
        return None
    outcomes = payload.get("fightersOutcome")
    status = _safe_text(payload.get("status"))
    current_round = _safe_number(payload.get("currentRound"))
    current_stance = _safe_text(payload.get("currentStance"))
    if (
        not isinstance(outcomes, list)
        or any(not isinstance(outcome, dict) for outcome in outcomes)
        or status is None
        or current_round is None
        or current_stance is None
    ):
        return None
    finish_type = payload.get("finishType")
    if finish_type is not None and _safe_text(finish_type) is None:
        return None
    finish_round = payload.get("finishRound")
    if finish_round is not None and _safe_number(finish_round) is None:
        return None
    raw_finish_time = payload.get("finishTime")
    finish_time = (
        None if raw_finish_time is None else _safe_finite_number_or_text(raw_finish_time)
    )
    if raw_finish_time is not None and finish_time is None:
        return None
    raw_winner_id = payload.get("winnerId")
    winner_id = None if raw_winner_id is None else _safe_winner_id(raw_winner_id)
    if raw_winner_id is not None and winner_id is None:
        return None
    return {
        "providerFightId": fight_id,
        "status": status,
        "currentRound": current_round,
        "currentStance": current_stance,
        "finish": {
            "type": finish_type,
            "round": finish_round,
            "time": finish_time,
            "winnerId": winner_id,
        },
        "fightersOutcomeCount": len(outcomes),
    }


def _update_coverage(counts: dict, classification: str) -> None:
    key = {
        "data_success": "dataSuccess",
        "provider_empty": "providerEmpty",
        "unavailable": "unavailable",
        "failed": "failed",
    }[classification]
    counts[key] += 1


def _finalize_coverage(coverage: dict) -> None:
    aggregate = {name: 0 for name in ("dataSuccess", "providerEmpty", "unavailable", "failed")}
    for endpoint in ("fightSummary", "totals", "rounds", "actions"):
        counts = coverage[endpoint]
        populated = []
        for name, classification in (
            ("dataSuccess", "data_success"),
            ("providerEmpty", "provider_empty"),
            ("unavailable", "unavailable"),
            ("failed", "failed"),
        ):
            aggregate[name] += counts[name]
            if counts[name]:
                populated.append(classification)
        counts["classification"] = populated[0] if len(populated) == 1 else "mixed"
    populated = [
        classification
        for name, classification in (
            ("dataSuccess", "data_success"),
            ("providerEmpty", "provider_empty"),
            ("unavailable", "unavailable"),
            ("failed", "failed"),
        )
        if aggregate[name]
    ]
    coverage["classification"] = populated[0] if len(populated) == 1 else "mixed"


def run_certified_smoke(request_data: Any, *_, **__) -> dict:
    """Run the bounded certification without returning credentials or tokens."""

    inputs = _inputs(request_data)
    username = inputs.get("username")
    password = inputs.get("password")
    operations = []
    if not isinstance(username, str) or not username or not isinstance(password, str) or not password:
        operations.append(_not_executed("POST /auth/login", "MISSING_CREDENTIALS"))
        return {"status": False, "data": {"operations": operations}}

    login, login_payload, login_ok = _request(
        "POST /auth/login",
        "POST",
        "/auth/login",
        base_url=_AUTH_API,
        body={"username": username, "password": password},
        accepted_statuses={201},
    )
    operations.append(login)
    if not login_ok or not isinstance(login_payload, dict):
        return {"status": False, "data": {"operations": operations}}
    access_token = login_payload.get("accessToken")
    refresh_token = login_payload.get("refreshToken")
    if not isinstance(access_token, str) or not access_token or not isinstance(refresh_token, str) or not refresh_token:
        operations[-1] = _receipt(
            "POST /auth/login", login["status"], login["shape"], login["count"], "INVALID_AUTH_RESPONSE"
        )
        return {"status": False, "data": {"operations": operations}}

    me, _, me_ok = _request(
        "GET /auth/me",
        "GET",
        "/auth/me",
        base_url=_AUTH_API,
        access_token=access_token,
    )
    operations.append(me)

    refresh, refresh_payload, refresh_ok = _request(
        "POST /auth/refresh",
        "POST",
        "/auth/refresh",
        base_url=_AUTH_API,
        body={"token": refresh_token},
        accepted_statuses={201},
    )
    operations.append(refresh)
    if not refresh_ok or not isinstance(refresh_payload, dict):
        return {"status": False, "data": {"operations": operations}}
    refreshed_access_token = refresh_payload.get("accessToken")
    refreshed_refresh_token = refresh_payload.get("refreshToken")
    if (
        not isinstance(refreshed_access_token, str)
        or not refreshed_access_token
        or not isinstance(refreshed_refresh_token, str)
        or not refreshed_refresh_token
    ):
        operations[-1] = _receipt(
            "POST /auth/refresh",
            refresh["status"],
            refresh["shape"],
            refresh["count"],
            "INVALID_AUTH_RESPONSE",
        )
        return {"status": False, "data": {"operations": operations}}

    certified = me_ok
    ids = {}
    for resource in ("promotions", "venues", "teams", "events", "fighters", "fights"):
        list_operation = f"GET /{resource}"
        list_receipt, payload, list_ok = _request(
            list_operation,
            "GET",
            f"/{resource}",
            access_token=refreshed_access_token,
        )
        operations.append(list_receipt)
        certified = certified and list_ok
        resource_id = _first_id(payload)
        ids[resource] = resource_id
        detail_operation = f"GET /{resource}/{{id}}"
        if not resource_id:
            operations.append(_not_executed(detail_operation))
            certified = False
            continue
        detail_receipt, _, detail_ok = _request(
            detail_operation,
            "GET",
            f"/{resource}/{resource_id}",
            access_token=refreshed_access_token,
        )
        operations.append(detail_receipt)
        certified = certified and detail_ok

    one_receipt, _, one_forbidden = _request(
        "GET /one/events",
        "GET",
        "/one/events",
        access_token=refreshed_access_token,
        accepted_statuses={403},
    )
    if one_forbidden:
        one_receipt["failureCode"] = "SCOPE_FORBIDDEN"
    operations.append(one_receipt)
    operations.append(_not_executed("GET /one/events/{oneEventId}", "SCOPE_UNVERIFIED"))
    certified = certified and one_forbidden

    fighter_id = ids.get("fighters")
    fight_id = ids.get("fights")
    statistics = (
        ("GET /stats/actions", "/actions"),
        ("GET /stats/fighters/{id}", f"/fighters/{fighter_id}" if fighter_id else None),
        (
            "GET /stats/fighters/{id}/career",
            f"/fighters/{fighter_id}/career" if fighter_id else None,
        ),
        ("GET /stats/fights/{id}", f"/fights/{fight_id}" if fight_id else None),
        (
            "GET /stats/fights/{id}/totals",
            f"/fights/{fight_id}/totals" if fight_id else None,
        ),
        (
            "GET /stats/fights/{id}/rounds",
            f"/fights/{fight_id}/rounds" if fight_id else None,
        ),
        (
            "GET /stats/fights/{id}/rounds/{roundNumber}",
            f"/fights/{fight_id}/rounds/1" if fight_id else None,
        ),
    )
    for operation, path in statistics:
        if not path:
            operations.append(_not_executed(operation))
            certified = False
            continue
        receipt, _, operation_ok = _request(
            operation,
            "GET",
            path,
            base_url=_STATISTICS_API,
            access_token=refreshed_access_token,
        )
        operations.append(receipt)
        certified = certified and operation_ok

    return {
        "status": certified,
        "data": {"operations": operations},
    }


def _run_fantasy_scenarios(request_data: Any) -> dict:
    packet = _empty_fantasy_packet()
    inputs = _inputs(request_data)
    username = inputs.get("username")
    password = inputs.get("password")
    requested_fight_id = inputs.get("fight_id")
    if not isinstance(username, str) or not username or not isinstance(password, str) or not password:
        return _failed_fantasy(packet, "authentication", "MISSING_CREDENTIALS")
    if requested_fight_id is not None:
        requested_fight_id = _safe_text(requested_fight_id)
        if requested_fight_id is None:
            return _failed_fantasy(packet, "fight_selection", "INVALID_FIGHT_ID")

    login, login_payload, login_ok = _request(
        "fantasy authentication",
        "POST",
        "/auth/login",
        base_url=_AUTH_API,
        body={"username": username, "password": password},
        accepted_statuses={201},
    )
    if not login_ok:
        return _failed_fantasy_request(packet, "fantasy authentication", login)
    if not isinstance(login_payload, dict):
        return _failed_fantasy_request(
            packet, "fantasy authentication", login, "INVALID_AUTH_RESPONSE"
        )
    access_token = _safe_text(login_payload.get("accessToken"))
    refresh_token = _safe_text(login_payload.get("refreshToken"))
    if not access_token or not refresh_token:
        return _failed_fantasy_request(
            packet, "fantasy authentication", login, "INVALID_AUTH_RESPONSE"
        )

    me, _, me_ok = _request(
        "fantasy identity",
        "GET",
        "/auth/me",
        base_url=_AUTH_API,
        access_token=access_token,
    )
    if not me_ok:
        return _failed_fantasy_request(packet, "fantasy identity", me)

    refresh, refresh_payload, refresh_ok = _request(
        "fantasy refresh",
        "POST",
        "/auth/refresh",
        base_url=_AUTH_API,
        body={"token": refresh_token},
        accepted_statuses={201},
    )
    if not refresh_ok:
        return _failed_fantasy_request(packet, "fantasy refresh", refresh)
    if not isinstance(refresh_payload, dict):
        return _failed_fantasy_request(
            packet, "fantasy refresh", refresh, "INVALID_AUTH_RESPONSE"
        )
    refreshed_access_token = _safe_text(refresh_payload.get("accessToken"))
    refreshed_refresh_token = _safe_text(refresh_payload.get("refreshToken"))
    if not refreshed_access_token or not refreshed_refresh_token:
        return _failed_fantasy_request(
            packet, "fantasy refresh", refresh, "INVALID_AUTH_RESPONSE"
        )

    def call(
        endpoint: str,
        path: str,
        expected: str,
        *,
        base_url: str = _METADATA_API,
        query: dict | None = None,
        event_id: str | None = None,
        fight_id: str | None = None,
        fighter_id: str | None = None,
        per_page: int = 1,
    ) -> tuple[dict, Any]:
        request_receipt, payload, request_ok = _request(
            endpoint,
            "GET",
            path,
            base_url=base_url,
            access_token=refreshed_access_token,
            query=query,
            per_page=per_page,
        )
        return _classify_payload(
            endpoint,
            request_receipt,
            payload,
            request_ok,
            expected,
            event_id=event_id,
            fight_id=fight_id,
            fighter_id=fighter_id,
        )

    events_receipt, events = call(
        "discover_events", "/events", "collection", per_page=_FANTASY_SAMPLE_LIMIT
    )
    packet["scenarios"].append(events_receipt)
    if events_receipt["classification"] != "data_success":
        return {"status": False, "data": packet}
    if any(not isinstance(item, dict) or _safe_text(item.get("id")) is None for item in events):
        packet["scenarios"][-1] = _replace_with_shape_failure(events_receipt)
        return {"status": False, "data": packet}

    fights_receipt, fights = call(
        "discover_fights", "/fights", "collection", per_page=_FANTASY_SAMPLE_LIMIT
    )
    packet["scenarios"].append(fights_receipt)
    if fights_receipt["classification"] != "data_success":
        return {"status": False, "data": packet}
    if any(not isinstance(item, dict) or _safe_text(item.get("id")) is None for item in fights):
        packet["scenarios"][-1] = _replace_with_shape_failure(fights_receipt)
        return {"status": False, "data": packet}
    sorted_fights = sorted(fights, key=lambda item: item["id"])
    sample = sorted_fights[:_FANTASY_SAMPLE_LIMIT]
    if requested_fight_id:
        selected_fight_id = requested_fight_id
        selected_list_item = next(
            (item for item in sorted_fights if item["id"] == requested_fight_id),
            {"id": requested_fight_id},
        )
        if all(item["id"] != requested_fight_id for item in sample):
            sample = [selected_list_item, *sample[: _FANTASY_SAMPLE_LIMIT - 1]]
    else:
        selected_fight_id = sample[0]["id"]
    packet["coverage"]["sampledFights"] = len(sample)

    detail_receipt, fight_detail = call(
        "fight_detail",
        f"/fights/{selected_fight_id}",
        "object",
        fight_id=selected_fight_id,
    )
    packet["scenarios"].append(detail_receipt)
    if detail_receipt["classification"] != "data_success":
        return {"status": False, "data": packet}

    event = fight_detail.get("event") if isinstance(fight_detail, dict) else None
    red_corner = fight_detail.get("redCorner") if isinstance(fight_detail, dict) else None
    blue_corner = fight_detail.get("blueCorner") if isinstance(fight_detail, dict) else None
    event_id = _safe_text(fight_detail.get("eventId")) if isinstance(fight_detail, dict) else None
    red_id = _safe_text(fight_detail.get("redCornerId")) if isinstance(fight_detail, dict) else None
    blue_id = _safe_text(fight_detail.get("blueCornerId")) if isinstance(fight_detail, dict) else None
    event_name = _safe_text(event.get("name")) if isinstance(event, dict) else None
    embedded_event_id = _safe_text(event.get("id")) if isinstance(event, dict) else None
    red_name = (
        f"{_safe_text(red_corner.get('firstName'))} {_safe_text(red_corner.get('lastName'))}"
        if isinstance(red_corner, dict)
        and _safe_text(red_corner.get("firstName"))
        and _safe_text(red_corner.get("lastName"))
        else None
    )
    blue_name = (
        f"{_safe_text(blue_corner.get('firstName'))} {_safe_text(blue_corner.get('lastName'))}"
        if isinstance(blue_corner, dict)
        and _safe_text(blue_corner.get("firstName"))
        and _safe_text(blue_corner.get("lastName"))
        else None
    )
    detail_red_id = _safe_text(red_corner.get("id")) if isinstance(red_corner, dict) else None
    detail_blue_id = _safe_text(blue_corner.get("id")) if isinstance(blue_corner, dict) else None
    if (
        _safe_text(fight_detail.get("id")) != selected_fight_id
        or not event_id
        or embedded_event_id != event_id
        or not event_name
        or not red_id
        or not blue_id
        or detail_red_id != red_id
        or detail_blue_id != blue_id
        or not red_name
        or not blue_name
    ):
        packet["scenarios"][-1] = _replace_with_shape_failure(detail_receipt, "JOIN_MISMATCH")
        return {"status": False, "data": packet}

    packet["scenarios"][-1]["providerEventId"] = event_id
    event_receipt, event_detail = call(
        "event_detail",
        f"/events/{event_id}",
        "object",
        event_id=event_id,
        fight_id=selected_fight_id,
    )
    if event_receipt["classification"] == "data_success":
        event_detail_id = _safe_text(event_detail.get("id"))
        event_detail_name = _safe_text(event_detail.get("name"))
        embedded_event_date = _safe_text(event.get("date"))
        event_detail_date = _safe_text(event_detail.get("date"))
        if (
            event_detail_id != event_id
            or event_detail_id != embedded_event_id
            or event_detail_name != event_name
            or event_detail_date != embedded_event_date
        ):
            event_receipt = _replace_with_shape_failure(event_receipt, "JOIN_MISMATCH")
    packet["scenarios"].append(event_receipt)
    if event_receipt["classification"] != "data_success":
        return {"status": False, "data": packet}

    packet["event"] = {
        "providerEventId": event_id,
        "label": event_detail_name,
        "date": event_detail_date,
    }
    packet["fight"] = {
        "providerFightId": selected_fight_id,
        "providerEventId": event_id,
        "label": f"{red_name} vs {blue_name}",
        "redFighterId": red_id,
        "blueFighterId": blue_id,
    }

    completed_careers = 0
    for corner, fighter_id in (("red", red_id), ("blue", blue_id)):
        detail_receipt, fighter_detail = call(
            "fighter_detail",
            f"/fighters/{fighter_id}",
            "object",
            fighter_id=fighter_id,
        )
        identity = _fighter_identity(fighter_detail, corner, fighter_id)
        if detail_receipt["classification"] == "data_success" and identity is None:
            detail_receipt = _replace_with_shape_failure(detail_receipt)
        packet["scenarios"].append(detail_receipt)
        if detail_receipt["classification"] != "data_success":
            return {"status": False, "data": packet}
        packet["fighters"].append(identity)

        stats_receipt, fighter_stats = call(
            "fighter_stats",
            f"/fighters/{fighter_id}",
            "object",
            base_url=_STATISTICS_API,
            fighter_id=fighter_id,
        )
        stats_summary = _fighter_statistics(fighter_stats, corner, fighter_id)
        if stats_receipt["classification"] == "data_success" and stats_summary is None:
            stats_receipt = _replace_with_shape_failure(stats_receipt)
        packet["scenarios"].append(stats_receipt)
        if stats_receipt["classification"] != "data_success":
            return {"status": False, "data": packet}
        packet["fighterStats"].append(stats_summary)

        career_receipt, _ = call(
            "fighter_career",
            f"/fighters/{fighter_id}/career",
            "object",
            base_url=_STATISTICS_API,
            fighter_id=fighter_id,
        )
        packet["scenarios"].append(career_receipt)
        if career_receipt["classification"] in {"failed", "unavailable"}:
            return {"status": False, "data": packet}
        completed_careers += 1

    coverage = packet["coverage"]
    for sampled_fight in sample:
        fight_id = sampled_fight["id"]
        summary_receipt, summary = call(
            "fight_summary",
            f"/fights/{fight_id}",
            "object",
            base_url=_STATISTICS_API,
            event_id=event_id if fight_id == selected_fight_id else None,
            fight_id=fight_id,
        )
        summary_value = None
        if summary_receipt["classification"] == "data_success":
            summary_value = _fight_statistics(summary, fight_id)
            if summary_value is None:
                summary_receipt = _replace_with_shape_failure(summary_receipt)
        packet["scenarios"].append(summary_receipt)
        _update_coverage(coverage["fightSummary"], summary_receipt["classification"])
        if fight_id == selected_fight_id and summary_value is not None:
            packet["fightStats"] = summary_value

        totals_receipt, _ = call(
            "fight_totals",
            f"/fights/{fight_id}/totals",
            "array",
            base_url=_STATISTICS_API,
            fight_id=fight_id,
        )
        packet["scenarios"].append(totals_receipt)
        _update_coverage(coverage["totals"], totals_receipt["classification"])

        rounds_receipt, _ = call(
            "fight_rounds",
            f"/fights/{fight_id}/rounds",
            "array",
            base_url=_STATISTICS_API,
            fight_id=fight_id,
        )
        packet["scenarios"].append(rounds_receipt)
        _update_coverage(coverage["rounds"], rounds_receipt["classification"])

        actions_receipt, _ = call(
            "fight_actions",
            "/actions",
            "actions",
            base_url=_STATISTICS_API,
            query={"fightNewId": fight_id},
            fight_id=fight_id,
            per_page=1,
        )
        packet["scenarios"].append(actions_receipt)
        _update_coverage(coverage["actions"], actions_receipt["classification"])

    round_receipt, _ = call(
        "fight_round_1",
        f"/fights/{selected_fight_id}/rounds/1",
        "array",
        base_url=_STATISTICS_API,
        fight_id=selected_fight_id,
    )
    packet["scenarios"].append(round_receipt)
    _finalize_coverage(coverage)

    no_failed_receipts = not any(
        receipt["classification"] == "failed" for receipt in packet["scenarios"]
    )
    full_path_executed = (
        packet["event"]["providerEventId"] == event_id
        and packet["fight"]["providerFightId"] == selected_fight_id
        and len(packet["fighters"]) == 2
        and len(packet["fighterStats"]) == 2
        and completed_careers == 2
        and coverage["fightSummary"]["dataSuccess"] >= 1
        and no_failed_receipts
    )
    packet["fullPathExecuted"] = full_path_executed
    packet["verdict"] = "passed" if full_path_executed else "failed"
    return {"status": full_path_executed, "data": packet}


def run_fantasy_scenarios(request_data: Any, *_, **__) -> dict:
    """Run a bounded Fantasy shape canary without returning provider payloads."""

    try:
        return _run_fantasy_scenarios(request_data)
    except Exception:
        packet = _empty_fantasy_packet()
        return _failed_fantasy(packet, "canary", "INTERNAL_ERROR")
