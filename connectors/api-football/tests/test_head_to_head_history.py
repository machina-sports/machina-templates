"""A fixture cannot be its own historical evidence in either dual-write family."""
from copy import deepcopy

from test_event_data_projection import load_payload, project


def test_selected_fixture_is_excluded_from_both_history_families():
    payload = load_payload()
    history = payload["head_to_head"]
    history["response"].insert(0, deepcopy(payload["fixture"]))
    history["results"] = len(history["response"])
    result = project(payload)["data"]
    legacy = next(doc for doc in result["documents"] if doc["name"].endswith("head-to-head"))
    canonical = next(doc for doc in result["evidence_documents"] if doc["value"]["kind"] == "head_to_head")
    assert len(legacy["value"]["facts"]) == len(history["response"]) - 1
    assert all(str(fact["provider_fixture_id"]) != "7001" for fact in legacy["value"]["facts"])
    assert all(str(fact["provider_evidence"]["event_id"]) != "7001" for fact in canonical["value"]["facts"])


def test_only_selected_fixture_means_no_prior_meetings_not_a_self_match():
    payload = load_payload()
    payload["head_to_head"]["response"] = [deepcopy(payload["fixture"])]
    payload["head_to_head"]["results"] = 1
    result = project(payload)["data"]
    canonical = next(doc for doc in result["evidence_documents"] if doc["value"]["kind"] == "head_to_head")
    assert canonical["value"]["status"] == "unavailable"
    assert canonical["value"]["facts"] == []
    assert "prior meetings" in canonical["value"]["unavailable_reason"]
