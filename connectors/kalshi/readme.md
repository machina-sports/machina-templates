# Kalshi Connector

REST API connector for Kalshi prediction markets - access event data, markets, trading info, and portfolio management.

## Installation

```python
get_local_template(
  template="connectors/kalshi",
  project_path="/app/machina-templates/connectors/kalshi"
)
```

Installs: `kalshi-api` connector + `sync-markets` and `sync-series` workflows.

## Configuration

Set these credentials:
- `Kalshi-API-Key`
- `Kalshi-User-Id`

## Usage

**Sync series by sport:**
```python
execute_workflow(
  name="kalshi-sync-series",
  context={"category": "Soccer"}  # or: American Football, Basketball, Baseball, Hockey, Tennis
)
```

**Sync markets:**
```python
execute_workflow(name="kalshi-sync-markets", context={"category": "Soccer"})
```

**Optional params:**
```python
context={
  "category": "Soccer",
  "include_product_metadata": True,
  "force-update": "true"
}
```

v0.2.0
