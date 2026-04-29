# Kalshi Connector

REST API connector for Kalshi prediction markets - access series, markets, and trading data.

## Quick Start

1. **Install connector:**
```python
get_local_template(
  template="connectors/kalshi",
  project_path="/app/machina-templates/connectors/kalshi"
)
```

2. **Set credentials:**
   - `Kalshi-API-Key`
   - `Kalshi-User-Id`

3. **Create folder structure:**
```python
execute_workflow(name="kalshi-folders")
```

## Workflows

**Sync series (e.g., Soccer):**
```python
execute_workflow(
  name="kalshi-sync-series",
  context={"category": "Sports", "tags": "Soccer"}
)
```

**Sync markets:**
```python
execute_workflow(
  name="kalshi-sync-markets",
  context={"category": "Sports", "tags": "Soccer"}
)
```

**Optional parameters:**
```python
context={
  "category": "Sports",
  "tags": "Soccer",
  "include_product_metadata": True,
  "force-update": "true"
}
```

## FAQ

**How do I sync other sports?**
```
Tags: Baseball, Tennis, Basketball, American Football, Hockey
```

**How do I view synced data?**
```
Search for 'kalshi-series' or 'kalshi-markets' documents in the Kalshi folder.
```

**How do I force update existing records?**
```python
"force-update": "true"
```

**How do I include metadata?**
```python
"include_product_metadata": True
```

## Technical Notes

**API Response:** Kalshi API returns `{series: [...]}`. The connector extracts the array as intermediate variable `series_data` for workflow transit.

**Record Uniqueness:** Each document includes metadata (`id`, `category`) to prevent overwrites. Differentiation is in metadata within documents, not in document names.

**Mappings:** Define metadata directly in mapping outputs for consistent structure; minimize payload fields.

v0.2.0
