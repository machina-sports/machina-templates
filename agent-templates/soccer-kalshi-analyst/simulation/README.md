# Simulation (MCP)

## EPL 2025 — buscar “próximos eventos sem forecast”

Veja `2025-EPL-ids.md` — ele contém a query MCP (`document/search`) pronta com:

- `sorters: ["value.schema:startDate", 1]`
- filtro `value.version_control.forecasted: {"$ne": true}`
- `page_size: 3` (pra você ir pedindo “mais 3” só aumentando o `page`)
