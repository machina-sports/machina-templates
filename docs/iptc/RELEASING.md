# Releasing `machina-sports-canonical`

How the distribution built from `tools/iptc/canonical/` reaches PyPI, and the
decisions that are not this document's to make.

Automation: `.github/workflows/publish-machina-sports-canonical.yml`.
Proof suite: `tests/test_iptc_canonical_package.py`.

---

## ✅ RESOLVED — the owner license decision

**The owner has decided the license for this distribution.** This is the one
blocker on the list below that is closed. It closes nothing else.

The distribution is published under the exact aggregate expression:

```
MIT AND CC-BY-4.0
```

A conjunction, because both sets of terms apply to different members of the same
archive:

- **MIT** covers the Machina-authored Python runtime, the provider adapters and
  the build tooling. Copyright (c) 2026 Machina Sports.
- **CC-BY-4.0** attribution obligations cover two packaged assets:
  `official-property-names.json`, which is extracted and generated from IPTC
  Sport Schema 1.1, and `shared-context.json`, which is Machina-authored but
  reproduces that work's pinned namespace bindings.

CC BY is not placed over the software, and the software's MIT terms do not
discharge the attribution owed on those two assets.

### The upstream work being attributed

| | |
|---|---|
| Work | IPTC Sport Schema 1.1 |
| Creator | IPTC Sports Content Working Group |
| Copyright | Copyright (C) International Press Telecommunications Council 2024 |
| Source | `https://github.com/iptc/sport-schema/tree/0e77bf8678f3702fe81c28673bede35efe47d633` |
| Licence | `https://creativecommons.org/licenses/by/4.0/` |

The upstream ontology files are **not shipped**; what ships is derived from them.
Nothing anywhere claims IPTC endorsement, sponsorship or affiliation.

### What carries the decision

Three files, declared as `license-files` in `pyproject.toml` and shipped in both
the wheel (under `.dist-info/licenses/`) and the sdist:

| File | What it is |
|---|---|
| `LICENSES/MIT.txt` | the MIT text, byte-identical to the sibling `sports-skills/LICENSE` |
| `LICENSES/CC-BY-4.0.txt` | the official Creative Commons CC BY 4.0 legal code, verbatim |
| `NOTICE-IPTC.md` | the attribution notice, the file-level classification of both assets, and the MIT boundary |

The publish job's "Refuse to publish without the approved license" step reads the
built wheel's `METADATA` and requires the exact `License-Expression` above **and**
all three `License-File` entries. It no longer accepts the mere presence of a
license field: `MIT` alone, `CC-BY-4.0` alone, a reordered conjunction, an `OR`,
or a missing notice are each rejected, and each rejection is an executed case in
`tests/test_iptc_canonical_package.py`.

---

## 🛑 BLOCKED — the first upload still cannot happen

**Resolving the license does not unblock the release.** Four holds remain, and
every one of them is outside this repository or outside this process:

1. **The pypi environment is not configured.** The `pypi` environment does not
   exist with a required human reviewer, so nothing enforces the approval gate at
   run time.
2. **The trusted publisher is not registered.** PyPI has no pending publisher for
   this project, so an upload would fail authentication — and registering one is
   a deliberate act, not a release step.
3. **The renewed digests have not been independently verified.** The rows in
   `docs/iptc/machina-sports-canonical-0.1.0.sha256` were re-recorded when the
   license metadata changed the artefact bytes, and they were produced by the
   same process that recorded them. The earlier independent rebuild verified a
   candidate that predates the license metadata and is now superseded.
4. **No human has approved publication.** No owner has said "publish" having seen
   the renewed digests and a green proof.

**Do not publish** until all four are closed. A published version cannot be
replaced: uploading `0.1.0` prematurely spends the version number permanently.

---

## One-time setup, before any tag exists

### 1. Register the trusted publisher on PyPI

Trusted publishing (OIDC) is how this workflow authenticates. There is
**no API token** anywhere in this repository, and none may be added: a standing
credential outlives the release it was created for.

Because `machina-sports-canonical` does not exist on the index yet, this is
registered as a **pending publisher** (PyPI → *Your projects* → *Publishing* →
*Add a pending publisher*), with exactly these four values:

| Field | Value |
|---|---|
| PyPI project name | `machina-sports-canonical` |
| Owner / repository | this repository, as GitHub spells it |
| Workflow filename | `publish-machina-sports-canonical.yml` |
| Environment name | `pypi` |

All four are matched by PyPI at upload time. A mismatch fails the upload with an
authentication error, not with a helpful message — check them character by
character. The first successful upload converts the pending publisher into a
normal trusted publisher for the created project.

### 2. Create the `pypi` environment with a required reviewer

The workflow binds its publish job to the `pypi` environment, but the approval
itself is enforced by GitHub, not by any file in this repository. In
*Settings → Environments → `pypi`*:

- Enable **Required reviewers** and add at least one **human** reviewer who is
  authorized to approve a public release. Without this, the workflow uploads the
  moment a tag is pushed and there is no gate at all.
- Restrict the environment's deployment branches/tags to the release tag pattern.

The proof suite asserts the job names this environment; it cannot assert that the
environment requires a reviewer. Verify it by opening the settings page.

---

## Tag convention

```
machina-sports-canonical-v0.1.0
```

Distribution-scoped, because this repository also releases templates and a bare
`v0.1.0` would collide. The workflow triggers on `machina-sports-canonical-v*`,
and the build job fails if the tag names a version the build did not produce.

---

## Reproducible artefacts

The release is built once, by
`packaging/machina_sports_canonical/release.py`, with the release epoch in the
environment:

```sh
SOURCE_DATE_EPOCH=1786398569 \
  python packaging/machina_sports_canonical/release.py . dist
sha256sum dist/*.whl dist/*.tar.gz
```

`1786398569` is the committer timestamp of `cf433075666de002e38fb3bd6f5dd8743e7caeb2`,
the canonical source commit recorded in `tools/iptc/canonical/package-receipt.json`
— re-derivable with `git log -1 --format=%ct <commit>`, not an arbitrary constant.

Both halves are needed. `wheel` reads `SOURCE_DATE_EPOCH` and stamps every zip
entry with it; the sdist path ignores it entirely, so the helper rewrites the
builder's mtimes, uid, gid and umask out of the tar afterwards — payloads, member
list and member order untouched. Without this, two builds of one commit produce
two different digests and the comparison below is unperformable.

Build it with the interpreter the release job uses (Python 3.11) and the pinned
tooling from `requirements-iptc-build.txt`. `python -m build` on its own, without
the epoch, produces **irreproducible** archives — do not use it to generate
digests for review.

### The reviewed digests

`docs/iptc/machina-sports-canonical-0.1.0.sha256` holds the **reviewed 0.1.0
release candidate** digests, and it is the authority every automated comparison
diffs against:

| Artefact | SHA-256 |
|---|---|
| `machina_sports_canonical-0.1.0-py3-none-any.whl` | `c162c20514a3d3ad2d5f43e5392ce23fc52053edc44a4ed60599f0a2db6dd9bf` |
| `machina_sports_canonical-0.1.0.tar.gz` | `5ba1fcc65182cce58b40df478bf74e04937a4350dbe9fa3eebe0bfa2d7f1894e` |

These rows were **renewed for the license decision**. Declaring
`License-Expression`, three `License-File` fields and three archive members
changes both artefacts, so the digests recorded before that change are superseded
— see the section below, which keeps them and says so.

The file is written exactly as `sha256sum` writes it, with **basenames** and the
wheel before the sdist, so one checked-in file is comparable byte-for-byte with
what any job generates. Three places read it:

- Both **package-proof** matrix legs (Python 3.9 and 3.11) build a release into
  `$RUNNER_TEMP` and `diff -u` their digests against it. Before this file existed
  each leg only compared its own build with its own build, so the two
  interpreters could have been stably producing *different* bytes with both legs
  green. Cross-interpreter reproducibility is now falsifiable: a divergent
  interpreter fails its own job.
- `tests/test_iptc_canonical_package.py` asserts the artefacts the running
  interpreter builds hash to exactly these rows.
- The release **build** job diffs its own `SHA256SUMS` against it *before*
  uploading the artefact, so a release whose bytes are not the approved bytes
  never reaches the approval gate.

Reproduce them locally with the command above; the rows must match character for
character. **If the wheel bytes change for any reason, these digests are stale and
this file must be re-recorded as a reviewed change.** Adding the license metadata
is exactly such a change, and it is why these rows differ from the ones below.

### Independent verification — SUPERSEDED

**This section is superseded evidence. It verifies a candidate this repository no
longer builds.** It is kept, rather than deleted, because a releaser is entitled
to see that the method works and that the pre-license candidate really was
reproduced elsewhere. It does not vouch for the renewed rows above — nobody has
rebuilt those independently, which is outstanding hold 3.

Every automated comparison above diffs a build against rows this repository
checked in, which proves the rows are stable — not that anyone other than the
process that wrote them ever reproduced them. The pre-license candidate was
reproduced once, outside that process, before any approval:

- **Candidate:** `f46799c`, the exact commit those digests were recorded for. It
  predates the license metadata.
- **Source:** obtained with `git archive f46799c` into separate isolated
  temporary trees, so no working tree, build cache or untracked file could
  contribute bytes.
- **Environment:** fresh disposable virtual environments, each installing the
  checked-in `requirements-iptc-build.txt` unchanged.
- **Build pins:** `build==1.4.4`, `setuptools==82.0.1`, `wheel==0.47.0`,
  `packaging==26.3`, `pyproject-hooks==1.2.0`, `importlib-metadata==8.7.0`,
  `tomli==2.2.1`, `zipp==3.23.0` and `colorama==0.4.6`, with the checked-in
  environment markers unchanged.
- **Interpreters:** Python **3.9.25** and Python **3.11.14**, each running
  `packaging/machina_sports_canonical/release.py` with
  `SOURCE_DATE_EPOCH=1786398569`.

Each interpreter independently produced the **superseded** digests — the bytes
`f46799c` built, before any license metadata existed:

| Artefact (superseded) | SHA-256 |
|---|---|
| `machina_sports_canonical-0.1.0-py3-none-any.whl` | `3c7fcbc539824ced118099f691ac23c3182c59ad0855aaec560d43dabb53361b` |
| `machina_sports_canonical-0.1.0.tar.gz` | `11783dd7fff89b634e55bccdd17952679b8f7362fe9fd0bfa8a378a5dbe8d324` |

Those two rows are **not** what
`docs/iptc/machina-sports-canonical-0.1.0.sha256` holds today. At the time they
matched that file byte for byte, and matched each other. The temporary trees and
environments were removed; this repository's working tree was not modified.

**This is pre-approval evidence. It is not release approval.** It says the
then-reviewed digests are what `f46799c` builds on an independent machine across
both proven interpreters, and nothing more. It is not an owner's decision to
publish, it does not stand in for the required reviewer on the `pypi`
environment, and it is not a license decision — the owner made that separately,
and this rebuild neither made it nor carries it. The 🛑 block above still holds.

---

## 🛑 Human release checkpoint

Everything above can be prepared and reviewed. Publishing may not begin until an
owner explicitly approves the release, having seen:

- the built wheel and sdist SHA-256 digests,
- a green package proof on Python 3.9 and 3.11,
- and the license decision recorded and merged.

There is no automated path around this checkpoint. The `pypi` environment's
required reviewer is what enforces it at run time.

---

## Release order

Do these in order. Each step depends on the one before it.

1. **Merge the pull request** into the default branch. Tagging an unmerged branch
   releases a commit that is not on the default branch, and the tag is what the
   published artefact is traced to for ever.
2. **Push the tag** on the merge commit:
   ```sh
   git tag machina-sports-canonical-v0.1.0
   git push origin machina-sports-canonical-v0.1.0
   ```
   This starts the workflow. The `build` job builds, checks the tag against the
   built version, records `SHA256SUMS` and uploads the artefact. It has no upload
   scope.
3. **Read the digests** in the `build` job log and compare them with
   `docs/iptc/machina-sports-canonical-0.1.0.sha256`. That job already diffed them
   against that file and would have failed on a mismatch, so this is a
   confirmation rather than the only check — but confirm it. If they are not
   identical, **stop** — do not approve.
4. **Approve the** deployment to the `pypi` environment. Only now does the
   `publish` job run: it downloads the reviewed artefact, verifies it with
   `sha256sum --check --strict SHA256SUMS`, applies the license gate, and uploads.
   It never rebuilds — publishing a rebuild publishes bytes nobody approved.
5. After `publish` succeeds, the `release` job downloads that same named workflow
   artefact, verifies `SHA256SUMS` again, and creates the GitHub Release for
   `machina-sports-canonical-v0.1.0`. It never checks out or rebuilds the source.
   Because it needs a successful `publish`, no GitHub Release is created for a
   distribution PyPI rejected.

---

## After publishing

1. Open the repository's Releases page and verify an actual **GitHub Release
   exists** for the exact tag `machina-sports-canonical-v0.1.0`.
2. Verify its uploaded assets contain **exactly three attachments** (GitHub's
   automatically generated source-code links are not uploaded attachments):
   - `machina_sports_canonical-0.1.0-py3-none-any.whl`
   - `machina_sports_canonical-0.1.0.tar.gz`
   - `SHA256SUMS`
3. Download those three attachments into a clean directory and run
   `sha256sum --check --strict SHA256SUMS`. Both distribution files must pass;
   this proves the GitHub Release exposes the exact bytes the build job hashed.
4. `https://pypi.org/pypi/machina-sports-canonical/json` returns `0.1.0`.
5. **Compare** the `digests.sha256` values in that JSON, for both the wheel and
   the sdist, against `SHA256SUMS` from the approved run. They must match exactly.
   A mismatch means what PyPI serves is not what was approved.
6. Verify a **clean** install from the index, in a throwaway virtual environment
   with nothing else in it:
   ```sh
   pip install machina-sports-canonical==0.1.0
   python -c "import machina_sports_canonical"
   ```
   Then repeat the offline resource case the proof suite covers — load
   `shared-context.json` and `official-property-names.json` through the installed
   package, from a directory outside this repository.

Only when all six pass is the version usable as a pin.

---

## When it goes wrong

**A published version cannot be replaced.** Deleting a release on PyPI does not
free its version number: `0.1.0` can never be re-uploaded with different bytes.

- **Before the upload** — any failure, at any step, is cheap. Fix it, rebuild,
  re-review the digests. Never approve past a failing gate.
- **After the upload** — if post-publish verification fails, **yank** `0.1.0`
  (which leaves it installable for existing exact pins but hides it from
  resolution) and ship `0.1.1` with the fix. Yanking plus `0.1.1` is the recovery;
  re-uploading `0.1.0` is not possible, and pretending the release is fine because
  it installed is how a bad pin spreads.
- **Do not proceed to the client runtime pin** on a release whose verification
  failed. A pin is only as good as the artefact it names.
- **Name collision at publish time** — the name being unclaimed when this was
  planned does not reserve it. If the upload fails on an existing project, stop
  and escalate; do not improvise a different distribution name during a release.
