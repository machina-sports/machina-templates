# Adaptive-routing spike — machina-ai native vs Vercel AI Gateway vs NVIDIA NeMo Switchyard

> **RESEARCH ONLY.** ClickUp `86ajz5tdp` / [RFC 003](../../docs/rfcs/003-machina-ai-adaptive-routing.md).
> Nothing here is wired to workflows, template installs, or any production path.
> Switchyard is pre-alpha upstream: *"Experimental software. Not for production use."*

One shared workload set ([workloads.jsonl](workloads.jsonl)), three runners, one
results schema. Each runner writes real measurements to `results/` — a runner that
cannot run (missing key/package) writes an explicit `SKIPPED` report instead of
numbers. **No estimated numbers are ever presented as benchmark results.**

| Runner | Option | Needs | Mode | Status in `results/` |
|---|---|---|---|---|
| [run_native.py](run_native.py) | A — native `machina-ai` router | nothing (stdlib + pyyaml for the connector) | offline, mocked adapters | RAN — real router code, real overhead numbers |
| [run_vercel.py](run_vercel.py) | B — `machina-ai` + Vercel AI Gateway | `AI_GATEWAY_API_KEY` (live spend) | live HTTP | SKIPPED until an operator runs it with a key |
| [run_switchyard.py](run_switchyard.py) | C — `machina-ai` + Switchyard libsy | `pip install nemo-switchyard==0.2.0` | offline, decision-only, fake host clients | RAN — real Rust decision code, faked model calls |

## What each measures

- **A (native)**: routing overhead per call (normalize→policy→dispatch→receipt),
  static-selection proof (`candidates[0]`), fallback observability under induced
  transient failure, and the escalation gap (no cross-call adaptive state).
- **B (Vercel)**: end-to-end latency/tokens through the gateway, resolved
  provider, and the static ordered `models` fallback chain. Adaptive
  (difficulty/quality) routing is app-owned per Vercel's own guidance — the
  gateway executes the model string it is given.
- **C (Switchyard)**: decision latency of the real Rust algorithms (`random`,
  `llm_task_classifier` with a schema-valid fake judge), threshold behavior
  (p_solve vs `base_threshold`), and session affinity (judge skipped on the
  second call of a session). Model calls are handed back to the host — the only
  integration shape compatible with `machina-ai`'s PolicyEngine.

## What none of them measure (yet)

Output **quality** per route. That requires live routes plus task-level evals;
running quality benchmarks without evals is exactly the "tunable router as a
guess" failure mode RFC 003 rules out of scope.

## Running

```bash
# Option A — always runnable
python3 spikes/adaptive-routing/run_native.py

# Option C — needs the pre-alpha package in a sandbox venv (never in client-api)
python3 -m venv /tmp/sy-venv && /tmp/sy-venv/bin/pip install nemo-switchyard==0.2.0
/tmp/sy-venv/bin/python spikes/adaptive-routing/run_switchyard.py

# Option B — live spend; explicit operator action
AI_GATEWAY_API_KEY=... python3 spikes/adaptive-routing/run_vercel.py --only vertex
```

## Guardrails honored

- Workflows/templates never gain provider, credential, endpoint, fallback, or
  remap fields — `scripts/check-machina-ai-policy.py` and
  `scripts/check-no-openai.sh all` stay green with this spike in the tree.
- The Switchyard venv is disposable and stays out of `client-api` requirements
  (pyscript connectors execute in-process there; a pre-alpha dependency in that
  runtime would be a platform-wide blast radius).
- The Vercel runner never exercises BYOK: the documented BYOK failure path
  falls back to system credentials and bills credits, which conflicts with our
  fail-closed credential policy until proven controllable.
