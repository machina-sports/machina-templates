# Caller deadlines

`timeout_ms` limits each provider attempt. Optional `total_deadline_ms` is a
positive integer in milliseconds, accepted as a request input or inside `options`.
It shortens the runtime's total invocation budget across retries and fallbacks;
it cannot extend runtime policy. Omitting it preserves existing behavior.

Broadcast's cited research requests use 45,000 ms for both budgets. The observed
API worker retirement grace is 60 seconds, leaving 15 seconds for validation and
persistence. A 120-second search previously outlived worker retirement and left an
unfinished execution audit. Changing this connector does not repair old audits.

SDK timeouts remain cooperative. Late results are rejected, but this is not a
replacement for durable worker execution or runtime interruption reconciliation.
Install this owner connector before workflows that depend on the new option.
No provider, credential, routing or retry policy is changed by this addition.
