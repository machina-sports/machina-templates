import json
import pathlib
import sys

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures"
for sub in ("scripts", "connectors", "local"):
    sys.path.insert(0, str(ROOT / sub))


def load_dataset():
    """The prototype's round (23-26/10/2026, Série A) as the connector would return it."""
    return {
        "competition": {"id": "serie-a-brazil", "name": "Serie A Brazil"},
        "season_id": "serie-a-brazil-2026",
        "as_of": "2026-10-22",
        "events": json.loads((FIX / "round.json").read_text()),
        "results": sorted((e for e in json.loads((FIX / "schedule.json").read_text())["data"]["schedules"]
                           if e["status"] == "closed"), key=lambda e: e["start_time"]),
        "standings": json.loads((FIX / "standings.json").read_text())["data"]["standings"][0]["entries"],
    }


@pytest.fixture
def dataset():
    return load_dataset()


@pytest.fixture
def contract():
    return yaml.safe_load((ROOT / "contracts" / "football_preview.yml").read_text())


@pytest.fixture
def client():
    return yaml.safe_load((ROOT / "clients" / "demo-ptbr.yml").read_text())
