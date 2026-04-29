# Data Model

This document defines the shared internal content objects used across the Machina Media agent. The architecture follows a one-to-many fan-out model: a single `Event` can generate multiple `Storylines`, which can be bundled into `Segments`. A `Segment` is realized as a `Script`, which can then be broken down into `Clip Candidates` and derivative `Social Posts`.

---

### `event`
The canonical representation of a sports event. This object tracks the state of a single game or match.

| Field | Type | Purpose |
| :--- | :--- | :--- |
| `sport` | `string` | The sport being played (e.g., "football", "basketball"). |
| `league` | `string` | The league the event belongs to (e.g., "NFL", "NBA"). |
| `home_team` | `object` | Home team information (name, score). |
| `away_team` | `object` | Away team information (name, score). |
| `score` | `string` | The current score. |
| `clock` | `string` | The current game clock or period (e.g., "Q4 02:15", "Final"). |
| `status` | `string` | The status of the event (e.g., "scheduled", "live", "completed"). |
| `start_time` | `datetime` | The scheduled start time of the event (ISO 8601). |
| `external_ids` | `object` | A dictionary of IDs from various data sources. |

---

### `storyline`
A single, newsworthy narrative thread related to an event. This is the atomic unit of our editorial engine.

| Field | Type | Purpose |
| :--- | :--- | :--- |
| `id` | `string` | A unique identifier for the storyline. |
| `event_ref` | `string` | A reference to the parent `event` object. |
| `type` | `string` | The category of the storyline (e.g., `live_swing`, `injury`, `trade`, `market_move`, `milestone`, `upset`, `narrative`). |
| `urgency` | `string` | The priority of the storyline (`breaking`, `high`, `medium`, `low`). |
| `headline` | `string` | A concise, machine-readable summary of the storyline. |
| `supporting_facts` | `array` | A list of data points or facts that support the headline. |
| `created_at` | `datetime` | The timestamp when the storyline was first identified. |

---

### `segment`
A block of content for the broadcast, composed of one or more storylines.

| Field | Type | Purpose |
| :--- | :--- | :--- |
| `id` | `string` | A unique identifier for the segment. |
| `kind` | `string` | The type of segment (`live_hit`, `briefing_block`, `recap`, `breaking_alert`). |
| `source_storyline_ids` | `array` | A list of `storyline` IDs that this segment covers. |
| `target_duration_sec` | `integer` | The estimated duration of the segment in seconds. |
| `status` | `string` | The current state of the segment (e.g., "planned", "scripted", "published"). |

---

### `script`
The actual content to be delivered in a segment, including host lines and production cues.

| Field | Type | Purpose |
| :--- | :--- | :--- |
| `segment_id` | `string` | A reference to the parent `segment` object. |
| `host_lines` | `array` | An array of strings, each representing a line for the host to read. |
| `beats` | `array` | A sequence of timed events or talking points within the script. |
| `title_options` | `array` | A list of suggested titles for the video segment. |
| `lower_thirds` | `array` | A list of suggested text for lower-third graphics. |

---

### `clip_candidate`
A potential short-form video clip derived from a longer segment.

| Field | Type | Purpose |
| :--- | :--- | :--- |
| `source_segment_id` | `string` | A reference to the parent `segment` object. |
| `hook` | `string` | The opening line or hook for the clip. |
| `title` | `string` | The suggested title for the short-form video. |
| `caption` | `string` | The suggested caption or description for the video. |
| `duration_target_sec` | `integer` | The target duration of the clip in seconds. |
| `thumbnail_text` | `string` | Suggested text for the video thumbnail. |

---

### `social_post`
A piece of content formatted for a specific social media platform.

| Field | Type | Purpose |
| :--- | :--- | :--- |
| `source_ref` | `string` | A reference to the source object (e.g., `segment_id`, `clip_candidate_id`). |
| `platform` | `string` | The target platform (`youtube_shorts`, `x`, `tiktok`, `instagram`). |
| `body` | `string` | The text content of the post. |
| `hashtags` | `array` | A list of relevant hashtags. |
| `variant_index` | `integer` | An index for A/B testing or content variations. |
