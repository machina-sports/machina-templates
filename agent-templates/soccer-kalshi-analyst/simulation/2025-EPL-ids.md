# EPL 2025 — query para achar eventos (ordem cronológica) sem forecast

- **season_urn**: `urn:apifootball:season:39:2025`
- **document**: `sport:Event`
- **objetivo**: pegar os **próximos 3** eventos em `value.schema:startDate` crescente, onde `value.version_control.forecasted != true`

## MCP `document/search` (exemplo)

Use exatamente este filtro + sorter e ajuste só o `page` (1, 2, 3...) quando quiser processar mais:

```json
{
  "filters": {
    "name": "sport:Event",
    "value.sport:competition.sport:season.@id": "urn:apifootball:season:39:2025",
    "value.version_control.forecasted": { "$ne": true }
  },
  "sorters": ["value.schema:startDate", 1],
  "page": 1,
  "page_size": 3
}
```

## Observações rápidas

- Se `forecasted` não existir no documento, `{"$ne": true}` também retorna (isso é desejado).
- Para “pegar mais 3”, aumente `page` para `2`, depois `3`, etc.

