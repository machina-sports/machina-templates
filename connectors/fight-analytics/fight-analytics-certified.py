"""Credential-safe Fight Analytics contract smoke connector."""

from __future__ import annotations

from typing import Any

import requests


_AUTH_API = "https://auth-api.fightanalytics.cc"
_METADATA_API = "https://api.fightanalytics.cc"
_STATISTICS_API = "https://mike-goldberg-v2.fightanalytics.cc"
_TIMEOUT = (5, 30)
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
    accepted_statuses: set[int] | None = None,
) -> tuple[dict, Any, bool]:
    headers = {"Accept": "application/json"}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    if method == "GET" and path in {
        "/promotions", "/venues", "/teams", "/events", "/fighters",
        "/fights", "/actions",
    }:
        headers["per_page"] = "1"

    try:
        response = requests.request(
            method,
            f"{base_url}{path}",
            headers=headers,
            json=body,
            timeout=_TIMEOUT,
        )
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
    if not isinstance(refreshed_access_token, str) or not refreshed_access_token:
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
