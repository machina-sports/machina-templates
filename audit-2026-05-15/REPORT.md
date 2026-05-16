# Auditoria de Instalação — Catálogo `machina-templates`

**Data:** 2026-05-15
**Branch:** `audit/install-catalog-2026-05-15` (local, sem PR)
**Canal de install:** MCP `machina-factory-customers` (transporte SSE) → tool `import_templates_from_git` → REST `POST /templates/git`
**Project alvo (sandbox):** `factory-templates-testing`
**Endpoint:** `https://machina-factory-factory-templates-testing.org.machina.gg/mcp/sse`
**Repo de origem:** `https://github.com/machina-sports/machina-templates` @ `main`

---

## Resumo executivo

| Métrica | Valor |
|---|---|
| Templates publicados testados | **84** |
| ✅ OK | **79** |
| 🔴 **FALHA** | **5** |
| Cobertura | 100% (33 agent-templates + 43 connectors + 7 skills + mkn-constructor) |
| Evidência crua | [`results.json`](./results.json) |
| Log da execução | [`run.log`](./run.log) |

---

## 🔴 Templates quebrados (separados para análise posterior)

> Nenhum template foi removido nesta etapa, conforme escopo.

### 1. `agent-templates/machina-media`

- **Erro do servidor:**
  > `Failed to process dataset file .../mappings/map-normalize-event.yml: Failed to import mapping dataset: Unsupported dataset type: mapping`
- **Causa estrutural provável:** `_install.yml` declara `type: "mapping"` (singular) em três datasets (linhas 37, 39, 41). O parser do server só aceita `type: "mappings"` (plural). É inconsistência de nomenclatura entre o que o catálogo publica e o vocabulário aceito pelo importador.
- **Linhas afetadas:** `agent-templates/machina-media/_install.yml` linhas 37–42.

### 2. `agent-templates/template-sportsblog`

- **Erro do servidor:**
  > `Invalid install file format: missing both 'datasets' and 'extends'`
- **Causa estrutural provável:** o bloco `datasets:` está **aninhado dentro de `setup:`** em vez de ser top-level. O parser procura `datasets`/`extends` na raiz do YAML; como só existe `setup:` na raiz, ele rejeita. Olhar a indentação do arquivo: `setup:` é a única chave top-level e tudo (inclusive `datasets:`) vive sob ele.
- **Arquivo afetado:** `agent-templates/template-sportsblog/_install.yml` (raiz).

### 3. `agent-templates/template-superbowl-lix`

- **Erro do servidor:**
  > `[Errno 2] No such file or directory: '/tmp/.../agent-templates/template-superbowl-lix/../connectors/groq/groq.yml'`
- **Causa estrutural provável:** o `_install.yml` referencia conectores via caminho cross-template (`../connectors/groq/groq.yml`, `../connectors/openai/openai.yml`, `../connectors/sportradar-nfl/sportradar-nfl.yml`), mas o importador clona/disponibiliza apenas o sub-diretório do template selecionado em `/tmp/...`. Os arquivos vizinhos `connectors/*` não estão presentes no tmp, então o `..` aponta para uma pasta vazia. Templates que usam o mesmo padrão e funcionam (ex.: `bundesliga-podcast`) usam `../../connectors/...` — duas pastas acima — o que pode estar no comportamento do importador. Este template usa `../connectors/` (um nível só) → resolve fora da pasta tmp.
- **Linhas afetadas:** `agent-templates/template-superbowl-lix/_install.yml` linhas 26, 28, 30.

### 4. `agent-templates/transfer-rumors-recap`

- **Erro do servidor:**
  > `Failed to process dataset file .../prompts/recap-transfer-rumors.yml: Failed to import prompt dataset: Invalid prompt dataset format`
- **Causa estrutural provável:** o YAML do prompt usa `instruction:` (singular) na linha 11, mas o schema válido (visto em `bundesliga-podcast/prompts/generate-podcast.yml` linha 9 e nos demais templates OK) exige `instructions:` (plural). Inconsistência de chave.
- **Arquivo afetado:** `agent-templates/transfer-rumors-recap/prompts/recap-transfer-rumors.yml`.

### 5. `connectors/api-football`

- **Erro do servidor:**
  > `AUTH-013 — An unexpected error has occurred / Internal server error` (HTTP 500)
- **Causa estrutural provável:** **não identificada por análise estática**. O `_install.yml` está bem formado (top-level `setup:` + `datasets:`), datasets internos referenciam arquivos que existem, e a mensagem do servidor é genérica (`AUTH-013` sugere falha na camada de auth/permissão interna ao tentar criar algum recurso, talvez colisão de id ou problema no `agents/populate.yml` / `agents/event-*-update.yml`). **Precisa investigar logs do server-side** (ou rodar install isolando datasets) para isolar a causa.
- **Arquivo afetado:** `connectors/api-football/_install.yml` + assets sob `agents/` e `workflows/`.

---

## ✅ Templates OK (79)

<details>
<summary>Lista completa</summary>

**agent-templates (29/33):** article-summary, assistant-tools, betting-copilot, bundesliga-podcast, chat-completion, corinthians-twitter, coverage-tools, daily-football-recap, ea-football-chat, event-podcast, iptc-mappings, kalshi-market-agent, machina-assistant, machina-cockpit, nba-conversational-experience, nfl-2025-preseason, nfl-podcast-generator, onboarding, pdf-generator, personalized-podcast, psg-podcast-generator, roast-agent, social-media-generator, template-fastf1, template-newsletter, template-quizzes, truth-point, voice-chat-completion, voice-tts-studio.

**connectors (42/43):** american-football, bwin, byteplus-modelark, docling, elevenlabs, exa-search, fastf1, goalserve-soccer, google-genai, google-speech-to-text, google-storage, google-workstation, grok, groq, kalshi, machina-ai, machina-ai-fast, machina-football-data, mlb-statsapi, mongodb-atlas, openai, oxylabs, perplexity, polymarket, rss-feed, sociavault, sportradar-mlb, sportradar-nba, sportradar-nfl, sportradar-nhl, sportradar-rugby, sportradar-soccer, sportradar-tennis, sports-skills, stability, stats-perform, storage, tallysight, temp-downloader, vertex-embedding, wordpress, zendesk.

**skills (7/7):** manifest-generator, match-headline-generator, match-stats-formatter, mkn-constructor, news-monitor-storylines, post-match-tweet-thread, press-conference-extractor.

**mkn-constructor (1/1):** mkn-constructor (raiz).

</details>

---

## Skeleton de template (para referência)

Dois padrões coexistem no catálogo:

### Padrão A — "Setup template" (agent-templates, skills, mkn-constructor)

```
<template-root>/
├── _install.yml          # entry point — bloco `setup:` + `datasets:` (TOP-LEVEL)
├── agents/               # *.yml — definições de agente
├── connectors/           # *.yml — configs de conector (locais ao template)
├── prompts/              # *.yml — prompts (key `instructions:` no plural)
├── workflows/            # *.yml — workflows
├── data/ | scripts/ | references/ | schemas/  # opcionais (varia por template)
└── SKILL.md              # narrativa (skills/mkn-constructor)
```

`_install.yml`:
```yaml
setup:
  title: <string>
  description: <string>
  category: [<string>]
  estimatedTime: <string>
  features: [<string>]
  integrations: [<string>]
  status: available
  value: <scope>/<template-name>
  version: <semver>

datasets:                     # <-- TOP-LEVEL, NÃO aninhado em setup:
  - type: agent | connector | prompts | workflow | skill | mappings
    path: <relativo-ao-template>      # ex: agents/foo.yml
  # cross-template (opcional): "../../connectors/<name>/<name>.yml"
```

### Padrão B — "Plain connector" (connectors/*)

```
<template-root>/
├── _install.yml          # apenas `datasets:` — SEM bloco `setup:`
├── <connector>.yml       # definição do conector
├── <connector>.py        # script opcional
└── test-credentials.yml  # workflow de validação de credenciais
```

`_install.yml`:
```yaml
datasets:
  - type: connector
    path: <name>.yml
  - type: workflow
    path: test-credentials.yml
```

> **Observação:** o catálogo aceita ambos os padrões. Connectors quebram quando alguém aplica o Padrão A (ou variante mista) sem garantir schema válido — caso de `api-football`, que segue Padrão A mas falha em 500.

---

## Erros observados no processo de instalação

| # | Erro retornado pelo `/templates/git` | Templates afetados | Tipo |
|---|---|---|---|
| 1 | `Unsupported dataset type: mapping` | `agent-templates/machina-media` | Vocabulário inválido em `type:` |
| 2 | `Invalid install file format: missing both 'datasets' and 'extends'` | `agent-templates/template-sportsblog` | `datasets:` aninhado em `setup:` |
| 3 | `No such file or directory: .../../connectors/<x>/<x>.yml` | `agent-templates/template-superbowl-lix` | Cross-template path inválido (`..` único) |
| 4 | `Invalid prompt dataset format` | `agent-templates/transfer-rumors-recap` | Chave `instruction:` em vez de `instructions:` |
| 5 | `AUTH-013 / Internal server error` (HTTP 500) | `connectors/api-football` | Erro server-side genérico — necessita logs |

---

## Como reproduzir

```bash
cd machina-templates
git checkout audit/install-catalog-2026-05-15
python3 audit-2026-05-15/install_audit.py        # roda os 84
python3 audit-2026-05-15/install_audit.py --scope agent-templates   # subset
python3 audit-2026-05-15/install_audit.py --resume    # retoma após interrupção
```

Resultados estruturados em `audit-2026-05-15/results.json`; log em `audit-2026-05-15/run.log`.

---

## Critérios de aceite — checklist

- [x] Todos os templates publicados foram testados para instalação (84/84).
- [x] Lista final contém nome, status, erro/falha e observação de possível causa estrutural.
- [x] Templates que falharam ficam claramente separados (seção 🔴 acima).
- [x] Skeleton de templates documentado (Padrão A + Padrão B, install e pares).
- [x] Erros do processo de instalação listados.
- [x] Branch local criada (`audit/install-catalog-2026-05-15`), sem abertura de PR.
- [x] Sem remoção de templates nesta etapa.
