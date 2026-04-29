# Machina Skills Compatibility Spec

## Purpose

This document defines the current package contract in `machina-templates`, the backward-compatibility rules for evolving it, and the additive path for formalizing `skill.yml` as the canonical skill manifest without breaking existing installs.

The goal is simple:

- every valid template that installs today must continue to install tomorrow
- existing `_install.yml` and `skill.yml` patterns remain valid
- new skill metadata is added additively, not destructively
- `machina-cli`, `machina-studio`, `core-api`, and `client-api` can converge on one shared concept of a skill

---

## Current State Summary

### Repo audit

Observed in `machina-templates`:

- `_install.yml` files: 64
- `skill.yml` files: 4

Current `skill.yml` locations:

- `skills/mkn-constructor/skill.yml`
- `connectors/polymarket/skills/sync-events/skill.yml`
- `connectors/polymarket/skills/sync-markets/skill.yml`
- `connectors/polymarket/skills/sync-series/skill.yml`

Current dataset types observed in `_install.yml`:

- `workflow`
- `connector`
- `mappings`
- `agent`
- `prompts`
- `prompt`
- `skill`

### Current architectural reality

The repository already contains a real skill abstraction.

- `_install.yml` is the installer/package manifest
- `skill.yml` is the machine-readable skill manifest
- `SKILL.md` is the human/operator-facing guide
- Studio already contains a Skills UI surface
- CLI is evolving toward package install/push behavior

The problem is not that skills do not exist.
The problem is that the contract is implicit, partially duplicated, and at risk of dialect drift.

---

## Definitions

### Template

A package in `machina-templates` that can install one or more Machina resources.

Examples:
- connector package
- agent template
- skill package

### Skill

A versioned packaged capability that can be discovered, installed, configured, and executed.

A skill may bundle or reference:
- workflows
- agents
- prompts
- connectors
- mappings
- documents/references
- local guide files

A skill is the product-facing abstraction.
The other resource types are implementation pieces.

### Installer manifest

`_install.yml` defines how a package is installed.

### Skill manifest

`skill.yml` defines what a skill is and how it is exposed to the platform.

---

## Canonical Contract: Current Version

## 1. `_install.yml` (current v1 installer contract)

### Role

`_install.yml` is the package installer manifest.
It is responsible for:

- installer metadata
- install ordering
- dataset inventory
- package source path

### Current structure

```yaml
setup:
  title: <string>
  description: <string>
  category: <list>
  estimatedTime: <string>
  features: <list>
  integrations: <list>
  status: <string>
  value: <string>
  version: <string>
  requirements: <list?>

datasets:
  - type: <string>
    path: <string>
```

### Current compatibility notes

- `setup` is required
- `datasets` is required for installable packages
- `type: skill` is already valid
- dataset ordering matters operationally
- `value` is currently used as the package path / install identity

### Current risks

- duplicated metadata with `skill.yml`
- inconsistent dataset taxonomy (`prompt` vs `prompts`)
- no explicit schema version field

---

## 2. `skill.yml` (current v1 skill contract)

### Role

`skill.yml` is the machine-readable runtime/product manifest for a skill.
It is responsible for:

- skill identity
- discoverability metadata
- reference document registration
- executable entrypoints

### Current structure

```yaml
skill:
  name: <string>
  title: <string>
  description: <string>
  version: <string>
  category: <list>
  status: <string>
  domain: <string>

  references: <list>
  workflows: <list>
  agents: <list?>
```

### Current proven fields in repo

Observed in production examples:

- `name`
- `title`
- `description`
- `version`
- `category`
- `status`
- `domain`
- `references`
- `workflows`

### Current strengths

- already installable through dataset type `skill`
- already expressive enough for Studio discovery basics
- already supports linked references and workflow entrypoints

### Current gaps

Not yet formalized:

- dependency graph
- install mode
- runtime target
- secret requirements
- local/cloud asset distinction
- monetization tier
- visibility rules
- SDK exposure contract
- execution semantics
- manifest versioning

---

## Backward-Compatibility Rules

These rules are mandatory for the architecture renewal.

### Rule 1: no valid existing package becomes invalid

Any package currently installable through `_install.yml` must remain installable.

### Rule 2: `skill.yml` stays

Do not replace `skill.yml` with a brand-new format.
Extend it additively.

### Rule 3: `_install.yml` stays

Do not collapse installer metadata into `skill.yml`.
Installer and runtime concerns remain separate.

### Rule 4: dataset type aliases must be supported during migration

At minimum, readers must tolerate:

- `prompt`
- `prompts`

until a canonical write-path is established.

### Rule 5: additive before destructive

All new skill metadata must be introduced as optional fields first.
Readers should accept both:

- current v1 manifests
- extended v1.1 manifests

### Rule 6: no path or folder renames in phase 1

Do not rename:
- `skills/`
- `skill.yml`
- `_install.yml`
- existing package roots

until all readers support the enriched contract.

### Rule 7: install semantics must not change silently

If package install behavior changes, the change must be encoded explicitly in manifest fields rather than inferred differently by new tooling.

---

## Canonical Responsibility Split

## `_install.yml` owns

- installer/package metadata
- dataset inventory
- package path identity
- install ordering
- install-time requirements

## `skill.yml` owns

- skill identity
- product/discovery metadata
- linked references
- entrypoints
- execution metadata
- dependency metadata
- future SDK/runtime exposure metadata

## `SKILL.md` owns

- human usage guidance
- procedural instructions
- examples
- operator-facing docs

---

## Proposed `skill.yml` v1.1 (additive only)

The following fields are proposed as optional additions.
No existing field is removed.

```yaml
skill:
  name: "example-skill"
  title: "Example Skill"
  description: "Example description"
  version: "1.0.0"
  category:
    - "example"
  status: "available"
  domain: "https://github.com/machina-sports/machina-templates"

  manifest_version: "1.1"
  visibility: "public"
  tier: "free"
  install_mode: "hybrid"
  runtime: "client-api"

  references: []
  workflows: []
  agents: []

  dependencies:
    connectors: []
    workflows: []
    prompts: []
    mappings: []
    documents: []
    skills: []

  secrets:
    required: []
    optional: []

  execution:
    entrypoint_type: "workflow"
    entrypoint_name: "example-workflow"
    async_supported: true

  sdk:
    exposed: true
    methods:
      - "run"
      - "get"
```

### Proposed field meanings

#### `manifest_version`
Version of the skill manifest contract, not the skill package version.

#### `visibility`
Allowed values:
- `public`
- `private`
- `internal`

#### `tier`
Allowed values:
- `free`
- `pro`
- `enterprise`

This is future-safe for Stripe and entitlement work without requiring implementation now.

#### `install_mode`
Allowed values:
- `local`
- `cloud`
- `hybrid`

#### `runtime`
Primary execution surface.
Expected values initially:
- `client-api`
- `core-api`
- `local`

Default recommendation for executable project skills: `client-api`

#### `dependencies`
Declarative dependency graph for validation and install planning.

#### `secrets`
Explicit required/optional secret list for setup and validation.

#### `execution`
Declares the default execution contract for CLI, Studio, and SDK readers.

#### `sdk`
Signals whether the skill should be surfaced in generated SDK clients and what high-level methods should exist.

---

## Dataset Taxonomy Compatibility Plan

### Current canonical types in the wild

- `connector`
- `workflow`
- `agent`
- `mappings`
- `skill`
- `prompt`
- `prompts`

### Problem

`prompt` and `prompts` both exist.
This is already a schema drift bug.

### Compatibility policy

#### Read path
All readers must accept both:
- `prompt`
- `prompts`

#### Write path
Pick one canonical value and standardize future manifests on it.

### Recommendation

Canonicalize on singular dataset names for new writes where possible:
- `connector`
- `workflow`
- `agent`
- `mapping` or preserve `mappings` if already coupled downstream
- `prompt`
- `skill`

However:
- do not mass-rewrite repo manifests in phase 1
- first update readers and validators to tolerate aliases

---

## Platform Split Recommendation

## `machina-templates`
Source of truth for package and skill manifests.

## `machina-cli`
Install/push/test surface for packages and skills.
Should eventually expose `skills` as the product-facing command surface while preserving compatibility with `template` commands during migration.

## `machina-studio`
Discovery, management, execution, and analytics UI for skills.
Consumes installed skill metadata and richer manifest fields over time.

## `core-api`
Owns:
- skill catalog
- search/discovery metadata
- visibility
- entitlement
- publishing/registry semantics

## `client-api`
Owns:
- project-scoped installed skill state
- skill execution
- skill activity
- project-local overrides

---

## Migration Sequence

### Phase 1: Spec and reader compatibility
- document current contract
- support current + v1.1 manifests
- support dataset aliases on read path
- no breaking changes to install

### Phase 2: Template contract cleanup
- introduce optional v1.1 fields in selected skills
- validate with CLI and Studio readers
- avoid mass rewrites

### Phase 3: Product surface cleanup
- add `skills` command family in CLI
- keep `template` aliases for compatibility
- Studio begins reading enriched skill metadata

### Phase 4: Backend convergence
- `core-api` becomes catalog/registry/entitlement authority
- `client-api` becomes runtime execution authority

### Phase 5: SDK exposure
- expose skill abstraction in TS/Python SDKs
- map skill manifest metadata to generated client methods

---

## Non-Goals for Phase 1

Do not do these yet:

- rename package roots
- remove `_install.yml`
- replace `skill.yml`
- force all templates to adopt v1.1
- introduce breaking install order changes
- hard-wire x402-specific semantics into the manifest

---

## Immediate Next Actions

1. Validate all manifest readers against current repo patterns.
2. Update validators to support legacy dataset aliases.
3. Implement additive `skill.yml` v1.1 support in readers.
4. Introduce CLI `skills` aliases without removing `template` flows.
5. Align Studio Skills tab to the enriched manifest incrementally.

---

## Final Principle

The path forward is not to invent a brand-new skill architecture.
It is to formalize the one that already exists, preserve everything that works, and extend it carefully enough that the platform can converge without breaking installs.
