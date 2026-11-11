"""The combined ZeroClick import document: World Cup storefront + Market Link Snapshot.

docs/openapi-zeroclick-combined.json is the World Cup import source, unchanged,
plus the upstream `sports-market-link-snapshot/1` and `/2` contracts
(machina-client-api c9c8743a8a96dd3b70546b6d7537bd587bf6707c) bundled under
MarketLinkV1*/MarketLinkV2* component names. It is an import source awaiting
dashboard import, not a live listing.

The snapshot bodies built below are SYNTHETIC fixtures written by hand to
exercise the schemas. They are not observed, captured or production data.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

DOCS = Path(__file__).resolve().parents[1] / "docs"
SOURCE = json.loads((DOCS / "openapi-import-source.json").read_text(encoding="utf-8"))
COMBINED = json.loads((DOCS / "openapi-zeroclick-combined.json").read_text(encoding="utf-8"))

SNAPSHOT = "/markets/v1/link-snapshot"
UPSTREAM_SHA = "c9c8743a8a96dd3b70546b6d7537bd587bf6707c"
V1_RESPONSE = "#/components/schemas/MarketLinkV1SnapshotResponse"
V2_RESPONSE = "#/components/schemas/MarketLinkV2SnapshotResponse"
ANY_RESPONSE = "#/components/schemas/MarketLinkV2AnySnapshotResponse"
GET = COMBINED["paths"][SNAPSHOT]["get"]
POST = COMBINED["paths"][SNAPSHOT]["post"]


def _validate(schema, instance):
    full = dict(schema)
    full["components"] = COMBINED["components"]
    jsonschema.Draft202012Validator(full).validate(instance)


def _schema(code):
    return POST["responses"][code]["content"]["application/json"]["schema"]


def _resolve(ref):
    node = COMBINED
    for part in ref[2:].split("/"):
        node = node[part.replace("~1", "/").replace("~0", "~")]
    return node


def _refs(node):
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref":
                yield value
            else:
                yield from _refs(value)
    elif isinstance(node, list):
        for item in node:
            yield from _refs(item)


def test_world_cup_source_is_preserved():
    for path, item in SOURCE["paths"].items():
        assert COMBINED["paths"][path] == item, path
    for kind, entries in SOURCE["components"].items():
        for name, value in entries.items():
            assert COMBINED["components"][kind][name] == value, (kind, name)
    assert COMBINED["security"] == SOURCE["security"] == [{"payPerUse": []}]
    assert COMBINED["servers"] == SOURCE["servers"]
    assert COMBINED["servers"][0]["url"] == "https://api.machina.gg"
    assert COMBINED["openapi"] == SOURCE["openapi"]


def test_exactly_one_path_is_added():
    assert set(COMBINED["paths"]) - set(SOURCE["paths"]) == {SNAPSHOT}
    assert set(COMBINED["paths"][SNAPSHOT]) == {"get", "post"}


def test_added_components_are_namespaced():
    added = set(COMBINED["components"]["schemas"]) - set(SOURCE["components"]["schemas"])
    assert added and all(name.startswith(("MarketLinkV1", "MarketLinkV2")) for name in added)
    assert {"MarketLinkV1Coverage", "MarketLinkV2Coverage", "MarketLinkV2AnySnapshotResponse"} <= added
    assert set(COMBINED["components"]["securitySchemes"]) - set(SOURCE["components"]["securitySchemes"]) == {
        "zeroclickSignature"
    }


def test_every_ref_resolves_locally():
    refs = set(_refs(COMBINED))
    assert refs
    for ref in refs:
        assert ref.startswith("#/"), ref
        _resolve(ref)


def test_operation_ids_are_unique():
    # operationId is optional in OpenAPI; preserve World Cup operations without one.
    ids = [op["operationId"] for item in COMBINED["paths"].values() for op in item.values() if "operationId" in op]
    assert len(ids) == len(set(ids))
    assert {"getMarketLinkSnapshotDiscovery", "getMarketLinkSnapshot"} <= set(ids)


def test_every_component_schema_is_valid_draft_2020_12():
    for name, schema in COMBINED["components"]["schemas"].items():
        jsonschema.Draft202012Validator.check_schema(schema)


def test_every_embedded_example_validates():
    count = 0
    for path, item in COMBINED["paths"].items():
        for method, op in item.items():
            media = [("request", op.get("requestBody", {}).get("content", {}).get("application/json"))]
            media += [(code, r.get("content", {}).get("application/json")) for code, r in op["responses"].items()]
            for where, content in media:
                for name, example in ((content or {}).get("examples") or {}).items():
                    _validate(content["schema"], example["value"])
                    count += 1
    assert count


def test_snapshot_200_and_422_accept_two_strict_distinct_contracts():
    assert _schema("200") == {"$ref": ANY_RESPONSE}
    assert _schema("422") == {"$ref": ANY_RESPONSE}
    assert _resolve(ANY_RESPONSE) == {"oneOf": [{"$ref": V1_RESPONSE}, {"$ref": V2_RESPONSE}]}
    v1, v2 = _resolve(V1_RESPONSE), _resolve(V2_RESPONSE)
    assert v1["additionalProperties"] is False and v2["additionalProperties"] is False
    assert v1["properties"]["contract"] == {"const": "sports-market-link-snapshot/1"}
    assert v2["properties"]["contract"] == {"const": "sports-market-link-snapshot/2"}
    assert POST["x-machina-contract-version"] == ["sports-market-link-snapshot/1", "sports-market-link-snapshot/2"]
    assert "the buyer does not choose it" in POST["description"]


def test_post_keeps_every_v1_response_header_and_billing_rule():
    assert set(POST["responses"]) == {"200", "400", "401", "402", "404", "409", "422", "429", "503"}
    headers = POST["responses"]["200"]["headers"]
    assert set(headers) == {"zc-usage", "zc-replay"}
    assert headers["zc-replay"]["schema"] == {"const": "1"}
    assert POST["responses"]["429"]["headers"]["Retry-After"]["schema"] == {"type": "integer", "minimum": 1}
    for phrase in ("`billable: true`", "600 s", "`zc-replay: 1`", "Provider settlement idempotency remains unverified"):
        assert phrase in POST["description"], phrase
    for code in ("400", "404"):
        assert _schema(code) == {"$ref": V1_RESPONSE}, code


def test_get_is_anonymous_and_post_is_zeroclick_signed():
    assert GET["security"] == []
    assert POST["security"] == [{"zeroclickSignature": []}]
    scheme = COMBINED["components"]["securitySchemes"]["zeroclickSignature"]
    assert (scheme["type"], scheme["in"], scheme["name"]) == ("apiKey", "header", "zc-signature")
    assert "verified by the seller SDK over the raw request" in scheme["description"]
    assert "Presence alone grants nothing" in scheme["description"]
    assert "buyers never hold, supply or use a seller signing secret" in scheme["description"]


def test_discovery_uses_the_v2_schema():
    schema = GET["responses"]["200"]["content"]["application/json"]["schema"]
    assert schema == {"$ref": "#/components/schemas/MarketLinkV2Discovery"}


def test_world_cup_is_enveloped_and_snapshot_is_unwrapped():
    contract = COMBINED["x-transport-contract"]
    assert contract.startswith("Scope: WORLD CUP paths (/world-cup/v1/*) ONLY.")
    assert SOURCE["x-transport-contract"] in contract
    assert "NOT wrapped" in contract
    for path in SOURCE["paths"]:
        assert COMBINED["paths"][path]["post"]["responses"]["200"]["content"]["application/json"]["schema"][
            "required"
        ] == ["status", "data", "meta"], path
    for ref in (V1_RESPONSE, V2_RESPONSE):
        assert not {"data", "meta"} & set(_resolve(ref)["properties"]), ref


def test_request_url_docs_accept_polymarket_ucl():
    media = POST["requestBody"]["content"]["application/json"]
    for text in (media["schema"]["description"], POST["requestBody"]["description"]):
        assert "https://polymarket.com/sports/ucl/<slug>" in text
        assert "https://polymarket.com/event/<slug>" in text
        assert "https://kalshi.com/markets/" in text
    assert {"polymarket", "polymarket_ucl", "kalshi_ucl"} <= set(media["examples"])
    for example in media["examples"].values():
        _validate(media["schema"], example["value"])


def test_publication_is_an_import_source_not_a_live_listing():
    publication = COMBINED["x-publication"]
    assert publication["status"] == "import_source_awaiting_dashboard_import"
    assert publication["live"] is False
    assert publication["sources"]["market_link_snapshot"]["commit"] == UPSTREAM_SHA
    assert "404" in publication["upstream_blocker"]
    assert COMBINED["info"]["version"] == "1.6.0"
    assert "Combined" in COMBINED["info"]["title"]
    dumped = json.dumps(COMBINED)
    for local in ("/Users/", ".hermes", "market-link-snapshot-v1.yaml#"):
        assert local not in dumped, local


# --- SYNTHETIC fixtures (hand-written, never observed data) ---------------------


def _synthetic_side(team, probability=0.5):
    quote = {
        "venue": "polymarket",
        "implied_probability": probability,
        "price_basis": "reference",
        "execution_guaranteed": False,
        "observed_at": "2000-01-01T00:00:00Z",
    }
    return {"team": team, "quotes": [quote], "lowest_reference": quote}


def _synthetic_v1_ok():
    return {
        "contract": "sports-market-link-snapshot/1",
        "service": "market-link-snapshot",
        "request": {"url": "https://polymarket.com/event/synthetic-game"},
        "observed_at": "2000-01-01T00:00:00Z",
        "billable": True,
        "status": "ok",
        "event": {"espn_event_id": "0", "sport": "nba", "home_team": "Synthetic Home",
                  "away_team": "Synthetic Away", "start_time": None},
        "source_market": {"venue": "polymarket"},
        "reference_prices": {"home": _synthetic_side("Synthetic Home"), "away": _synthetic_side("Synthetic Away")},
        "coverage": {"usable_sources": ["polymarket"], "attempted_sources": ["polymarket"], "missing": [],
                     "complete": True},
        "price_basis": "reference",
        "execution_guaranteed": False,
        "limitations": ["full_game_moneyline_only", "reference_prices_not_executable"],
        "warnings": [],
        "error": None,
    }


def _synthetic_v2_ok():
    document = _synthetic_v1_ok()
    document.update(
        contract="sports-market-link-snapshot/2",
        request={"url": "https://polymarket.com/sports/ucl/synthetic-game"},
        market_type="three_way_moneyline",
        settlement_period="regulation",
        source_market={"market_type": "three_way_moneyline", "settlement_period": "regulation",
                       "sport": "ucl", "espn_event_id": "0"},
        limitations=["regulation_three_way_moneyline_only", "reference_prices_not_executable"],
    )
    document["event"]["sport"] = "ucl"
    document["reference_prices"]["draw"] = _synthetic_side(None, 0.25)
    return document


def _synthetic_v1_error(code):
    document = _synthetic_v1_ok()
    document.update(billable=False, status="error", event=None, source_market=None, reference_prices=None,
                    coverage=None, limitations=[], error={"code": code, "kind": None, "detail": None})
    return document


def _synthetic_v2_no_usable_prices():
    document = _synthetic_v2_ok()
    empty = {"team": None, "quotes": [], "lowest_reference": None}
    document.update(billable=False, status="error", reference_prices={"home": empty, "away": empty, "draw": empty},
                    error={"code": "no_usable_prices", "kind": None, "detail": None})
    return document


def test_synthetic_v1_and_v2_successes_validate_on_200():
    _validate(_schema("200"), _synthetic_v1_ok())
    _validate(_schema("200"), _synthetic_v2_ok())


def test_synthetic_v1_with_a_draw_is_rejected():
    document = _synthetic_v1_ok()
    document["reference_prices"]["draw"] = _synthetic_side(None, 0.25)
    with pytest.raises(jsonschema.ValidationError):
        _validate(_schema("200"), document)


def test_synthetic_v2_without_a_draw_is_rejected():
    document = _synthetic_v2_ok()
    del document["reference_prices"]["draw"]
    with pytest.raises(jsonschema.ValidationError):
        _validate(_schema("200"), document)


def test_synthetic_error_documents_validate():
    _validate(_schema("400"), _synthetic_v1_error("unsupported_url"))
    _validate(_schema("404"), _synthetic_v1_error("market_not_found"))
    _validate(_schema("422"), _synthetic_v1_error("game_not_matched"))
    _validate(_schema("422"), _synthetic_v2_no_usable_prices())
    _validate(_schema("503"), {**_synthetic_v1_error("provider_unavailable"),
                               "error": {"code": "provider_unavailable", "kind": "timeout", "detail": None}})
    _validate(_schema("401"), {"error": "zeroclick_signature_required", "discovery": SNAPSHOT})
    _validate(_schema("402"), {"error": "payment_required", "challenge": "synthetic"})
    _validate(_schema("409"), {"error": "request_id_reused"})
    _validate(_schema("429"), {"error": "rate_limited"})
    _validate(_schema("503"), {"error": "zeroclick_dedup_unavailable"})
    with pytest.raises(jsonschema.ValidationError):
        _validate(_schema("400"), _synthetic_v2_no_usable_prices())
