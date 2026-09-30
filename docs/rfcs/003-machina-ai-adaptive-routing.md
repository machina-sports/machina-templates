# RFC 003 — machina-ai adaptive routing: native vs Vercel AI Gateway vs NVIDIA NeMo Switchyard

| | |
|---|---|
| **Status** | **Research.** No production decision is made by this document. |
| **Tracking** | ClickUp `86ajz5tdp` — "Avaliar roteamento adaptativo no machina-ai com NeMo Switchyard" |
| **Baseline** | `connectors/machina-ai/machina-ai.py` (intelligent router v1, this repository, `main`) |
| **Switchyard pin** | `https://github.com/NVIDIA-NeMo/Switchyard` @ `b256d936f1d77bf13ec9bec399ea0a253e07ca05` (2026-08-13); released wheel `nemo-switchyard==0.2.0` (PyPI, 2026-08-10); Apache-2.0 |
| **Vercel docs pin** | `vercel.com/docs/ai-gateway/*` pages, `last_updated` 2026-07-28 → 2026-08-01, fetched 2026-08-13 |
| **Executable form** | `spikes/adaptive-routing/` — three runners over one workload set; committed results in `spikes/adaptive-routing/results/` |
| **Related** | `docs/intelligent-router-spec.md` (router contract this RFC extends, esp. §12 routing decision engine) |

---

## 0. The boundary this document does not cross

**This is research.** Nothing in this RFC authorizes implementing, enabling, or
deploying an external routing dependency in any environment.

Three invariants hold for every option evaluated here, without exception:

1. **Workflows and templates never own routing.** No provider, model-vendor,
   credential, endpoint, fallback, or remap fields in committed YAML.
   `scripts/check-machina-ai-policy.py` and `scripts/check-no-openai.sh all`
   stay green and structurally enforce this; weakening either lint is out of
   scope for any adaptive-routing work.
2. **`PolicyEngine` remains the final gate.** Whatever produces a route
   *suggestion* — a profile table, an escalation heuristic, a Switchyard
   algorithm — the suggestion is validated against operator-owned
   provider/model/endpoint/credential policy before any adapter executes.
   A decision backend can only pick among candidates policy already allows.
3. **Fail closed.** Protected routes (NVIDIA NIM, `openai_compatible`) keep
   their fail-closed semantics; no decision layer may convert a policy
   rejection into a cross-provider retry.

**NVIDIA NeMo Switchyard is pre-alpha.** Its own README states, verbatim:

> "Switchyard is pre-alpha software that is evolving rapidly. The API and
> algorithms are expected to change significantly before we reach v1.0."

> "Experimental software. Not for production use."

(`README.md`, "Maturity" section, at the pinned commit; the PyPI package also
declares `Development Status :: 3 - Alpha`.) Switchyard is therefore evaluated
here **as a design reference and sandbox spike only**, blocked for production
by its own upstream declaration until §8's criteria are met.

---

## 1. Problem

The `machina-ai` router on `main` is a **static policy router**: it resolves
profile → provider/model deterministically and per-call. It is not an
**adaptive decision router**: nothing about task difficulty, output quality,
failure history, or session trajectory changes the next decision.

Evidence (all in `connectors/machina-ai/machina-ai.py`):

- `PolicyEngine._profile_candidate` returns `candidates[0]` of the profile —
  first allowed candidate, no scoring: the profile list shape suggests ranked
  alternatives, but only index 0 is ever chosen.
- `DEFAULT_CONFIG` ships `remaps: {}` and `fallbacks: {}` — the adaptive-ish
  hooks exist in the contract but are empty by default.
- Defaults are Vertex-backed (`chat`/`search_answer` → `gemini-2.5-flash`,
  `embedding` → `text-embedding-004`, transcription → Google Speech);
  `vertex_anthropic` ships dormant for a controlled canary; `nvidia_nim` is
  protected/fail-closed.
- Receipts already emit decision metadata (`selected_provider`,
  `selected_model`, `route_reason`, `fallback_used`, `fallback_attempts`) —
  the observability substrate an adaptive layer would need is present.

What adaptive routing would buy, per the published ecosystem results the
research request cited (NVIDIA Switchyard blog): escalation routing between a
cheap and a frontier model reported ~74% cost reduction using the frontier on
~7% of calls (~6 accuracy-points tradeoff, LangChain case) and staged routing
reported near-frontier performance at ~28% lower average cost
(Cognition/Devin case). Those are *their* numbers on *their* workloads — this
RFC treats them as motivation, not as evidence for ours.

The question this research answers: **where should the decision logic live,
and which mechanics layer (if any) should execute it** — native code in
`machina-ai`, the Vercel AI Gateway, or Switchyard?

---

## 2. Option A — native `machina-ai` (baseline, measured)

`spikes/adaptive-routing/run_native.py` runs the real router with mocked
adapters (zero provider time), so latency isolates router overhead. Results in
`spikes/adaptive-routing/results/native.json`:

- **Routing overhead:** p50 **29–45 µs** per call across the 8 workloads
  (p95 ≤ ~66 µs, 200 iterations each). Decision cost is negligible against any
  model call; there is no performance argument for an external decision layer.
- **Static selection, proven:** 50 repeats per workload always resolve the
  same `(provider, model, route_reason)` — `distinct_routes_over_repeats: 1`
  for all workloads.
- **Fallback observability works when configured:** with a configured
  `fallbacks.chat.vertex_ai → groq` chain and an induced transient failure,
  the receipt records `route_reason: "fallback:vertex_ai:1"`,
  `fallback_used: true`, and a sanitized `fallback_attempts[]` entry
  (`error_class: provider_unavailable`).
- **The escalation gap, demonstrated:** after 3 consecutive primary failures,
  the *next* call still routes to the static primary
  (`route_reason: "profile:balanced"`, `fallback_used: false`). Router state
  is per-call; there is no cross-call signal, memory, or escalation. This is
  the specific capability adaptive routing would add.

**Cost:** no new vendor, no new deployment, no new dependency. The work is
code we own, gated behind config that defaults to today's behavior.

---

## 3. Option C — NVIDIA NeMo Switchyard (pinned, spiked decision-only)

### 3.1 What it is

Three surfaces over one Rust core (upstream docs at the pinned commit):

- **`switchyard-server`** — standalone Rust HTTP proxy exposing OpenAI Chat
  Completions, OpenAI Responses, and Anthropic Messages, translating any of
  the three formats to any route. Install: `cargo install --locked switchyard-server`.
- **`switchyard-libsy`** — embeddable decision library: *"It never calls a
  model itself: an algorithm decides which target to use and hands every model
  call back to you"* (README). Python bindings ship in the
  `nemo-switchyard` wheel (`switchyard.libsy`, PyO3/abi3).
- **Python launcher** for coding agents (not relevant to us).

Routing algorithms: `passthrough`, `random` (weights/seed), `llm_classifier`
(capability / custom / **escalation** modes — all need a judge LLM),
`stage_router` (deterministic on tool-result signals, optional classifier
assist), plus custom algorithms via the Rust trait. Escalation mode reacts to
real trajectory (weak-first, judge confirms, streak latches the session to the
strong target) and **requires a session identity header** to latch. Session
affinity is **process-local, in-memory** — no external store.

**Compatibility notes against our contract:** no embeddings surface (no
`/v1/embeddings`; chat-shaped protocols only), streaming/tools/structured
output supported in translation, telemetry is content-free by design
(Prometheus, GenAI OTel spans, optional JSONL routing log; *"The labels never
include request or response text."*).

### 3.2 Maturity evidence (why production is blocked)

- The two README quotes in §0, plus `Development Status :: 3 - Alpha` on PyPI.
- Version `0.2.0` everywhere (Cargo workspace + wheel); first crates.io
  publish of the server was 2026-08-10 — days old at evaluation time.
- **Known issues, upstream `docs/known_issues.md` (0.2.0), verbatim:**
  1. "Buffered upstream work continues after the client disconnects, so a
     cancelled request can still incur provider cost."
  2. "Routing-tier attribution is missing from `GET /v1/stats` and `/metrics`
     for LLM-classifier judge failures that route to the default target,
     escalation decisions, and `stage_router` fallback decisions."
  3. "The retry recovery counter stays at zero after a successful upstream retry."
  4. "`x-switchyard-session-id` is not recorded in native session stats."
  5. "The native server does not send the documented `X-Switchyard-Version`
     header upstream."
- **API churn observed live during this spike:** the released 0.2.0 wheel
  emits decision key `selected_model`; repo HEAD — two days after that release
  — has already renamed it to `selected_model_id`
  (`crates/switchyard-py/src/libsy_bindings.rs`). Pre-alpha churn is not
  hypothetical; it hit this spike.

License is clean Apache-2.0 (no NVIDIA riders found; NIM is an optional
backend, not a requirement; no GPU needed for the proxy).

### 3.3 Spike results (decision-only, offline, real Rust code)

`spikes/adaptive-routing/run_switchyard.py` exercises `switchyard.libsy` with
fake host clients (zero network/spend) — the **only integration shape
compatible with our invariants**, because the host keeps executing the calls
and `PolicyEngine` stays between decision and execution. Results in
`spikes/adaptive-routing/results/switchyard.json`:

- **Decision overhead:** `random` p50 ~**90–93 µs** per decision (200
  iterations/workload). Same order of magnitude as our whole router; the real
  cost of adaptive routing is not the algorithm, it is the judge model call.
- **Classifier threshold behaves as documented:** fake judge verdict
  `p_solve 0.2` (< `base_threshold` 0.5) → `capable-model`; `p_solve 0.9` →
  `efficient-model`.
- **Session affinity works:** second call with the same
  `x-switchyard-session-id` skips the judge (verified via judge call count).
- **Embeddings/search workloads: skipped** — no Switchyard surface for them;
  any adoption would still leave embeddings/transcription/media on our router.

### 3.4 Operational shape if ever adopted

- **As proxy:** a new Rust service to deploy, monitor, and page on — per
  cluster or per tenant — plus the platform's first Rust operational surface.
- **As libsy in `client-api`:** blocked by a platform constraint — pyscript
  connectors execute in-process in `client-api`, so `nemo-switchyard` (a
  native PyO3 extension, pre-alpha) would enter the `client-api` requirements
  and its blast radius would be every tenant at once. Not acceptable at this
  maturity. A sandboxed sidecar/venv is the only defensible spike shape.

---

## 4. Option B — Vercel AI Gateway (docs-verified; live spike gated)

### 4.1 What it is (and is not)

A managed **mechanics layer**: unified endpoint (`ai-gateway.vercel.sh`),
model catalog, protocol compatibility (AI SDK, OpenAI Chat Completions +
`/embeddings`, OpenAI Responses, Anthropic Messages), provider routing with
health-aware defaults, ordered model fallbacks, BYOK, observability, spend
controls.

**It is not an adaptive router.** Vercel's own guidance
(KB: *How to build your own AI model router*; *Cost-aware model routing*):

> "Keep routing, key, and retention decisions in your code while the gateway
> handles provider integrations, failover, and cost metering."

> "The classifier is the part you own."

Difficulty/quality-based selection stays app-owned under every option — which
means adopting the gateway **does not remove any of the decision work**; it
only replaces execution mechanics our adapters already do.

### 4.2 Facts that gate adoption (all from official docs, fetched 2026-08-13)

- **Pricing:** "AI Gateway charges no markup and no platform fee on tokens.
  You pay the provider's list price" (paid tier, prepaid credits). Free tier:
  subset of models, lower per-model rate limits (429s), monthly free credit
  (value not published).
- **BYOK — the critical behavior:** BYOK requires the paid tier and adds no
  markup, **but**: "When a request with your credentials fails, AI Gateway
  keeps it running by falling back to system credentials, and that fallback
  usage is billed against your credits balance." No documented toggle to
  disable this fallback was found, and "a budget can't be used to cap BYOK
  spend." **This silently violates our credential-binding policy** (spec §15:
  a route's credential must not be swapped for another) — until Vercel exposes
  a verified off-switch, BYOK is incompatible with our fail-closed posture.
- **Routing Rules (team-wide rewrite/deny) are beta**, verbatim: "AI Gateway
  routing rules are in beta and may change before general availability. Avoid
  relying on them in production."
- **Model fallbacks are static ordered lists** (`models` array): exhaust a
  model's providers, then try the next model; triggers on failure/
  unavailability only — never on difficulty or quality.
- **Provider controls:** `only` (allowlist, free per-request), `order`,
  `sort: cost | ttft | tps`; default selection is health-aware
  (uptime/latency). Receipts expose `resolvedProvider`, per-attempt audit,
  `cost`/`marketCost`.
- **Retention:** gateway itself does not retain prompts/outputs; provider-side
  ZDR is opt-in — per-request free, team-wide **$0.10/1k requests**
  (Pro/Enterprise), fails closed when no compliant provider exists.
- **Add-on surcharges to model in any cost picture:** Custom Reporting
  ($0.075/1k writes, $5/1k queries), team-wide provider allowlist ($0.10/1k),
  Trace Drains (metered outside credits, no Pro allowance), payment
  processing fees (rate unpublished).
- **No published AI Gateway SLA** was found (status page shows a dedicated
  component; Enterprise plan lists SLAs generically).

### 4.3 Spike status

`spikes/adaptive-routing/run_vercel.py` runs the same workloads live
(chat + embeddings + static fallback probe) and **skips cleanly without
`AI_GATEWAY_API_KEY`** — the committed result is an explicit `SKIPPED` record.
Live numbers require an operator-provided key on a controlled account and are
deliberately not fabricated here. The BYOK fallback behavior must be validated
on that controlled account before any adoption conversation.

---

## 5. Comparison

| Dimension | A — native | B — Vercel AI Gateway | C — Switchyard |
|---|---|---|---|
| Maturity | Shipped on `main`; 103 tests green | GA product; Routing Rules beta ("avoid in production") | **Pre-alpha**; "Not for production use."; live API churn observed |
| Adaptive decision (difficulty/quality/trajectory) | Absent today; buildable behind policy | **Not provided** — app-owned by their own guidance | Core feature (classifier/escalation/stage), needs judge LLM + session identity |
| Who executes model calls | Our adapters | Vercel | Proxy mode: Switchyard; libsy mode: **our adapters** (compatible shape) |
| PolicyEngine survives intact | Yes | Partially — BYOK system-credential fallback bypasses credential binding; no documented off-switch | Yes, in libsy decision-only shape |
| Embeddings / transcription / media | Yes (contract v1) | Embeddings yes; media partial | **No** — chat-shaped only |
| New operational surface | None | SaaS dependency + credits + surcharge matrix | Rust proxy to run, or pre-alpha native ext in-process (blocked) |
| Decision observability | Receipts (`route_reason`, `fallback_attempts`) | Gateway logs/receipts, trace drains (metered) | Headers + Prometheus + OTel; tier attribution incomplete (known issue #2) |
| Content retention | Content-free receipts by default | Gateway retains none; provider ZDR opt-in ($) | Content-free by design |
| Marginal cost | Engineering only | List-price tokens; surcharges for team-wide controls | Infra/on-call + judge-model tokens |
| Measured this spike | ✅ overhead 29–45 µs p50; static proof; fallback receipt | ⏸ gated (needs key) | ✅ decision 90–93 µs p50; threshold + affinity verified |

---

## 6. Where the pieces belong (research hypothesis)

1. **The decision layer belongs in `machina-ai`.** All three sources agree by
   elimination: Vercel says classifier/escalation is app-owned; Switchyard's
   only invariant-compatible shape (libsy) returns the decision to the host
   anyway; and our receipts/policy substrate already exists. The next
   increment is the spec's §12 engine grown one notch: a `router_strategy`
   policy key (`static` default | `escalation` | `stage` | `classifier`),
   semantic route targets (`cheap_chat` / `balanced_chat` / `frontier_chat` /
   `private_runtime`), objective escalation signals (repeated transient
   failures, malformed structured output, explicit complexity flag,
   long-context need), richer receipts (`router_strategy`, `candidate_pool`,
   `decision_reason`, `session_affinity_key`, `cost_class`, `latency_class`)
   — everything operator-config, default off, committed workflows unchanged.
2. **Switchyard is a design reference now, a possible decision backend later.**
   Its escalation/stage semantics (latching, confirmations, fail-open-to-strong,
   session affinity) are the best-documented designs we found and directly
   inform (1). A `decision_backend: switchyard` config could be revisited
   in sandbox once §8 criteria are met.
3. **Vercel AI Gateway is an optional mechanics experiment, per-tenant, later.**
   It would sit *behind* `machina-ai` as an execution target, never as
   workflow-visible policy. It only becomes interesting if we want catalog
   breadth/failover without operating adapters — and only after the BYOK
   fallback is proven controllable on a controlled account.
4. **Quality evals precede any tunable router.** Without per-task
   traces/evals (prompt class, route, outcome quality, latency, usage), a
   learned router is a guess. Evals are a prerequisite line item, not part of
   this RFC's scope.

---

## 7. Reproducible spike protocol

One workload set (`spikes/adaptive-routing/workloads.jsonl`: 6 chat including
JSON-extraction and long-context shapes, 1 embedding, 1 search), three runners,
one results schema, committed real results only:

- `run_native.py` — always runnable; mocks adapters, measures the real router.
- `run_switchyard.py` — needs `nemo-switchyard==0.2.0` in a **disposable
  sandbox venv** (never `client-api`); decision-only with fake host clients;
  records pin + skips embeddings/search with the reason.
- `run_vercel.py` — live; requires `AI_GATEWAY_API_KEY`; consumes credits;
  writes `SKIPPED` without one. Supports `--only vertex` to demonstrate
  provider restriction at no surcharge.

Remaining to execute before any decision meeting: (a) Option B live run on a
controlled paid-tier account incl. BYOK-failure probe, (b) a real-judge
escalation run for Option C in sandbox (adds judge tokens/latency to the
decision cost picture), (c) quality evals per §6.4.

---

## 8. Recommendation (go/no-go), risks, rollback

### Go/no-go

- **Switchyard in any production path: NO-GO.** Blocked by upstream's own
  maturity declaration, open known issues (notably post-disconnect provider
  spend and incomplete routing-tier attribution), and API churn we observed
  directly. **Re-evaluate when ALL of:** a stable (≥ v1.0 or explicitly
  production-blessed) release exists; the §3.2 known issues relevant to spend
  attribution and session stats are closed upstream; decision API is stable
  across two consecutive releases; and our sandbox spike reproduces with a
  real judge under pinned versions.
- **Vercel AI Gateway as default mechanics: NO-GO now.** The BYOK
  system-credential fallback (unswitchable per current docs, uncapped by
  budgets) conflicts with fail-closed credential binding; team-wide Routing
  Rules are beta by their own warning; and the gateway adds no adaptive
  capability we lack. **Conditional sandbox-go:** a controlled paid-tier
  account spike (no BYOK, `only` + ZDR validation, live latency/cost
  receipts) is cheap and worth running to keep the option honestly priced.
- **Native `router_strategy` escalation increment in `machina-ai`: GO for
  design + offline spike** (as research follow-up). It is the smallest change
  that closes the demonstrated escalation gap, keeps every invariant, adds no
  vendor, and its telemetry then produces the dataset that would justify (or
  kill) any external decision backend.

### Risks

1. **Pre-alpha dependency risk (C):** API/algorithm churn (observed), unowned
   security posture, post-disconnect spend (known issue #1).
2. **Policy bypass risk (B):** BYOK fallback silently re-executes with
   Vercel's credentials and bills credits; budgets don't cap it.
3. **In-process blast radius:** any decision-backend library imported by
   `client-api` ships to every tenant; sandbox-only until stability is proven.
4. **Judge-cost blindness:** classifier/escalation adds a model call per
   unlatched turn; without receipts for judge usage, "cheaper routing" can be
   net-negative. Receipts must attribute judge tokens explicitly.
5. **Eval-free tuning:** adopting any learned/tunable router before task-level
   evals exist would optimize noise.

### Rollback plan (applies to any future enablement)

Adaptive routing ships **config-only, default off**: `router_strategy: static`
remains the shipped default; enabling `escalation`/`classifier` (or a
`decision_backend`) is an operator runtime-policy change per environment.
Rollback is therefore a single config flip back to `static` — no template
reinstall, no workflow edits, no redeploy of committed YAML. Receipts must
record `router_strategy` + `decision_reason` on every call so any enablement
window is fully auditable after rollback. Protected routes (NIM) are exempt
from every strategy: fail-closed behavior is not overridable by a decision
backend.

### Guardrails verification (this branch, with the spike in-tree)

- `connectors/machina-ai/tests/` — **103 passed**.
- `scripts/check-no-openai.sh all` — exit 0.
- `python3 scripts/check-machina-ai-policy.py` — exit 0.

---

## 9. References

- Switchyard repo (pinned `b256d936f1d7`): README "Maturity";
  `docs/known_issues.md`; `docs/core_concepts.md`; `docs/getting_started.md`;
  `crates/libsy/README.md`; `docs/routing_algorithms/*`;
  `crates/switchyard-server/README.md`; `docs/internal/metrics_reference.md`.
- NVIDIA blog — *Route AI Agent Workloads Across Models with NVIDIA NeMo
  Switchyard* (benchmark claims cited as motivation only).
- Vercel docs (fetched 2026-08-13): `ai-gateway` overview; `pricing`;
  `models-and-providers/provider-options`, `provider-filtering-and-ordering`,
  `model-fallbacks`, `routing-rules`; `authentication-and-byok/byok`;
  `security-and-compliance/zdr`; `observability-and-spend/observability`,
  `trace-drains`; `sdks-and-apis/openai-chat-completions`; KB guides *build
  your own AI model router* and *cost-aware model routing*.
- This repo: `connectors/machina-ai/machina-ai.py`;
  `connectors/machina-ai/tests/`; `scripts/check-machina-ai-policy.py`;
  `scripts/check-no-openai.sh`; `docs/intelligent-router-spec.md`; `CLAUDE.md`.
- Spike artifacts: `spikes/adaptive-routing/` (runners, workloads, committed
  results).
