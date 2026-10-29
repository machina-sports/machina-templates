# Eval Judges

Evaluator workflows for runtime evals (client-api `core/runtime_controls`, Studio **Arena → Evals**).

The eval runner calls the evaluator workflow with the evaluator envelope as its workflow context
(`content.input`, `content.output`, `source`, …) and reads `verdict`, `score`, `reason`, `labels`
(and optionally `failure_class`, `severity`) from the workflow outputs. Anything outside the
`judge-output` contract becomes `run_status=error`, never a verdict.

| Workflow | Needs | Verdict |
|---|---|---|
| `eval-judge-quality` | `TEMP_CONTEXT_VARIABLE_VERTEX_AI_CREDENTIAL` / `_PROJECT_ID` | Gemini judges whether the output faithfully answers the input |
| `eval-judge-deterministic` | nothing | `pass` if the target returned a non-empty `result`, else `fail` |
| `eval-demo-echo` (target) | nothing | returns the text upper-cased; `#fail` in the text returns an empty result |

Try it: publish an eval with target `eval-demo-echo`, evaluator `eval-judge-deterministic`, any judge
prompt, sampling 100%; run the target with `{"text": "hi"}` and `{"text": "x #fail"}`; Recent
Evaluations shows one `pass` and one `fail`.

Requires client-api with machina-client-api#380, #403 and #404, and the project listed in core-api's
`PROJECT_EVAL_AUTHORING_PROJECTS` for authoring with a project token.
