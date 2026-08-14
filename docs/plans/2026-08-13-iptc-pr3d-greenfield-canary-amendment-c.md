# Revised PR3-D — greenfield canonical canary (Approved Amendment C)

**Additive scope note.** Companion to
`docs/plans/2026-08-10-iptc-pr3-canonical-runtime-wci-provider-substitution.md`,
which stays as the historical approved plan. This note does not rewrite it; it
records what Amendment C replaced and what revised PR3-D actually builds.

**Authority:** the greenfield canonical-adoption amendment approved by the
project owner on 2026-08-13. Where that amendment and the 2026-08-10 plan
disagree, the amendment wins.

---

## 1. What changed and why

The Task 13 assessment of the in-flight PR3-D work found that satisfying the
historical World Cup document shape — a flat `provider_ids` dict and competitor
`@id` compatibility — needed either a design exception to the frozen canonical
layer or a wider legacy migration than PR 3 authorizes. Amendment C takes the
third option: **do not mutate the historical runtime at all.** The World Cup is
finished, so that runtime is regression evidence, not a migration target.

**Superseded** (only the WCI-mutating instructions): the WCI-mutating parts of
§B7, §B11, §B12, and the PR3-D entry in §B15/§B17 — concretely, plan tasks 11–15
as written. Nothing in the frozen Background, Design, Trade-offs, Verification or
Non-goals sections is modified, and Amendments A and B are untouched.

**Retained unchanged** (§C3): the released `machina-sports-canonical` 0.1.0
package; the client-api runtime pin; a thin shared connector with no canonical
logic and exactly four public operations; fail-closed provider/capability/rights
preflight; zero provider calls on refusal; `event_view` by default with
`sport_schema_graph` opt-in; `capabilities`, `rights` and `provenance` on every
path; no provider fields above the seam.

## 2. What revised PR3-D builds

A minimal canonical-first canary template, `machina-sports-canonical-canary`,
instead of repointing any existing consumer. One unchanged workflow source is
exercised across `sports-skills`, API-Football, Sportradar and Opta synthetic
equivalent fixtures. Amendment B's closed allowed-difference set (§B11) is
enforced unchanged.

The migration-guide deliverable is **replaced by a forward adoption guide**
(§C6): new consumers start from the canonical envelope, the historical runtime
stays untouched, and **no legacy alias-removal programme is implied**.

## 3. Task map for revised PR3-D

| Old task | Disposition |
|---|---|
| 9, 10 — shared connector + fail-closed preflight | **Retained**, re-scoped review only. Greenfield-compatible: no consumer-specific path, name or vocabulary. |
| 11 — resolver workflow | **Discarded.** It resolved against a historical crosswalk document. |
| 12 — compatibility projection | **Discarded.** §C2 builds no legacy alias projection. |
| 13 — ingest rewire | **Discarded.** §C2 performs no ingest migration. |
| 14 — read-seam repoint | **Discarded.** §C2 performs no read-seam migration. |
| 15 — four-provider proof | **Retained, re-pointed** at the canary template. |
| 16, 17 — audit, stop/review | Unchanged, per §C7 steps 4–7. |

New work: the canary template and its one workflow, and the forward adoption
guide.

## 4. Order (§C7, strict)

1. Re-scope tests and artifacts (§C8).
2. Build `machina-sports-canonical-canary`.
3. Run the four-provider offline proof (§C4).
4. Full audit against §C3, §C4, §C6.
5. **Explicit sandbox template-import approval from the project owner.**
6. Fantasy sandbox import and execution (§C5), on the already-verified PR3-C
   digest `sha256:ced159b21c95089f8175db16555874a40ec7cb82b7ca0c5f0969e5cdf457f13d`.
7. Stop and review.

Steps 5 and 6 are approval gates, not continuations. No production deployment
under any circumstance.

## 5. Definition of done

Remains **9 of 12**. Conditions 10, 11 and 12 are discharged as §C6 states:
condition 10 by a **no-mutation proof** for the inventoried legacy consumers plus
greenfield canary behaviour — *not* by a historical migration; condition 11 by
the fresh Fantasy canary template installation and execution; condition 12 by the
forward adoption guide.

## 6. Scope honesty

The four-provider proof is **synthetic**. It establishes shape and behaviour at
the **prototype tier**. It is not live provider parity and it is not a rights
position: every adapter reachable through the seam emits `prototype_only`
evidence, so every production-tier request refuses (§B10, §A8).
