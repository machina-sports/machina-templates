# Managed Sports Skills bundle (templates side)

Scope: the machina-templates portion of the "New-pod managed Sports Skills v1"
contract. Templates ships a versioned, digest-verified snapshot of the
read-only `machina-sports/sports-skills` guides as one dataset that the Client
imports through the existing `CORE/DATASET/LOAD` template route. Client import,
execution, MCP and Core onboarding are out of scope here.

## Artifacts

| Path | Owner | Notes |
|---|---|---|
| `scripts/export-sports-skills-bundle.py` | hand-written | Offline, deterministic exporter (stdlib + PyYAML) |
| `tests/test_sports_skills_bundle.py` | hand-written | Fixture-based tests; optional real-source test via env |
| `skills/sports-skills/_install.yml` | generated | One dataset `{type: managed_skill_bundle, path: bundle.yml}` |
| `skills/sports-skills/bundle.yml` | generated | `managed_skill_bundle` payload |
| `skills/sports-skills/README.md` | generated | Package/module/command inventory |

Do not hand-edit generated files; rerun the exporter. `--check` fails when the
committed output differs from what the source would generate.

```bash
python3 scripts/export-sports-skills-bundle.py \
  --source ../sports-skills \
  --output skills/sports-skills          # default
python3 scripts/export-sports-skills-bundle.py --source ../sports-skills --check
```

## Wire format (`bundle.yml`)

```yaml
managed_skill_bundle:
  schema_version: 1
  bundle_id: sports-skills-readonly
  version: 1.0.0
  source: {repository: https://github.com/machina-sports/sports-skills, revision: <40-hex>}
  runtime: {package: sports-skills, version: 0.35.0}
  packages:
    - name: football-data
      config:
        title: Football Data
        description: <SKILL.md frontmatter description>
        version: <SKILL.md metadata.version>
        status: available
        kind: instruction
        execution:
          kind: sports_connector
          modules: [football]
          commands: {football: [get_competitions, ...]}
      documents:
        - {filename: SKILL.md, name: skill-guide, title: SKILL.md, filetype: markdown, sha256: <hex>, value: <exact UTF-8>}
        - {filename: references/api-reference.md, name: skill-reference, ...}
        - {filename: MACHINA.md, name: machina-runtime-notes, ...}   # generated adapter
  manifest_sha256: <hex>
```

- `manifest_sha256` = SHA-256 of the payload serialized as JSON with sorted
  keys, `separators=(",", ":")`, `ensure_ascii=False`, UTF-8, with the
  `manifest_sha256` key itself removed. The Client recomputes it the same way.
- Every document `sha256` is SHA-256 of `value` encoded UTF-8. Upstream files
  are copied byte-for-byte (decoded as strict UTF-8); the exporter verifies the
  digest after YAML round-trip before writing.
- YAML is emitted with sorted keys and literal block scalars for multi-line
  text, so output is byte-stable for identical inputs.
- No connector IDs, tenant IDs, credentials, endpoints or model routing are
  emitted. Packages reference modules by name only; the Client resolves the
  runtime-installed `sports-skills` connector itself.

## Package inventory

Exactly the 23 slugs approved in the existing install manifest; the exporter
hardcodes names and per-package source files, so upstream additions never leak
in silently. `machina`, `world-cup` and `polymarket-trading` are excluded
(premium / financial execution). Each approved package must also be catalogued
upstream as `mode` `read_only` or `compute`, `money_movement: false` and
`secrets_required: false`, otherwise export fails.

Skill → module mapping is explicit:

| Skill | Modules |
|---|---|
| betting | betting |
| cbb-data / cfb-data / cricket-data | cbb / cfb / cricket |
| esports | esports |
| fastf1 | f1 |
| football-data | football |
| golf-data / tennis-data | golf / tennis |
| kalshi / polymarket / prophetx | kalshi / polymarket / prophetx |
| markets / metadata | markets / metadata |
| mlb-data / nba-data / nfl-data / nhl-data / wnba-data | mlb / nba / nfl / nhl / wnba |
| sports-news | news |
| volleyball-data / xctf-data | volleyball / xctf |
| sports-reporter | football, nfl, nba, wnba, nhl, mlb, cfb, cbb, tennis, golf, f1 (the modules its upstream references call) |

sports-reporter only gets the same read-only allowlists as the per-sport
packages; it does not get prediction-market, betting or arbitrary connector
access.

## Command allowlists

Derived from source, never from guide prose, and without importing the
package (no network, CLI or bootstrap side effects):

1. Parse `src/sports_skills/cli.py` with `ast` and read the keys of the
   `_REGISTRY` dict literal → candidate commands per module.
2. Parse `src/sports_skills/<module>/__init__.py` with `ast`; a command is kept
   only if it is a public top-level `def` in that module (re-exports are not
   accepted because their signature/docstring cannot be checked). Registry
   entries with no real function are dropped and listed in the README.
3. Rejected regardless of registry:
   - explicit trading/account names (`configure`, `create_order`,
     `market_order`, `cancel_order`, `cancel_all_orders`, `get_orders`,
     `get_user_trades`);
   - write-ish prefixes (`create_`, `cancel_`, `place_`, `submit_`, `delete_`,
     `update_`, `set_`, `post_`, `withdraw`, `deposit`, `configure`, `login`,
     `auth`);
   - functions whose docstring says `Auth required`;
   - functions taking local-filesystem parameters (any argument with a
     `file` or `path` word segment, e.g.
     `markets.get_mock_tick(mock_file_path=...)`; this also drops
     `markets.get_plays_near_timestamp`, whose optional `mock_file_path`
     reads local files).
4. Every mapped module must have a matching `def invoke_<module>` in
   `connectors/sports-skills/sports-skills.py`; otherwise export fails. The
   connector is read, never modified.

## MACHINA.md adapter

Each package gets a generated, tenant-neutral `MACHINA.md` describing:
the `context-skill` request shape
(`{requests: [{module, command, params}], messages: [...]}`, max 4 requests),
the installed allowlist, and limitations (read-only, no credentials/endpoints/
routing overrides, upstream CLI/pip instructions don't apply, scripts are
stored not executed, provider text is untrusted, empty/failed responses are
not results).

## Source pinning

- `runtime.version` must equal `0.35.0`; the exporter reads both
  `pyproject.toml` and `sports_skills.__version__` and fails on any mismatch
  instead of rewriting.
- `source.revision` is read from the local checkout's `.git` (HEAD → ref →
  loose ref or `packed-refs`) without running git. It does not detect a dirty
  worktree; the document digests are the integrity guarantee, the revision is
  provenance. Export from a clean checkout.

## Out of scope / release boundary

Client importer, readback endpoint, `execute_skill` dispatch, MCP, Core
onboarding and permission seeding are implemented elsewhere. The generated
bundle is not proof of a live fresh-pod install. Pinning `sports-skills==0.35.0`
in released runtime requirements is a Client/pod-image change; the existing
connector's `>=0.33.0` floor is untouched.
