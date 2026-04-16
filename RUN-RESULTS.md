# Goalserve Soccer Run Results
## Test Credentials Workflow

  Running workflow: goalserve-soccer-test-credentials
  Mode: sync

╭───────────────────────────── Workflow Complete ──────────────────────────────╮
│ Status: executed                                                             │
│ Workflow Run ID: 69e15713ec1f7952e7867c95                                    │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─────────────────────────────────── Output ───────────────────────────────────╮
│ {                                                                            │
│   "outputs": {                                                               │
│     "result": {                                                              │
│       "leagues_count": 0,                                                    │
│       "sample": [],                                                          │
│       "status": "error"                                                      │
│     },                                                                       │
│     "workflow-error": {                                                      │
│       "code": 500,                                                           │
│       "context": {                                                           │
│         "command": "get_leagues_mapping",                                    │
│         "connector_name": "goalserve-soccer-pyscript",                       │
│         "model": null,                                                       │
│         "workflow_context": "connector_execution"                            │
│       },                                                                     │
│       "message": "API key is required"                                       │
│     },                                                                       │
│     "workflow-status": "failed"                                              │
│   },                                                                         │
│   "totals": {                                                                │
│     "completion_tokens": 0,                                                  │
│     "prompt_tokens": 0,                                                      │
│     "total_tokens": 0                                                        │
│   }                                                                          │
│ }                                                                            │
╰──────────────────────────────────────────────────────────────────────────────╯

## Sync Leagues Workflow

  Running workflow: goalserve-soccer-sync-leagues
  Mode: sync

╭───────────────────────────── Workflow Complete ──────────────────────────────╮
│ Status: executed                                                             │
│ Workflow Run ID: 69e15714ec1f7952e7867c97                                    │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─────────────────────────────────── Output ───────────────────────────────────╮
│ {                                                                            │
│   "outputs": {                                                               │
│     "leagues": [],                                                           │
│     "workflow-error": {                                                      │
│       "code": 500,                                                           │
│       "context": {                                                           │
│         "command": "get_leagues_mapping",                                    │
│         "connector_name": "goalserve-soccer-pyscript",                       │
│         "model": null,                                                       │
│         "workflow_context": "connector_execution"                            │
│       },                                                                     │
│       "message": "API key is required"                                       │
│     },                                                                       │
│     "workflow-status": "failed"                                              │
│   },                                                                         │
│   "totals": {                                                                │
│     "completion_tokens": 0,                                                  │
│     "prompt_tokens": 0,                                                      │
│     "total_tokens": 0                                                        │
│   }                                                                          │
│ }                                                                            │
╰──────────────────────────────────────────────────────────────────────────────╯
