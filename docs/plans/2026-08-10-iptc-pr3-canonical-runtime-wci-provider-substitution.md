# IPTC PR 3 Canonical Runtime and WCI Provider Substitution Implementation Plan
> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.
**Goal:** Publish and install the canonical Python runtime, then prove World Cup Intelligence provider substitution without provider branches above the seam.
**Architecture:** `machina-templates` remains source authority. A pinned `machina-sports-canonical` wheel maps import namespace `machina_sports_canonical` to existing `tools/iptc/canonical` bytes without copying/moving logic. `machina-client-api` installs it; a thin shared pyscript connector imports it; WCI persists the canonical envelope plus exact-path derived compatibility aliases under the unchanged `worldcup:event` name.
**Tech Stack:** Python 3.9+/3.11, stdlib-only canonical core, setuptools/build, pytest/unittest, Machina pyscript connectors/YAML workflows, Docker.

---

## Authority and scope

The full approved architecture is held in the **internal architecture decision record (revision B)** that governs this work; treat that record as authority. Where this plan and that record disagree, the record wins and this plan is amended before implementation continues.

This plan contains **17 tasks** across four physical PRs (PR3-A .. PR3-D) plus a stop/review gate. Every task is **strict TDD**: the RED test is written and observed failing for the stated reason before any implementation line is written. A task is not complete until its GREEN commands pass and its commit is made.

### Current package/runtime evidence

These facts constrain the design and must not be re-litigated during implementation:

- The `machina-client-api` template importer stores **one pyscript sidecar** per connector.
- `core.connector.executor.connector_script` **execs that sidecar in-process** (same interpreter, same site-packages).
- Therefore any `import machina_sports_canonical` inside a pyscript **requires the wheel to be installed in the image** — there is no per-template dependency install, no vendoring hook, and no sys.path injection at execution time.
- **Production** images build from the **root `requirements.txt`**.
- **Development** images build from **`docker/development/requirements.txt`**.
- `requirements.prod.txt` is **not referenced** by either dockerfile and must not be touched.
- PyPI name `machina-sports-canonical` returned **404/unclaimed on 2026-08-10**. Unclaimed is not owned. Ownership only exists after a successful release upload; any task depending on the installed distribution is blocked until then.

### Global conventions

- Repo root for PR3-A / PR3-B / PR3-D: this `machina-templates` repository.
- Repo root for PR3-C: the sibling `machina-client-api` repository.
- All paths below are repository-relative; cross-repository paths are prefixed with the repository name.
- Test runner: `python3 -m tools.iptc.run_test_suites` is the manifest runner; individual suites run with `python3 -m pytest <path> -q` (fallback `python3 -m unittest <dotted.path> -v` if the suite is unittest-shaped).
- **No consumer behavior changes in PR3-A or PR3-B.** Behavior changes start in PR3-D.
- **External approval gates** (tasks 5, 8, 16) are hard stops. The implementing agent must stop and report; it must not self-approve, publish, deploy, or import to sandbox.

---

# PR3-A — Architecture/inventory hardening (current `machina-templates` branch)

Branch: `refactor/iptc-consumers-and-compatibility` (existing). The branch was opened at
inventory commit `d38baeb`; the reviewed plan commit `02fe533` sits on top of it, so the
branch tip is not `d38baeb` and no task should assert that it is.
No consumers are modified in this PR. Only inventory tooling, review ledger, and regenerated artifacts.

---

## Task 1 — Document-name and storage-predicate detection in the inventory tool

**Prerequisite:** On `refactor/iptc-consumers-and-compatibility`, with inventory commit `d38baeb` present and the reviewed plan commit `02fe533` applied on top of it — `02fe533` is the base this task builds on, not `d38baeb`. Working tree clean apart from ignored `.claude/tasks/CURRENT.md`.

**Objective:** Teach `tools/iptc/inventory.py` to detect two coupling classes the current scan misses: (a) **document-name coupling** — literal document names such as `worldcup:event` used in save/load/query positions; (b) **storage-predicate coupling** — filter/sorter/query paths such as `value.schema:startDate` and `value.sport:status` that bind a consumer to the persisted document shape. Detection must be evidence-bearing: each hit records file, line, matched literal, and coupling category.

**Create:**
- `tests/test_iptc_consumer_inventory.py`

**Modify:**
- `tools/iptc/inventory.py`
- `tools/iptc/test-suites.json` — **mechanically required, not discretionary.** `tests/test_iptc_test_manifest.py` asserts exact set equality between the manifest and the `tests/test_iptc_*.py` files on disk, so creating the new suite without registering it fails the manifest gate and `run_test_suites` refuses to start. Register the new suite in its existing group at its sorted position; touch no other manifest field.

**Test paths:**
- `tests/test_iptc_consumer_inventory.py`
- Fixtures inline in the test module (no new fixture tree in this task).

**RED test + command + expected failure:**

Write `tests/test_iptc_consumer_inventory.py` with at minimum these cases:
1. `test_detects_document_name_coupling` — a synthetic YAML snippet containing `name: worldcup:event` in a save/load task yields a finding with `category == "document-name"` and `literal == "worldcup:event"`.
2. `test_detects_storage_predicate_startdate` — a snippet containing `value.schema:startDate` in a filter/sorter yields `category == "storage-predicate"` and `path == "value.schema:startDate"`.
3. `test_detects_storage_predicate_status` — same for `value.sport:status`.
4. `test_findings_carry_file_and_line_evidence` — every finding has non-empty `file` and integer `line >= 1`.
5. `test_real_repo_scan_detects_worldcup_event_couplings` — a real-repo scan returns findings at their **verified** locations, which are two different trees:
   - at least one `document-name` finding for the literal `worldcup:event` from `agent-templates/world-cup-intelligence/`;
   - at least one `storage-predicate` finding for the exact path `value.schema:startDate` **and** at least one for the exact path `value.sport:status`, both from the real `connectors/` tree — `connectors/sportradar-soccer/` and `connectors/stats-perform/` are the confirmed carriers of both paths.
6. `test_the_storage_predicates_are_absent_from_wci_and_present_in_connectors` — a separate guard asserting the inverse: scanning `agent-templates/world-cup-intelligence/` alone yields **zero** `storage-predicate` findings for either exact path, while the connectors scan yields both. WCI filters on `name`, `value._id`, `value.@type`, `value.event_urn`, `value.subject_urn`, `value.status` and `value.ts`; it reads `schema:startDate` and `sport:status` in Python off an already-loaded document, which is not a storage predicate. This guard exists so that a later change moving a predicate into WCI fails loudly, and so that case 5 can never be made to pass by broadening the matcher — matching a bare `sport:status` or `schema:startDate` anywhere in a file is the forbidden false-positive matcher and must not be used to manufacture a WCI hit.

Command:
```
python3 -m pytest tests/test_iptc_consumer_inventory.py -q
```

Expected failure (RED): `ImportError`/`AttributeError` for the not-yet-existing detection entrypoint (e.g. `cannot import name 'scan_couplings' from 'tools.iptc.inventory'`), or assertion failures showing zero findings of category `document-name` / `storage-predicate`. Record the exact failure text in the commit body.

**Minimal implementation API:**

In `tools/iptc/inventory.py`, add only:
```python
COUPLING_DOCUMENT_NAME = "document-name"
COUPLING_STORAGE_PREDICATE = "storage-predicate"

def scan_couplings(root: str) -> list[dict]:
    """Return findings: {file, line, category, literal|path, snippet}."""
```
plus the two narrow matchers it needs. Wire `scan_couplings` into the existing inventory generation so its findings land in the generated inventory under an added **top-level** `couplings` key — a sibling of the existing top-level keys, appended after them. Every pre-existing top-level key must survive unchanged, with its existing position preserved; a test pins that key set and its order. Do **not** restructure the existing scanner, rename existing fields, or change existing output ordering beyond appending the one additive key.

**GREEN commands:**
- Focused: `python3 -m pytest tests/test_iptc_consumer_inventory.py -q`
- Full: `python3 -m tools.iptc.run_test_suites`

**Commit message:** `test(iptc): detect document-name and storage-predicate couplings`

**Rollback / stop condition:** If wiring `couplings` into generation changes any pre-existing top-level key of `inventory.json` — its presence, its value or its position — other than appending the additive `couplings` key, revert the wiring, keep `scan_couplings` standalone, and record the deviation in the commit body.

Stop and report if case 5 cannot pass **against its corrected evidence roots**: the `document-name` finding from `agent-templates/world-cup-intelligence/`, and both exact `value.*` `storage-predicate` findings from the real `connectors/` tree. Do not relocate an assertion to a root the evidence does not support, and do not loosen matchers to substring-anywhere matching to force a hit — a matcher that fires inside prose, docstrings, `description:` fields or commented-out tasks is a false-positive generator and must not ship.

### ⚠️ Task 1 evidence amendment / implementation deviation

The approved spec asserted that both `value.schema:startDate` and `value.sport:status` storage-predicate couplings exist inside `agent-templates/world-cup-intelligence`. Verified repository evidence says otherwise: WCI carries `worldcup:event` document-name couplings, but neither of those two exact `value.*` paths. They live in the provider connector trees, principally `connectors/sportradar-soccer/` and `connectors/stats-perform/`. **The code candidate remains `9f563a0`; no code change was required** — it already used narrow, context-aware matchers and already pinned the WCI absence with its own test, so the plan was wrong and the code was right. Two consequences carry forward and must be honoured downstream: **Task 2** must assign owners and dispositions for those provider connector consumers, not treat WCI as the coupled party; and **Task 12** cannot reason about alias closure from WCI alone, because the readers that filter on the persisted storage shape are those connector workflows.

**Recorded history:** candidate commit `9f563a0` triggered this correction. It ran against the earlier version of case 5, which asserted all three findings inside `agent-templates/world-cup-intelligence/`; the repository evidence contradicted that premise. The plan has been amended to the verified roots above. The prohibition on broad matching is unchanged and still absolute — broadening was, and remains, the wrong way to satisfy the old assertion.

---

## Task 2 — Consumer review ledger and regenerated inventory

**Prerequisite:** Task 1 committed and green.

**Objective:** Create a durable, machine-checkable review ledger for every generated dependency, and regenerate the inventory artifacts so ledger and inventory agree. Every generated dependency must be either **reviewed** (with a disposition and evidence) or **explicitly excluded** (with a stated reason). The final unreviewed count must be **zero**. No consumer files change.

**Create:**
- `docs/iptc/consumer-review.json`

**Modify (regenerated artifacts only):**
- `docs/iptc/INVENTORY.md`
- `docs/iptc/inventory.json`

**Test paths:**
- `tests/test_iptc_consumer_inventory.py` (extend; do not create a second suite)

**RED test + command + expected failure:**

Add to `tests/test_iptc_consumer_inventory.py`:
1. `test_review_ledger_exists_and_has_schema_and_version` — file loads as JSON, has `schema` (string identifier) and `version` (string).
2. `test_every_entry_has_required_fields` — each entry has `repo`, `path`, `category`, `owner`, `disposition`, `evidence`; `disposition` ∈ {`migrate`, `compat-alias`, `no-change`, `excluded`}; `evidence` non-empty.
3. `test_every_generated_dependency_is_reviewed_or_excluded` — the set of `(repo, path)` from `docs/iptc/inventory.json` is a subset of the ledger's `(repo, path)` set.
4. `test_unreviewed_count_is_zero` — computed unreviewed count == 0.
5. `test_no_orphan_ledger_entries` — every ledger entry with `disposition != "excluded"` corresponds to a real generated dependency (guards against a ledger that drifts ahead of reality).

Command:
```
python3 -m pytest tests/test_iptc_consumer_inventory.py -q
```

Expected failure (RED): `FileNotFoundError: docs/iptc/consumer-review.json`, then (after the file exists but is incomplete) an assertion listing the specific `(repo, path)` pairs present in `inventory.json` but absent from the ledger.

**Minimal implementation API:** No new Python API. The ledger is data:
```json
{
  "schema": "machina.iptc.consumer-review/v1",
  "version": "1",
  "entries": [
    {"repo": "machina-templates", "path": "...", "category": "...",
     "owner": "...", "disposition": "...", "evidence": "..."}
  ]
}
```
Regenerate artifacts with:
```
python3 -m tools.iptc
```

**GREEN commands:**
- Focused: `python3 -m pytest tests/test_iptc_consumer_inventory.py -q`
- Full: `python3 -m tools.iptc.run_test_suites`
- Diff check: `git diff --stat` must show only `docs/iptc/consumer-review.json`, `docs/iptc/INVENTORY.md`, `docs/iptc/inventory.json`, and `tests/test_iptc_consumer_inventory.py`.

**Commit message:** `docs(iptc): add consumer review ledger and regenerate inventory`

**Rollback / stop condition:** If regeneration modifies any file outside `docs/iptc/`, stop — the generator has a side effect that must be understood before PR3-B. If a dependency cannot be assigned an `owner`, do not invent one: mark `owner: "UNASSIGNED"`, `disposition: "excluded"`, and state the reason in `evidence`; report the list of `UNASSIGNED` entries in the PR description.

---

# PR3-B — Package foundation (new `machina-templates` branch)

Branch: create `feat/iptc-canonical-package` from the PR3-A branch tip.
`machina-templates` remains source authority. Packaging **maps** to existing bytes; it does not move or copy logic.

---

## Task 3 — Root packaging configuration for `machina-sports-canonical==0.1.0`

**Prerequisite:** PR3-A merged (or its branch tip used as the base) and green.

**Objective:** Add root packaging configuration that builds distribution `machina-sports-canonical` version `0.1.0`, exposing import namespace `machina_sports_canonical` mapped onto the existing `tools/iptc/canonical` source directory. No source file is moved or copied. Adapters ship. JSON package data ships. The built package embeds a receipt recording version, source path, and a manifest of packaged files with hashes.

**Create:**
- `pyproject.toml` packaging section (or a new root `pyproject.toml` if none exists — verify first; do not clobber an existing one)
- `setup.py` plus `packaging/machina_sports_canonical/build.py` — minimal `build_py` filter whose only exception is the repository-only `export_official_terms.py`; no canonical runtime transformation is allowed
- `tools/iptc/canonical/package-receipt.json` — non-executable package metadata containing distribution version, authoritative source path/commit, and the existing nine-file core manifest receipt
- `README-machina-sports-canonical.md` (package long description) and `LICENSE` reference if absent

**Modify:**
- Root `pyproject.toml` (packaging/build-system/tool config only)
- `MANIFEST.in` (only if sdist data inclusion requires it)
- `tests/test_iptc_vendored_manifest.py` only to list `package-receipt.json` as an explicit, reasoned **not-vendored package-metadata file**; the nine-file sports-skills manifest and every existing canonical source byte remain unchanged

**Test paths:** Task 4 provides the tests. This task's own verification is build-only.

**RED test + command + expected failure:** This task's RED belongs to Task 4 and is written **first** as part of Task 4's ordering note below. To keep strict TDD, execute Task 4's step 1 (write the failing suite) before writing packaging config, then return here. The observed RED is:
```
python3 -m pytest tests/test_iptc_canonical_package.py -q
```
failing with `ModuleNotFoundError: No module named 'machina_sports_canonical'` and a build-artifact-absent assertion.

**Minimal implementation API:**

`pyproject.toml` must specify exactly:
- `[project] name = "machina-sports-canonical"`, `version = "0.1.0"`, `requires-python = ">=3.9"`, `dependencies = []`.
- `[build-system] requires = ["setuptools>=68", "wheel"]`, `build-backend = "setuptools.build_meta"`.
- Package discovery mapping `machina_sports_canonical` → `tools/iptc/canonical` (setuptools `package-dir` mapping plus explicit `packages` listing, including the adapters subpackage).
- `package-data` including `official-property-names.json`, `shared-context.json`, and `package-receipt.json`.
- The custom `build_py` filter removes exactly `machina_sports_canonical.export_official_terms` from wheel/sdist runtime modules. It must reject configuration that excludes any additional module. The generator remains in the repository at its current path and is neither moved nor shipped.

Receipt content (read-only JSON package data, never imported as code):
```json
{
  "distribution_version": "0.1.0",
  "source": "machina-templates:tools/iptc/canonical",
  "source_commit": "<reviewed merge/source commit>",
  "core_manifest": {"<relative core path>": "<sha256>"}
}
```
The `core_manifest` key set and hashes must equal `tools/iptc/vendored-manifest.json`; adapters ship in the wheel but remain outside the sports-skills vendored-core receipt and are checked separately against their authoritative source bytes.

**GREEN commands:**
- `python3 -m build`
- `python3 -m pytest tests/test_iptc_canonical_package.py -q` (passes only after Task 4's assertions are satisfied)
- `python3 -m tools.iptc.run_test_suites`

**Commit message:** `build(iptc): package canonical core as machina-sports-canonical 0.1.0`

**Rollback / stop condition:** Stop if packaging requires any edit to an **existing** file under `tools/iptc/canonical/`; adding the approved non-executable `package-receipt.json` is the sole package-metadata exception and must be explicitly excluded from sports-skills vendoring without changing the nine-file core manifest. Stop if a root `pyproject.toml` already exists and serves another purpose that packaging config would break; report and request direction rather than merging configs speculatively.

---

## Task 4 — Package proof suite

**Prerequisite:** Task 3's design decided; this suite is written **before** Task 3's implementation (see Task 3 RED note).

**Objective:** Prove the distribution is real, self-contained, faithful to source, and offline-capable — on a clean interpreter.

**Create:**
- `tests/test_iptc_canonical_package.py`

**Modify:**
- `tools/iptc/test-suites.json` — register the package proof suite
- `tests/test_iptc_test_manifest.py` — keep the suite inventory exact
- `.github/workflows/validate-iptc-sport-schema.yml` — include `pyproject.toml`, `setup.py`, `packaging/machina_sports_canonical/**`, receipt and package test paths in triggers/gates

**Test paths:**
- `tests/test_iptc_canonical_package.py`

**RED test + command + expected failure:**

Cases, all required:
1. `test_wheel_and_sdist_build` — `python -m build` produces exactly one `.whl` and one `.tar.gz` for `machina_sports_canonical-0.1.0`.
2. `test_clean_venv_import` — create a throwaway venv, install the built wheel with `--no-index` (no network), `import machina_sports_canonical` succeeds.
3. `test_constants_functions_and_adapters_import` — importable: the canonical constants module, the serialization/validation functions, and each shipped adapter module.
4. `test_json_resources_load_offline` — `official-property-names.json` and `shared-context.json` load from the **installed** package, with no filesystem reach-back into the repo and no network.
5. `test_installed_source_hashes_match_authoritative` — the installed nine-file `core_manifest` key set and hashes equal `tools/iptc/vendored-manifest.json`; every installed adapter module and JSON resource is byte-equal to its authoritative source under `tools/iptc/canonical/`; `package-receipt.json` is present and no installed runtime file is unaccounted for.
6. `test_python39_parse_and_stdlib_only` — every packaged `.py` parses under a 3.9-compatible AST feature check, and no import outside the stdlib allowlist appears in any packaged module.
7. `test_zero_runtime_dependencies` — installed distribution metadata reports no `Requires-Dist`.
8. `test_wheel_record_is_closed_and_excludes_generator` — wheel `RECORD` contains exactly the expected core, adapters, JSON resources and distribution metadata; it excludes `machina_sports_canonical/export_official_terms.py`, and the build filter excludes no other source module.

Command:
```
python3 -m pytest tests/test_iptc_canonical_package.py -q
```

Expected failure (RED): `ModuleNotFoundError: No module named 'machina_sports_canonical'` from case 2/3, and a "no dist artifacts found" assertion from case 1.

**Minimal implementation API:** Test-only helpers, kept inside the test module: `_build_dists(tmp)`, `_clean_install(whl, python_exe)`, `_sha256(path)`, `_packaged_modules()`. No production API.

**GREEN commands:**
- Focused: `python3 -m pytest tests/test_iptc_canonical_package.py -q`
- Build: `python3 -m build`
- Clean installs: run the clean-venv install case under **Python 3.9** and **Python 3.11** where the interpreter is available; skip-with-reason (not silently pass) when absent, and print the skip.
- Full: `python3 -m tools.iptc.run_test_suites`

**Commit message:** `test(iptc): prove canonical package build, install and source fidelity`

**Rollback / stop condition:** Stop if case 5 fails because packaging rewrote or reformatted source — never "fix" it by regenerating the manifest from the installed copy; that would make the test tautological. Stop if case 6 requires adding a third-party dependency to satisfy an import: the canonical core is stdlib-only by contract.

---

## Task 5 — Trusted publishing workflow and release gate

**Prerequisite:** Tasks 3 and 4 committed and green; PR3-B branch ready for review.

**Objective:** Add release automation and the tag convention, **stopping before public PyPI publication**. Publication requires external human approval.

**Create:**
- `.github/workflows/publish-machina-sports-canonical.yml`
- `docs/iptc/RELEASING.md` (tag convention, approval gate, post-release verification checklist)

**Modify:** none.

**Test paths:**
- `tests/test_iptc_canonical_package.py` (extend with a workflow-shape test)

**RED test + command + expected failure:**
- `test_publish_workflow_uses_trusted_publishing` — the workflow file exists, triggers on tags matching the convention, requests `id-token: write`, uses PyPI trusted publishing (OIDC), and contains **no** API-token secret reference.
- `test_release_docs_document_approval_gate` — `docs/iptc/RELEASING.md` states the external approval gate and the post-release verification steps.

Command:
```
python3 -m pytest tests/test_iptc_canonical_package.py -q -k publish or release
```
Expected failure (RED): `FileNotFoundError` for the workflow and the docs file.

**Minimal implementation API:**
- Tag convention: `machina-sports-canonical-v0.1.0` (distribution-scoped so it cannot collide with template release tags).
- Workflow: build with `python -m build`, then `pypa/gh-action-pypi-publish` gated on a GitHub **environment** requiring reviewer approval. No token secrets.

**GREEN commands:**
- Focused: `python3 -m pytest tests/test_iptc_canonical_package.py -q`
- Full: `python3 -m tools.iptc.run_test_suites`
- `python3 -m build` (artifacts reproduced locally)

**Commit message:** `ci(iptc): add trusted publishing workflow for canonical package`

**🛑 EXTERNAL APPROVAL GATE — STOP HERE.**
Do not publish to public PyPI. Report to the human: artifacts built, hashes, and the request to approve release.

**After approval only, in order:**
1. Merge PR3-B.
2. Tag and release `machina-sports-canonical-v0.1.0`.
3. Verify the GitHub release exists and references the built artifacts.
4. Verify `https://pypi.org/pypi/machina-sports-canonical/json` returns `0.1.0`.
5. Verify published wheel/sdist sha256 equal the locally built artifacts' hashes.
6. Verify a clean install from PyPI (`pip install machina-sports-canonical==0.1.0`) imports and passes the Task 4 offline-resource case.

**Rollback / stop condition:** PyPI releases are **not deletable in a way that frees the version**; a bad `0.1.0` burns the version number. If any pre-release verification fails, do **not** publish — fix and rebuild. If post-publish verification (steps 4–6) fails, stop the entire PR3-C sequence: yanking and shipping `0.1.1` is the correct recovery, not proceeding on a broken pin. The name being 404/unclaimed on 2026-08-10 does **not** mean it is reserved; if a name collision appears at publish time, stop and escalate.

---

# PR3-C — Client runtime (new `machina-client-api` branch)

Repo: sibling `machina-client-api` repository.
Branch: create `feat/iptc-canonical-runtime`.
**No schema code lands in client-api.** The client installs and executes; it does not own vocabulary.

---

## Task 6 — Pin the exact package version in client requirements

**Prerequisite:** Task 5 fully complete **including release and post-release verification**. Without a published, verified `0.1.0`, this task is blocked and must not be started.

**Objective:** Pin `machina-sports-canonical==0.1.0` exactly (no range, no `~=`) in every dependency file actually consumed by an image build, and nowhere else.

**Modify (`machina-client-api`):**
- `requirements.txt` (production image source)
- `docker/development/requirements.txt` (development image source)
- `pyproject.toml`
- `pdm.lock` — regenerate from the updated project metadata; never hand-edit only the top-level pin

**Do not modify:** `requirements.prod.txt` — it is not referenced by either dockerfile.

**Create:** none.

**Test paths:**
- `tests/test_connector_canonical_runtime.py` (created in Task 7; its pin assertions are written here first)

**RED test + command + expected failure:**
- `test_canonical_pinned_exactly_in_runtime_requirements` — each of the three files contains the literal `machina-sports-canonical==0.1.0`.
- `test_unreferenced_prod_requirements_untouched` — `requirements.prod.txt` contains no `machina-sports-canonical` reference.

Command:
```
python3 -m pytest tests/test_connector_canonical_runtime.py -q -k pinned or untouched
```
Expected failure (RED): assertion that the literal pin is absent from `requirements.txt`.

**Minimal implementation API:** Add exactly one line per file:
```
machina-sports-canonical==0.1.0
```
placed in alphabetical position if the file is sorted; otherwise appended in the existing style.

**GREEN commands:**
- Focused: `python3 -m pytest tests/test_connector_canonical_runtime.py -q`
- `pip install -r requirements.txt --dry-run` (resolver sanity)

**Commit message:** `build(iptc): pin machina-sports-canonical==0.1.0 in client runtime`

**Rollback / stop condition:** Stop if the pin conflicts with an existing resolved dependency — the canonical package has zero dependencies, so a conflict means a name clash or a stale local index, both of which need investigation, not a loosened pin. Never relax `==` to a range to make resolution pass.

---

## Task 7 — Connector runtime execution proof

**Prerequisite:** Task 6 committed; the package installable in the local dev environment.

**Objective:** Prove, through the **real** executor, that a declared pyscript connector can import `machina_sports_canonical` and call a deterministic canonical function — and that the security posture around it is fail-closed.

**Create:**
- `tests/test_connector_canonical_runtime.py` (extended from Task 6's pin assertions)
- Test-local fixture connector declaration + pyscript sidecar under the test tree (not under production connector paths)

**Modify:** none in production code.

**Test paths:**
- `machina-client-api/tests/test_connector_canonical_runtime.py`

**RED test + command + expected failure:**
1. `test_real_executor_runs_pyscript_importing_canonical` — invoke the real `core.connector.executor.connector_script`; patch only `connector_retrieve` to supply the stored connector fixture, while leaving import resolution, `exec`, declared-command dispatch and canonical functions unmocked. The fixture pyscript does `import machina_sports_canonical` and calls a deterministic canonical function; assert the exact expected return value.
2. `test_only_declared_commands_are_callable` — a command not present in the connector declaration is refused; the refusal is an error, not a silent no-op.
3. `test_unknown_capability_fails_closed` — an unrecognized capability name produces refusal, never a permissive default.
4. `test_refused_rights_are_redacted` — refusal messages contain no source refs, credentials, payload contents, or internal paths.
5. `test_no_canonical_source_in_client_api` — a repo scan asserts client-api contains **zero** canonical schema source (no `official-property-names.json`, no adapters, no serialization implementation); only the pinned dependency reference exists.

Command:
```
python3 -m pytest tests/test_connector_canonical_runtime.py -q
```
Expected failure (RED): case 1 fails with `ModuleNotFoundError: No module named 'machina_sports_canonical'` before install, then with an assertion mismatch on the deterministic value before the fixture is correct; cases 3/4 fail open until the gate is exercised.

**Minimal implementation API:** Test-only. No production API added to client-api. If cases 2–4 fail because the existing executor genuinely fails open, **stop and report** — that is a client-api security finding requiring its own decision, not a fix to smuggle into this PR.

**GREEN commands:**
- Focused: `python3 -m pytest tests/test_connector_canonical_runtime.py -q`
- Full client suite: the repo's standard test command.

**Commit message:** `test(iptc): prove connector runtime imports canonical package`

**Rollback / stop condition:** Do **not** substitute a mocked executor to get green — a mocked executor proves nothing about in-process exec and invalidates the entire runtime claim. Stop if the only way to pass case 1 is `sys.path` manipulation inside the pyscript; that would contradict the image-installed-wheel evidence and means the pin is not actually effective.

---

## Task 8 — Image build verification

**Prerequisite:** Task 7 green.

**Objective:** Prove the pinned package is present **inside both built images**, at the exact version, and stop before deploying anything.

**Create:** none.
**Modify:** none (dockerfiles should need no change; if one does, that is a finding — report before editing).

**Test paths:** verification is command-driven; record outputs in the commit body.

**RED test + command + expected failure:** N/A as a code test — this is a build verification task whose RED is the pre-Task-6 state (package absent from images). If a code-level assertion is desired, extend `test_connector_canonical_runtime.py` with a marker-gated test that shells out to `docker run` and is skipped-with-reason when Docker is unavailable.

**Commands:**
```
python3 -m pytest tests/test_connector_canonical_runtime.py -q
docker build -f docker/production/dockerfile  -t machina-client-api:iptc-prod .
docker build -f docker/development/dockerfile -t machina-client-api:iptc-dev  .
docker run --rm machina-client-api:iptc-prod python -c "import machina_sports_canonical as m; print(m.__version__)"
docker run --rm machina-client-api:iptc-dev  python -c "import machina_sports_canonical as m; print(m.__version__)"
```
Both `docker run` invocations must print `0.1.0`.

**Commit message:** `build(iptc): verify canonical package installed in client images`

**🛑 EXTERNAL APPROVAL GATE — STOP HERE.**
Do not deploy to sandbox. Report: both image digests, both printed versions, and the request to approve the sandbox image rollout.

**Rollback / stop condition:** If the production image prints nothing while development prints `0.1.0`, the production build is not consuming root `requirements.txt` as assumed — stop and re-establish the evidence before proceeding. Never add schema code to client-api to work around a missing install.

---

# PR3-D — Shared connector and WCI golden proof (`machina-templates`, after client sandbox runtime exists)

Branch: create `feat/iptc-wci-canonical-seam` from `main` after PR3-B merged.
**Blocked** until the sandbox runs an image containing `machina-sports-canonical==0.1.0` (Task 8 approval executed).

---

## Task 9 — Shared canonical connector

**Prerequisite:** Task 8 approved and the sandbox image live.

**Objective:** Add a thin shared pyscript connector that exposes canonical operations to templates. It contains **only** dispatch and injected-crosswalk resolution. It contains **no** schema vocabulary, **no** serialization logic, and **no** CLI or long-running service.

**Create:**
- `connectors/machina-sports-canonical/machina-sports-canonical.yml`
- `connectors/machina-sports-canonical/machina-sports-canonical.py`
- `connectors/machina-sports-canonical/_install.yml` (optional; include only if the repo's install convention requires it)
- `tests/test_iptc_canonical_connector.py`

**Modify:** none.

**Test paths:**
- `tests/test_iptc_canonical_connector.py`

**RED test + command + expected failure:**
1. `test_declared_commands_exist` — the YAML declares exactly: provider preflight, canonicalize event envelope, validate event envelope, capability/rights gate; each maps to a function present in the pyscript.
2. `test_connector_contains_no_schema_vocabulary` — the pyscript source contains no IPTC property literals (`sport:`, `schema:` prefixed names), no serialization implementation, and no hardcoded vocabulary tables.
3. `test_connector_delegates_to_package` — canonicalize/validate paths call `machina_sports_canonical` functions (`adapters.*.to_observation`, `serialize.canonical_envelope`, `check_compatibility`, `rights_findings`, `surrogate_resolver`); assert via import-graph/source inspection, not by mocking.
4. `test_provider_allowlist_enforced` — a provider absent from the allowlist is refused.
5. `test_no_cli_or_service_entrypoint` — no `__main__`, no server/loop construct.

Command:
```
python3 -m pytest tests/test_iptc_canonical_connector.py -q
```
Expected failure (RED): `FileNotFoundError` for the connector YAML and pyscript.

**Minimal implementation API (pyscript functions, dispatch-only):**
```python
def provider_preflight(...): ...
def canonicalize_event(...): ...
def validate_event(...): ...
def capability_rights_gate(...): ...
```
Each body: resolve injected crosswalk, delegate to the package, return the package result. Crosswalk maps are **injected**, never embedded.

**GREEN commands:**
- Focused: `python3 -m pytest tests/test_iptc_canonical_connector.py -q`
- Full: `python3 -m tools.iptc.run_test_suites`

**Commit message:** `feat(iptc): add shared machina-sports-canonical connector`

**Rollback / stop condition:** Stop if any test can only pass by inlining vocabulary into the connector — that duplicates the seam and defeats the whole PR. Stop if the connector needs to reach the filesystem for JSON resources; those load from the installed package.

---

## Task 10 — Fail-closed provider preflight before retrieval

**Prerequisite:** Task 9 green.

**Objective:** Preflight must **refuse all current prototype-only adapters at production tier before any provider retrieval occurs**, with zero provider calls made. Post-render rights evaluation is a **drift check**, not the gate.

**Modify:**
- `connectors/machina-sports-canonical/machina-sports-canonical.py`
- `connectors/machina-sports-canonical/machina-sports-canonical.yml` (capability declarations only)

**Test paths:**
- `tests/test_iptc_canonical_connector.py` (extend)

**RED test + command + expected failure:**
1. `test_production_tier_refuses_prototype_adapters` — for each currently prototype-only adapter, preflight at production tier refuses.
2. `test_zero_provider_calls_on_refusal` — instrument the provider call surface with a counter; assert the count is exactly `0` on refusal (refusal must precede retrieval, not follow it).
3. `test_unknown_capability_name_fails_closed` — an undeclared/unknown dotted capability refuses.
4. `test_capabilities_use_existing_dotted_names` — declared capabilities are drawn from the existing dotted capability vocabulary; no new ad-hoc names introduced.
5. `test_post_render_rights_is_drift_check_only` — post-render `rights_findings` output is recorded as a drift finding and does not itself authorize or block retrieval.

Command:
```
python3 -m pytest tests/test_iptc_canonical_connector.py -q
```
Expected failure (RED): case 2 fails with a nonzero provider-call count (refusal happening after retrieval), and case 1 fails because production tier currently permits prototype adapters.

**Minimal implementation API:** Extend `provider_preflight` to evaluate `(provider, tier, capability)` and return a refusal before any retrieval path is reachable. Unknown capability → refuse.

**GREEN commands:**
- Focused: `python3 -m pytest tests/test_iptc_canonical_connector.py -q`
- Full: `python3 -m tools.iptc.run_test_suites`

**Commit message:** `feat(iptc): fail-closed provider preflight before retrieval`

**Rollback / stop condition:** Stop if any adapter must be promoted out of prototype tier to make a downstream test pass — tier promotion is a rights/parity decision requiring Amendment B authority, not a test convenience. Do not weaken case 2 to "at most one call".

---

## Task 11 — WCI install reference and canonical resolver workflow

**Prerequisite:** Task 10 green.

**Objective:** Make the shared connector available to WCI and add a stable resolver workflow that turns provider-scoped identifiers into stable Machina URNs using the existing crosswalk maps.

**Create:**
- `agent-templates/world-cup-intelligence/workflows/worldcup-resolve-canonical-event.yml` (exact chosen name; do not vary)
- `agent-templates/world-cup-intelligence/tests/test_worldcup_canonical_event.py`

**Modify:**
- `agent-templates/world-cup-intelligence/_install.yml` (add cross-template install reference to `connectors/machina-sports-canonical`)

**Test paths:**
- `agent-templates/world-cup-intelligence/tests/test_worldcup_canonical_event.py` — resolver, compatibility, ingest and read-seam cases for Tasks 11–14

**RED test + command + expected failure:**
1. `test_install_reference_present` — `_install.yml` references the shared connector.
2. `test_resolver_workflow_exists_with_exact_name` — `workflows/worldcup-resolve-canonical-event.yml` exists.
3. `test_resolver_accepts_event_urn_provider_and_provider_event_id` — the workflow's declared inputs are exactly `event_urn`, `provider`, `provider_event_id`.
4. `test_equivalent_provider_ids_resolve_to_same_machina_urn` — for event, team, and competition, equivalent provider IDs across providers resolve to the same stable Machina URN.
5. `test_unmapped_structural_resources_get_marked_surrogates` — an unmapped structural resource yields a surrogate URN that is explicitly **marked** as a surrogate (never silently indistinguishable from a real mapping).

Command:
```
python3 -m pytest agent-templates/world-cup-intelligence/tests/test_worldcup_canonical_event.py -q -k resolver
```
Expected failure (RED): `FileNotFoundError` for the resolver workflow; then case 4 failing with divergent URNs per provider.

**Minimal implementation API:** Workflow tasks: preflight → crosswalk lookup via existing maps → `surrogate_resolver` fallback for unmapped structural resources → return `{event_urn, team_urns, competition_urn, surrogates[]}`. No provider branching in the workflow body.

**GREEN commands:**
- Focused: `python3 -m pytest agent-templates/world-cup-intelligence/tests/test_worldcup_canonical_event.py -q -k resolver`
- Full: `python3 -m tools.iptc.run_test_suites`

**Commit message:** `feat(wci): add canonical event resolver workflow and install reference`

**Rollback / stop condition:** Stop if resolution requires a new crosswalk map — this task uses **existing** maps. Stop if a surrogate would be minted for a *non-structural* resource; surrogates are for structural gaps only.

---

## Task 12 — Versioned deprecated compatibility projection

**Prerequisite:** Task 11 green.

**Objective:** Add exactly **one** explicit, versioned, deprecated compatibility projection derived **only** from `event_view`. The persisted document name stays `worldcup:event`. The document root value is the canonical envelope **plus** the exact legacy top-level aliases that existing filters/readers require. Nested-only compatibility is **forbidden** — the Task 1 storage-predicate findings prove readers filter on top-level paths.

The consumers those findings name are **provider connector workflows**, principally under `connectors/sportradar-soccer/` and `connectors/stats-perform/`, not WCI itself: WCI reads `schema:startDate` and `sport:status` in Python from an already-loaded document. Top-level aliases therefore remain necessary, but the compatibility they preserve is owed to those real provider connector consumers. This does **not** widen the task: the scope stays the single WCI projection under the unchanged document name `worldcup:event`, and no connector workflow is modified here. Migrating those consumers is later work outside this plan.

**Create:**
- Compatibility projection definition (mapping or workflow fragment) under `agent-templates/world-cup-intelligence/mappings/` — exact filename chosen at implementation time and recorded in the commit body
- Snapshot fixtures, one per alias, under the WCI test fixture tree

**Modify:** none of the existing consumer readers.

**Test paths:**
- `agent-templates/world-cup-intelligence/tests/test_worldcup_canonical_event.py` (extend) — compatibility cases

**RED test + command + expected failure:**
1. `test_document_name_unchanged` — persisted name is exactly `worldcup:event`.
2. `test_root_is_canonical_envelope_plus_aliases` — root contains the canonical envelope keys **and** each legacy top-level alias.
3. `test_aliases_derived_only_from_event_view` — each alias's value equals the exact `event_view` path it derives from; no alias is computed from raw provider payloads.
4. `test_nested_only_compatibility_rejected` — a projection that nests the aliases fails the check (guards regression).
5. `test_snapshot_per_alias_with_removal_owner` — one snapshot test per alias; each alias carries a documented removal owner and deprecation version.
6. `test_no_rename_and_no_index_removal` — no document rename and no index removal in the diff.
7. `test_storage_predicates_still_resolve` — the exact predicates `value.schema:startDate` and `value.sport:status`, as written by the real provider connector consumers Task 1 located under `connectors/sportradar-soccer/` and `connectors/stats-perform/`, still resolve against the projected document. Direct tie-back to the Task 1 findings at their verified locations; assert against the predicate paths those connectors actually use, not against a WCI-authored predicate, which does not exist.

Command:
```
python3 -m pytest agent-templates/world-cup-intelligence/tests/test_worldcup_canonical_event.py -q -k compat
```
Expected failure (RED): case 2 fails — root is the bare canonical envelope with no legacy aliases; case 7 fails — storage predicates do not resolve.

**Minimal implementation API:** A single declarative alias table: `legacy_top_level_key -> event_view.<exact.path>`, plus `deprecated_since` and `removal_owner` per entry. No logic beyond exact-path projection.

**GREEN commands:**
- Focused: `python3 -m pytest agent-templates/world-cup-intelligence/tests/test_worldcup_canonical_event.py -q -k compat`
- Full: `python3 -m tools.iptc.run_test_suites`

**Commit message:** `feat(wci): add versioned deprecated compatibility projection`

**Rollback / stop condition:** Stop if more than one projection is needed — a second projection means the alias set is not actually closed and the inventory (Task 2) is incomplete. Stop if any alias cannot be derived from `event_view` by exact path; computing it would make the projection a second source of truth.

---

## Task 13 — Rewire fixture ingestion through the seam

**Prerequisite:** Task 12 green.

**Objective:** Make `worldcup-ingest-fixtures.yml` preflight before provider retrieval, canonicalize the retrieved payload, derive compatibility, and persist. Stop calling `worldcup-market-intelligence.py::mint_event_identity`. Retain the deprecated function **only if** the inventory says a remaining consumer exists.

**Modify:**
- `agent-templates/world-cup-intelligence/workflows/worldcup-ingest-fixtures.yml`
- `agent-templates/world-cup-intelligence/worldcup-market-intelligence.py` — only if the inventory shows zero remaining consumers of `mint_event_identity`, and then only to mark it deprecated (removal is a later PR)

**Do not touch:** standings, injuries, squads, brackets workflows.

**Test paths:**
- `agent-templates/world-cup-intelligence/tests/test_worldcup_canonical_event.py` (extend) — ingest cases

**RED test + command + expected failure:**
1. `test_preflight_precedes_provider_retrieval` — task order in the workflow places preflight strictly before the retrieval task.
2. `test_ingest_canonicalizes_and_derives_compatibility` — persisted document is envelope + aliases (Task 12 shape).
3. `test_mint_event_identity_not_called_by_ingest` — the ingest workflow no longer references `mint_event_identity`.
4. `test_deprecated_function_retention_matches_inventory` — if `docs/iptc/inventory.json` lists a remaining consumer, the function is retained and marked deprecated; if not, retention is not required.
5. `test_adjacent_workflows_unchanged` — `git diff --name-only` shows no standings/injuries/squads/brackets workflow files.

Command:
```
python3 -m pytest agent-templates/world-cup-intelligence/tests/test_worldcup_canonical_event.py -q -k ingest
```
Expected failure (RED): case 1 fails (retrieval currently precedes any gate); case 3 fails (`mint_event_identity` still referenced).

**Minimal implementation API:** Workflow edits only — insert preflight task, replace identity-minting task with the resolver + canonicalize + compatibility tasks, keep persistence target unchanged.

**GREEN commands:**
- Focused: `python3 -m pytest agent-templates/world-cup-intelligence/tests/test_worldcup_canonical_event.py -q -k ingest`
- Full: `python3 -m tools.iptc.run_test_suites`

**Commit message:** `refactor(wci): route fixture ingestion through canonical seam`

**Rollback / stop condition:** Stop if removing `mint_event_identity` from ingest changes the persisted document's identity values — identity must be **equal**, not merely well-formed. Do not "clean up" adjacent workflows even if they look wrong; note them for a later PR.

---

## Task 14 — Serve canonical through the read seam without behavior change

**Prerequisite:** Task 13 green.

**Objective:** Serve the canonical envelope / `event_view` through the existing read seam, changing nothing observable downstream.

**Modify:**
- `agent-templates/world-cup-intelligence/workflows/worldcup-get-iptc-event-context.yml`
- `agent-templates/world-cup-intelligence/mappings/worldcup-iptc-event-to-api-response.yml`
- `agent-templates/world-cup-intelligence/workflows/worldcup-match-preview.yml` — **only at the lookup task**

**Test paths:**
- `agent-templates/world-cup-intelligence/tests/test_worldcup_canonical_event.py` (extend) — seam cases

**RED test + command + expected failure:**
1. `test_prompt_task_unchanged_by_hash` — sha256 of the match-preview prompt task block is byte-identical before and after.
2. `test_post_lookup_task_order_unchanged` — the ordered list of task names after the lookup task is identical.
3. `test_cache_semantics_unchanged` — cache key inputs and TTL are identical.
4. `test_api_response_snapshot_unchanged` — the mapping's output snapshot is byte-identical.
5. `test_downstream_behavior_unchanged` — end-to-end fixture through the seam produces the same downstream outputs.

Command:
```
python3 -m pytest agent-templates/world-cup-intelligence/tests/test_worldcup_canonical_event.py -q -k seam
```
Expected failure (RED): snapshot files absent → the snapshot tests fail on first run; capture the pre-change baseline **before** editing the workflows (baseline capture is part of the RED step).

**Minimal implementation API:** Read-path source substitution only: lookup reads the canonical envelope/`event_view`; mapping projects from it. No new tasks, no reordering, no cache-key change.

**GREEN commands:**
- Focused: `python3 -m pytest agent-templates/world-cup-intelligence/tests/test_worldcup_canonical_event.py -q -k seam`
- Full: `python3 -m tools.iptc.run_test_suites`

**Commit message:** `refactor(wci): serve canonical envelope through read seam`

**Rollback / stop condition:** Stop if any snapshot changes. A changed prompt hash or a changed post-lookup order means the seam is leaking into behavior — revert and re-scope. Do not update a snapshot to match new output in this task; snapshots here exist precisely to forbid change.

---

## Task 15 — Four-provider substitution proof

**Prerequisite:** Task 14 green.

**Objective:** Prove that the **same WCI workflow source** produces an equivalent canonical result across four providers, with provider selection changing **only in configuration** — no provider branches above the seam.

**Create:**
- Synthetic equivalent fixtures under a clearly named prototype path, e.g. `tests/fixtures/iptc/prototype-four-provider/{sports-skills,api-football,sportradar-soccer,opta}/`
- `tests/test_iptc_wci_provider_substitution.py` (this task completes the suite)

**Modify:**
- `agent-templates/world-cup-intelligence/tests/test_worldcup_market_intelligence.py` — replace legacy-only `TestMintEventIdentity` assertions with canonical-envelope plus compatibility assertions
- `tools/iptc/test-suites.json` and `tests/test_iptc_test_manifest.py` — register the new WCI/substitution suites exactly

**Test paths:**
- `tests/test_iptc_wci_provider_substitution.py`
- `agent-templates/world-cup-intelligence/tests/test_worldcup_canonical_event.py`
- `agent-templates/world-cup-intelligence/tests/test_worldcup_market_intelligence.py`
- Existing `tests/test_iptc_cross_provider_equivalence.py` remains a required regression suite

**RED test + command + expected failure:**

Four legs, one per provider: sports-skills canonical envelope, API-Football adapter, Sportradar soccer adapter, Opta adapter.
1. `test_same_workflow_source_all_providers` — the workflow file hash is identical across legs; only configuration differs.
2. `test_identity_equivalent_across_providers` — resolved Machina **event**, **team**, and **competition** URNs are equal across legs.
3. `test_participants_equivalent` — participant sets equal.
4. `test_start_equivalent` — start instant equal.
5. `test_normalized_status_equivalent` — normalized status equal.
6. `test_score_result_equivalent_where_supported` — where the provider supports score/result **and** the value is stable, values equal; where unsupported, the leg is recorded as unsupported rather than skipped silently.
7. `test_workflow_output_contract_stable` — output contract shape identical across legs.
8. `test_allowed_differences_are_closed_set` — differences are confined to the closed set: **provider IDs, provenance, rights, capabilities, raw evidence, and actions/statistics not shared by capability**. Any difference outside this set fails.
9. `test_llm_prose_semantic_not_byte_equal` — LLM-generated prose is compared semantically, never byte-for-byte.
10. `test_expected_capability_differences_are_explicit` — the synthetic matrix records the reviewed expectations rather than treating absence as failure: sports-skills lacks result/clock/actions; API-Football provides result+clock; Sportradar adds result+attendance/country; Opta adds actions/play-by-play. The test reads capability reports, never provider-name branches in workflow code.
11. `test_every_leg_is_prototype_only` — each fixture leg passes at prototype tier and fails at production tier with `rights-prototype-only`.

Command:
```
python3 -m pytest tests/test_iptc_wci_provider_substitution.py -q
```
Expected failure (RED): fixtures absent → collection error; then case 2 failing with per-provider divergent URNs before the resolver is wired for all four legs.

**Minimal implementation API:** Fixtures + configuration matrix only. If a leg needs a code branch to pass, that is the failure this task exists to detect — report it, do not add the branch.

**GREEN commands:**
- Focused: `python3 -m pytest tests/test_iptc_wci_provider_substitution.py agent-templates/world-cup-intelligence/tests/test_worldcup_canonical_event.py agent-templates/world-cup-intelligence/tests/test_worldcup_market_intelligence.py -q`
- Existing equivalence regression: `python3 tests/test_iptc_cross_provider_equivalence.py -v` (review baseline: 44 tests passed)
- Full: `python3 -m tools.iptc.run_test_suites`

**Commit message:** `test(wci): prove four-provider canonical substitution`

**Scope honesty:** These are **synthetic** fixtures. This proves **prototype shape and behavior**. It does **not** prove live provider rights or live data parity, and the test module docstring must say so verbatim.

**Rollback / stop condition:** Stop if passing requires widening the allowed-difference set — the set is closed by Amendment B. Stop if any leg requires live network access; fixtures are offline by construction.

---

## Task 16 — Full audit, static checks, and sandbox proof gate

**Prerequisite:** Task 15 green.

**Objective:** Run the complete verification surface, then stop for approval before touching the Machina sandbox.

**Commands:**
```
python3 -m pytest tests/test_iptc_wci_provider_substitution.py -q
python3 -m pytest tests/test_iptc_canonical_connector.py -q
python3 -m tools.iptc.run_test_suites
python3 -m tools.iptc                      # regenerate; diff must be empty or explained
python3 scripts/check-machina-ai-policy.py all --require-semantic  # router-policy lint
```
Plus: full install audit (every `_install.yml` reference resolves) and static template import checks (every workflow/mapping/connector reference resolves without executing).

**Create/Modify:** none beyond regenerated inventory artifacts, if any.

**Commit message:** `chore(iptc): full audit for WCI canonical substitution`

**🛑 EXTERNAL APPROVAL GATE — STOP HERE.**
Do not import to or execute in the Machina sandbox. Report: all command outputs, the four-provider result matrix, and the request to approve sandbox import.

**After approval only:**
1. Import the templates into the **sandbox**.
2. Execute the synthetic four-provider proof in the sandbox.
3. Record the sandbox run outputs against the local matrix.

**No production deployment** in this plan under any circumstance.

**Rollback / stop condition:** If the sandbox run diverges from the local matrix on any non-allowed-difference field, stop and treat it as a real seam defect — the local fixtures are then insufficient and must be corrected before any further work. Do not adjust the sandbox to match local.

---

## Task 17 — Stop and review

**Prerequisite:** Task 16 sandbox proof recorded.

**Objective:** Hard stop. Full review of PR3-A..PR3-D before any further consumer migration.

**Create:** a short review note appended to this plan file (or a sibling `-review.md`) recording: what shipped, what was proven, what was explicitly not proven, and open findings.

**Later work — outline only, not authorized by this plan:**
- **E** — Machina Media / shared selectors
- **F** — SportsClaw `get_canonical_event`
- **G** — Sports TV
- Customer migration and alias-removal plans

**Explicitly out of scope:** Sports Experience, plus the other adjacent internal product surfaces that are not named in the later-work outline above.

**Commit message:** `docs(iptc): record PR3 stop-and-review outcome`

**Rollback / stop condition:** No new consumer work begins until this review is signed off.

---

# Acceptance matrix

| # | Task | Primary artifact | Green proof | Gate |
|---|---|---|---|---|
| 1 | Coupling detection | `tools/iptc/inventory.py` | `test_iptc_consumer_inventory.py` detects `worldcup:event`, `value.schema:startDate`, `value.sport:status` | — |
| 2 | Review ledger | `docs/iptc/consumer-review.json` | unreviewed count == 0; artifacts regenerated | — |
| 3 | Packaging config | `pyproject.toml` | `python -m build` produces wheel + sdist | — |
| 4 | Package proof | `tests/test_iptc_canonical_package.py` | clean-venv import, offline resources, hash fidelity, py39 parse, zero deps | — |
| 5 | Publish workflow | `.github/workflows/publish-*.yml` | trusted publishing, no token secret | 🛑 release approval |
| 6 | Runtime pin | 3 dependency files | exact `==0.1.0`; `requirements.prod.txt` untouched | blocked on release |
| 7 | Executor proof | `tests/test_connector_canonical_runtime.py` | real `connector_script` imports package; fail-closed + redacted | — |
| 8 | Image verify | both dockerfiles | `0.1.0` printed inside prod and dev images | 🛑 sandbox image approval |
| 9 | Shared connector | `connectors/machina-sports-canonical/` | delegates to package; no vocabulary; no CLI | blocked on sandbox runtime |
| 10 | Preflight | connector pyscript | prototype adapters refused at production tier; **zero** provider calls | — |
| 11 | Resolver | `workflows/worldcup-resolve-canonical-event.yml` | equivalent provider IDs → same Machina URN; marked surrogates | — |
| 12 | Compat projection | WCI mapping | name stays `worldcup:event`; root = envelope + exact top-level aliases; per-alias snapshots + removal owner | — |
| 13 | Ingest rewire | `worldcup-ingest-fixtures.yml` | preflight before retrieval; `mint_event_identity` not called | — |
| 14 | Read seam | context workflow + response mapping + preview lookup | prompt hash, task order, cache semantics, outputs unchanged | — |
| 15 | Four-provider proof | `tests/test_iptc_wci_provider_substitution.py` | identity/participants/start/status/score equivalent; closed difference set | — |
| 16 | Full audit | all suites + install/static checks | all green; four-provider matrix recorded | 🛑 sandbox template approval |
| 17 | Stop/review | review note | sign-off recorded | 🛑 hard stop |

---

# Strict merge order

```
CoS Amendment B
  → PR3-A
  → PR3-B merge
  → 0.1.0 publish approval / release
  → PR3-C merge
  → sandbox image approval
  → PR3-D
  → sandbox template approval / proof
  → stop & review
```

No step may be started before its predecessor is complete. In particular: **PR3-C task 6 is blocked until `0.1.0` is published and verified**, and **PR3-D task 9 is blocked until the sandbox runs an image containing the pinned package**.
