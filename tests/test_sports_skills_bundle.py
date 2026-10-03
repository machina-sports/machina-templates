"""Offline tests for scripts/export-sports-skills-bundle.py.

Uses a temporary fixture checkout. Set SPORTS_SKILLS_SOURCE to a local
sports-skills checkout to also exercise the real upstream source.
"""

import hashlib
import importlib.util
import json
import os
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "export-sports-skills-bundle.py"

_spec = importlib.util.spec_from_file_location("export_sports_skills_bundle", SCRIPT)
exporter = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(exporter)

REVISION = "0123456789abcdef0123456789abcdef01234567"
ALL_MODULES = sorted({m for mods, _ in exporter.PACKAGES.values() for m in mods})

# Fixture module source: (command, signature, docstring). Commands listed in
# EXTRA_REGISTRY are registered in cli.py but deliberately have no function.
SPECIAL_FUNCTIONS = {
    "polymarket": [
        ("get_sports_markets", "*, limit: int = 50", "Read markets."),
        ("create_order", "*, token_id: str, side: str", "Place a limit order."),
        ("get_orders", "*, market=None", "View open orders. Auth required: configure wallet credentials."),
        ("configure", "*, private_key=None", "Configure wallet."),
    ],
    "markets": [
        ("get_todays_markets", "*, sport=None", "Today's markets."),
        ("get_mock_tick", "*, mock_file_path: str", "Replay a local file."),
        ("get_market_profile", "*, profile: str", "Profile is not a file path."),
    ],
}
EXTRA_REGISTRY = {"football": ["ghost_command"]}


def _functions(module):
    return SPECIAL_FUNCTIONS.get(module, [("get_scoreboard", "*, date=None", "Scoreboard.")])


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def _skill_md(name):
    return (
        f"---\nname: {name}\ndescription: |\n  Read-only {name} guide.\nlicense: MIT\n"
        f'metadata:\n  author: machina-sports\n  version: "0.1.0"\n---\n\n# {name}\n\nUse `get_scoreboard`.\n'
    )


def make_source(root):
    _write(root / "pyproject.toml", '[project]\nname = "sports-skills"\nversion = "0.35.0"\n')
    _write(root / "src/sports_skills/__init__.py", '"""SDK."""\n\n__version__ = "0.35.0"\n')
    registry = {}
    for module in ALL_MODULES:
        registry[module] = {c: {} for c, _, _ in _functions(module)}
        registry[module].update({c: {} for c in EXTRA_REGISTRY.get(module, [])})
        body = "import network_client_that_must_not_be_imported\n\n\ndef _private():\n    return 1\n"
        for command, signature, doc in _functions(module):
            body += f'\n\ndef {command}({signature}) -> dict:\n    """{doc}"""\n    return {{}}\n'
        _write(root / f"src/sports_skills/{module}/__init__.py", body)
    _write(
        root / "src/sports_skills/cli.py",
        "import sys\n\n_SHAPING = ['limit']\n\n_REGISTRY = " + repr(registry) + "\n",
    )

    catalog = {}
    for name, (_, files) in exporter.PACKAGES.items():
        mode = "compute" if name == "betting" else "read_only"
        catalog[name] = {"mode": mode, "money_movement": False, "secrets_required": False}
        for filename in files:
            if filename == "SKILL.md":
                text = _skill_md(name)
            else:
                # Exercise exact-byte preservation: unicode, CRLF, trailing spaces, tabs.
                text = f"# {name} {filename} — ç\r\nline with trailing space \n\tindented\n"
            _write(root / "skills" / name / filename, text)
    catalog["polymarket-trading"] = {"mode": "financial_execution", "money_movement": True, "secrets_required": True}
    _write(root / "skills/polymarket-trading/SKILL.md", _skill_md("polymarket-trading"))
    _write(root / "skills/catalog.json", json.dumps({"skills": catalog, "version": 1}))

    _write(root / ".git/HEAD", "ref: refs/heads/main\n")
    _write(root / ".git/packed-refs", f"# pack-refs with: peeled\n{REVISION} refs/heads/main\n")
    return root


@pytest.fixture
def source(tmp_path):
    return make_source(tmp_path / "sports-skills")


def build(source, connector=exporter.DEFAULT_CONNECTOR):
    return exporter.build_payload(source, connector)


def test_exact_inventory_and_byte_identical_documents(source):
    payload, _ = build(source)

    assert payload["schema_version"] == 1
    assert payload["bundle_id"] == "sports-skills-readonly"
    assert payload["version"] == "1.0.0"
    assert payload["runtime"] == {"package": "sports-skills", "version": "0.35.0"}
    assert payload["source"] == {"repository": "https://github.com/machina-sports/sports-skills", "revision": REVISION}

    names = [p["name"] for p in payload["packages"]]
    assert len(names) == 23 and names == sorted(exporter.PACKAGES)
    assert not set(names) & {"machina", "world-cup", "polymarket-trading"}

    for package in payload["packages"]:
        _, files = exporter.PACKAGES[package["name"]]
        filenames = [d["filename"] for d in package["documents"]]
        assert filenames == files + ["MACHINA.md"]
        for doc in package["documents"]:
            assert doc["sha256"] == hashlib.sha256(doc["value"].encode("utf-8")).hexdigest()
            if doc["filename"] != "MACHINA.md":
                upstream = (source / "skills" / package["name"] / doc["filename"]).read_bytes()
                assert doc["value"].encode("utf-8") == upstream
        assert package["config"]["kind"] == "instruction"
        assert package["config"]["status"] == "available"
        assert package["config"]["version"] == "0.1.0"
        assert package["config"]["description"] == f"Read-only {package['name']} guide."


def test_rendered_bundle_is_deterministic_and_round_trips(source):
    first = exporter.render(*build(source))
    second = exporter.render(*build(source))
    assert first == second

    install = yaml.safe_load(first["_install.yml"])
    assert install["datasets"] == [{"type": "managed_skill_bundle", "path": "bundle.yml"}]

    payload = yaml.safe_load(first["bundle.yml"])["managed_skill_bundle"]
    body = {k: v for k, v in payload.items() if k != "manifest_sha256"}
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    assert payload["manifest_sha256"] == hashlib.sha256(canonical).hexdigest()
    ref = next(p for p in payload["packages"] if p["name"] == "nba-data")["documents"][1]
    assert "\r\n" in ref["value"] and "trailing space \n" in ref["value"]


def test_manifest_hash_changes_with_source_content(source):
    before, _ = build(source)
    _write(source / "skills/nba-data/references/team-ids.md", "changed\n")
    after, _ = build(source)
    assert before["manifest_sha256"] != after["manifest_sha256"]


def test_allowlists_exclude_trading_auth_filesystem_and_invented_commands(source):
    payload, dropped = build(source)
    commands = {}
    for package in payload["packages"]:
        commands.update(package["config"]["execution"]["commands"])

    assert commands["polymarket"] == ["get_sports_markets"]
    assert commands["markets"] == ["get_market_profile", "get_todays_markets"]
    assert commands["football"] == ["get_scoreboard"]
    assert "football.ghost_command: no public function in module source" in dropped
    assert "polymarket.create_order: trading/write command" in dropped
    assert "polymarket.get_orders: trading/write command" in dropped
    assert "markets.get_mock_tick: takes a local filesystem path" in dropped
    assert not any(c.startswith("_") for cmds in commands.values() for c in cmds)


def test_auth_required_docstring_is_rejected_even_for_read_names(source):
    path = source / "src/sports_skills/kalshi/__init__.py"
    _write(path, path.read_text() + '\n\ndef get_balance() -> dict:\n    """Auth required."""\n    return {}\n')
    cli = source / "src/sports_skills/cli.py"
    _write(cli, cli.read_text().replace("'kalshi': {", "'kalshi': {'get_balance': {}, "))
    _, dropped = build(source)
    assert "kalshi.get_balance: requires account auth" in dropped


def test_reporter_shares_only_read_only_sport_modules(source):
    payload, _ = build(source)
    reporter = next(p for p in payload["packages"] if p["name"] == "sports-reporter")
    modules = reporter["config"]["execution"]["modules"]
    assert set(modules) == set(reporter["config"]["execution"]["commands"])
    assert not set(modules) & {"polymarket", "kalshi", "prophetx", "markets", "betting"}


def test_machina_notes_are_generic_and_describe_context_skill(source):
    payload, _ = build(source)
    for package in payload["packages"]:
        notes = package["documents"][-1]
        assert notes["name"] == "machina-runtime-notes"
        assert "context-skill" in notes["value"] and "At most 4 requests" in notes["value"]
        for module, cmds in package["config"]["execution"]["commands"].items():
            assert f"`{module}`: " + ", ".join(f"`{c}`" for c in cmds) in notes["value"]
        assert "Fantasy" not in notes["value"]


def test_no_tenant_ids_or_credentials_in_config(source):
    payload, _ = build(source)
    text = exporter.render(payload, [])["bundle.yml"]
    for forbidden in ("connector_id", "credential", "api_key", "Fantasy", "6a35cbfb5099d82da81f24b2"):
        assert forbidden not in text
    for package in payload["packages"]:
        assert set(package["config"]) == {"title", "description", "version", "status", "kind", "execution"}
        assert set(package["config"]["execution"]) == {"kind", "modules", "commands"}
        for doc in package["documents"]:
            assert set(doc) == {"filename", "name", "title", "filetype", "value", "sha256"}


@pytest.mark.parametrize("target", ["pyproject.toml", "src/sports_skills/__init__.py"])
def test_version_mismatch_is_reported_not_rewritten(source, target):
    path = source / target
    original = path.read_text().replace("0.35.0", "0.34.0")
    _write(path, original)
    with pytest.raises(exporter.ExportError, match=r"expected 0\.35\.0.*0\.34\.0"):
        build(source)
    assert path.read_text() == original


def test_missing_approved_file_fails(source):
    (source / "skills/kalshi/references/series-tickers.md").unlink()
    with pytest.raises(exporter.ExportError, match="series-tickers.md"):
        build(source)


def test_non_utf8_source_fails(source):
    (source / "skills/golf-data/references/majors.md").write_bytes(b"\xff\xfe bad")
    with pytest.raises(exporter.ExportError, match="UTF-8"):
        build(source)


def test_high_risk_catalog_entry_fails(source):
    catalog_path = source / "skills/catalog.json"
    catalog = json.loads(catalog_path.read_text())
    catalog["skills"]["kalshi"]["mode"] = "financial_execution"
    _write(catalog_path, json.dumps(catalog))
    with pytest.raises(exporter.ExportError, match="kalshi"):
        build(source)


def test_frontmatter_name_mismatch_fails(source):
    _write(source / "skills/esports/SKILL.md", _skill_md("not-esports"))
    with pytest.raises(exporter.ExportError, match="esports/SKILL.md"):
        build(source)


def test_module_without_connector_invoke_fails(source, tmp_path):
    connector = tmp_path / "connector.py"
    text = exporter.DEFAULT_CONNECTOR.read_text().replace("def invoke_prophetx(", "def removed_prophetx(")
    _write(connector, text)
    with pytest.raises(exporter.ExportError, match="invoke_prophetx"):
        build(source, connector)


def test_real_connector_supports_every_mapped_module():
    invokable = exporter.connector_invoke_modules(exporter.DEFAULT_CONNECTOR)
    assert set(ALL_MODULES) <= invokable


def test_revision_from_loose_ref_and_detached_head(source):
    other = "f" * 40
    _write(source / ".git/refs/heads/main", other + "\n")
    assert exporter.read_source_revision(source) == other
    _write(source / ".git/HEAD", REVISION + "\n")
    assert exporter.read_source_revision(source) == REVISION
    _write(source / ".git/HEAD", "not-a-sha\n")
    with pytest.raises(exporter.ExportError, match="invalid source revision"):
        exporter.read_source_revision(source)


def test_main_writes_and_check_detects_drift(source, tmp_path):
    out = tmp_path / "out"
    assert exporter.main(["--source", str(source), "--output", str(out)]) == 0
    assert sorted(p.name for p in out.iterdir()) == ["README.md", "_install.yml", "bundle.yml"]
    assert exporter.main(["--source", str(source), "--output", str(out), "--check"]) == 0

    _write(source / "skills/betting/references/api-reference.md", "upstream changed\n")
    assert exporter.main(["--source", str(source), "--output", str(out), "--check"]) == 1


def test_main_reports_errors_without_writing(source, tmp_path):
    (source / "skills/catalog.json").unlink()
    out = tmp_path / "out"
    assert exporter.main(["--source", str(source), "--output", str(out)]) == 2
    assert not out.exists()


@pytest.mark.skipif(not os.environ.get("SPORTS_SKILLS_SOURCE"), reason="set SPORTS_SKILLS_SOURCE to a local checkout")
def test_real_upstream_source():
    payload, dropped = build(Path(os.environ["SPORTS_SKILLS_SOURCE"]))
    files = exporter.render(payload, dropped)
    assert len(payload["packages"]) == 23
    assert payload["runtime"]["version"] == "0.35.0"
    commands = {}
    for package in payload["packages"]:
        commands.update(package["config"]["execution"]["commands"])
    assert set(commands) == set(ALL_MODULES)
    for denied in ("create_order", "market_order", "cancel_order", "cancel_all_orders", "get_orders", "configure"):
        assert denied not in commands["polymarket"]
    assert "get_mock_tick" not in commands["markets"]
    assert "get_plays_near_timestamp" not in commands["markets"]
    assert "prophetx" in commands
    assert yaml.safe_load(files["bundle.yml"])["managed_skill_bundle"] == payload
