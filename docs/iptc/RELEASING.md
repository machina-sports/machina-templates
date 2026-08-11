# Releasing `machina-sports-canonical`

How the distribution built from `tools/iptc/canonical/` reaches PyPI, and the two
decisions that are not this document's to make.

Automation: `.github/workflows/publish-machina-sports-canonical.yml`.
Proof suite: `tests/test_iptc_canonical_package.py`.

---

## 🛑 BLOCKED — the first upload cannot happen yet

**Nothing may be uploaded to PyPI until the owner explicitly chooses and approves
license metadata for this distribution.**

This repository has no root `LICENSE` file, so the package declares no license.
Packaging must not invent one. `sports-skills` publishing the same canonical bytes
under MIT is *evidence about another repository* — it is not authorization to
relicense this source, and no automated step here may treat it as one. The IPTC
`LICENSE.md` under `agent-templates/iptc-mappings/references/` covers the pinned
upstream ontology bytes only and does not cover this code.

Until an owner decides:

- The publish job **fails closed** at its "Refuse to publish without an approved
  license" step. It reads the built wheel's `METADATA` and requires either a
  `License-Expression` or a `License-File` field. Today the wheel has neither, so
  a tagged run reaches the approval gate and then stops before the upload action.
- That is intentional. The workflow is committed *in the blocked state* so the
  release path is reviewable now and the decision is not rushed to unblock it.

To unblock, an owner must decide — as a reviewed change, not as part of a release:

1. Which license the distribution is published under.
2. Whether a `LICENSE` file is added to this repository, or the metadata carries a
   `License-Expression` alone.

Then the license metadata is added to `pyproject.toml` in its own pull request,
`tests/test_iptc_canonical_package.py` is updated to assert the approved value,
and the digests below are re-recorded because the wheel bytes change.

A published version cannot be replaced. Uploading `0.1.0` under no license, or
under the wrong one, spends the version number permanently.

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
3. **Read the digests** in the `build` job log and compare them with the digests
   reviewed at the checkpoint above. They must be identical. If they are not,
   **stop** — do not approve.
4. **Approve the** deployment to the `pypi` environment. Only now does the
   `publish` job run: it downloads the reviewed artefact, verifies it with
   `sha256sum --check --strict SHA256SUMS`, applies the license gate, and uploads.
   It never rebuilds — publishing a rebuild publishes bytes nobody approved.

---

## After publishing

1. The GitHub release/run references the uploaded artefacts, and the publish job
   printed their hashes.
2. `https://pypi.org/pypi/machina-sports-canonical/json` returns `0.1.0`.
3. **Compare** the `digests.sha256` values in that JSON, for both the wheel and
   the sdist, against `SHA256SUMS` from the approved run. They must match exactly.
   A mismatch means what PyPI serves is not what was approved.
4. Verify a **clean** install from the index, in a throwaway virtual environment
   with nothing else in it:
   ```sh
   pip install machina-sports-canonical==0.1.0
   python -c "import machina_sports_canonical"
   ```
   Then repeat the offline resource case the proof suite covers — load
   `shared-context.json` and `official-property-names.json` through the installed
   package, from a directory outside this repository.

Only when all four pass is the version usable as a pin.

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
