# Agent Template Validation Report

**Pull Request:** [machina-sports/machina-templates#98](https://github.com/machina-sports/machina-templates/pull/98)
**Connector Path:** `connectors/goalserve-soccer`

## Validation Results

| Check | Status | Notes |
|-------|--------|-------|
| 1. `_install.yml` has required fields | **PASS** | Contains `setup` block with `title`, `description`, `value`, `version`, and `datasets`. |
| 2. All paths in datasets actually exist | **PASS** | All connector and workflow YAML files listed in datasets are present in the directory. |
| 3. YAML files are valid and parseable | **PASS** | All `.yml` files parsed successfully without syntax errors. |
| 4. Connector JSON schemas valid OpenAPI 3.0 | **N/A** | The connector is a `pyscript` connector (`goalserve-soccer-pyscript`), so it uses a Python script (`goalserve-soccer.py`) rather than an OpenAPI JSON schema. |
| 5. Workflow outputs include `workflow-status` | **PASS** | All workflow files include the required `workflow-status` output definition. |
| 6. Context-variables reference valid vault key patterns | **PASS** | Files correctly use the `$TEMP_CONTEXT_VARIABLE_GOALSERVE_API_KEY` pattern. |
| 7. No hardcoded secrets or tokens in any file | **PASS** | Only placeholders (context variables) are used for credentials. |

## Fixes Applied
- Fixed an issue in `test-credentials.yml` where the incorrect connector name (`goalserve-soccer` instead of `goalserve-soccer-pyscript`) and command (`getLeaguesMapping` instead of `get_leagues_mapping`) were specified. Also ensured the context variable was properly nested and quoted.

## Conclusion
The template passes all validation checks.
