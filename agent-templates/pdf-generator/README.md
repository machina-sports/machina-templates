# PDF Generator (GCS-hosted)

Render a structured payload as a multi-page PDF and host it on Google
Cloud Storage. Three built-in layouts cover the most common asks:

| Template        | Pages   | Use case                                           |
|-----------------|---------|----------------------------------------------------|
| `brand-assets`  | ~14pp   | Brand guidelines (cover, palette, logos, voice)    |
| `rate-card`     | 1–2pp   | Pricing tiers / sponsorship rate card              |
| `contact-sheet` | N pages | 4×4 image grid with captions and pagination       |

Output is a PDF uploaded to your project's GCS bucket (via the
`google-storage` connector) — the workflow returns the public URL.

## Install

```bash
machina template install agent-templates/pdf-generator
```

Required vault keys (already wired if you also installed
`connectors/google-storage`):

- `TEMP_CONTEXT_VARIABLE_GOOGLE_STORAGE_API_KEY` — service-account JSON
- `TEMP_CONTEXT_VARIABLE_GOOGLE_STORAGE_BUCKET_NAME`

For the brief-driven workflow (`pdf-generator-from-brief`), also:

- `TEMP_CONTEXT_VARIABLE_VERTEX_AI_CREDENTIAL`
- `TEMP_CONTEXT_VARIABLE_VERTEX_AI_PROJECT_ID`

## Usage — `pdf-generator` workflow

### Brand Assets (~14pp)

```bash
machina workflow run pdf-generator \
  template=brand-assets \
  brand_color="#0A2540" \
  remote_path="brand/" \
  content='{
    "brand_name": "North Pitch FC",
    "tagline": "Football, the way the north plays it.",
    "about": "North Pitch FC is a community-first football club...",
    "mission": "To make football the best part of every supporter'\''s week.",
    "values": [
      {"name":"Local first","description":"Built by the city, for the city."},
      {"name":"Open play","description":"Attacking football, every match."},
      {"name":"Honest pricing","description":"No hidden fees, ever."}
    ],
    "logos": [
      {"url":"https://example.com/logo-primary.png","label":"Primary lockup"}
    ],
    "palette": [
      {"name":"Deep Navy","hex":"#0A2540","usage":"Primary"},
      {"name":"Pitch Green","hex":"#1B7F3B","usage":"Accent"},
      {"name":"Bone","hex":"#F4F1EA","usage":"Background"},
      {"name":"Crowd Red","hex":"#D7263D","usage":"Highlight"}
    ],
    "typography": [
      {"name":"Söhne","description":"Display + headlines","sample":"Match day."},
      {"name":"Inter","description":"Body copy","sample":"The quick brown fox..."}
    ],
    "voice": {
      "description":"Direct, warm, never corporate.",
      "do":["Speak like a fan","Use first names","Celebrate every goal","Acknowledge the loss"],
      "dont":["Use stadium hyperbole","Hide behind brand-speak","Talk down to supporters","Promise silverware"]
    },
    "contact": {
      "email":"brand@northpitch.fc",
      "website":"northpitch.fc"
    }
  }'
```

### Rate Card

```bash
machina workflow run pdf-generator \
  template=rate-card \
  brand_color="#0A2540" \
  content='{
    "title":"North Pitch FC · 2026 Sponsorship Rate Card",
    "period":"2026 Season",
    "intro":"Three tiers of partnership, designed for clubs of every size.",
    "tiers": [
      {"name":"Bronze","description":"Matchday visibility","deliverables":["LED board (5 min)","Programme half-page","Social mention"],"price":"€12,000"},
      {"name":"Silver","description":"Season-long presence","deliverables":["LED board (15 min)","Full-page programme","Newsletter feature","2 social posts/match"],"price":"€34,000"},
      {"name":"Gold","description":"Headline partner","deliverables":["Stadium naming rights","Front-of-shirt","Bespoke content series","All matchday assets"],"price":"On request"}
    ],
    "notes":["All prices ex-VAT","12-month commitment","Includes 4 hospitality seats per match (Silver+)"],
    "contact":{"email":"partners@northpitch.fc","phone":"+44 191 555 0100"}
  }'
```

### Contact Sheet

```bash
machina workflow run pdf-generator \
  template=contact-sheet \
  content='{
    "title":"Pre-season Press Shoot · September 2026",
    "columns":4,
    "rows":4,
    "show_captions":true,
    "images":[
      {"url":"https://example.com/img/01.jpg","caption":"01 — Squad lineup"},
      {"url":"https://example.com/img/02.jpg","caption":"02 — Captain portrait"}
    ]
  }'
```

## Usage — `pdf-generator-from-brief` workflow

Skip the JSON wrangling and let Gemini draft the brand-assets payload
from a freeform brief:

```bash
machina workflow run pdf-generator-from-brief \
  brand_name="North Pitch FC" \
  brand_color="#0A2540" \
  brief="A community-owned 4th-tier English football club... values: local first, open play, honest pricing. Voice: warm, direct, never corporate."
```

## Frontend / runtime use

Both workflows are sync. Call them from a deployed page through the
Factory proxy:

```js
const { proxyUrl } = window.MACHINA_DEPLOY;
const res = await fetch(`${proxyUrl}/workflow/execute/pdf-generator`, {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify({
    template: "brand-assets",
    brand_color: "#0A2540",
    content: { /* ... */ },
  }),
});
const { pdf_url } = await res.json();
```

## Customizing the layouts

Layouts live in `connectors/pdf-generator.py`. Each is a function:

- `_build_brand_assets(content, pagesize, brand_color) -> story[]`
- `_build_rate_card(content, pagesize, brand_color) -> story[]`
- `_build_contact_sheet_canvas(content, pagesize, brand_color, output_path)` (raw canvas)

To add a new layout (e.g. `event-recap`), add a new builder function and
wire it into the `template == "..."` dispatch in `invoke_generate`.

The brand-assets layout intentionally lands around 14 pages so the
output matches the canonical "PDF · 14pp · brand assets" deliverable.
