# Architecture

This document outlines the technical architecture of the Machina Media agent, including workflows, agents, prompts, and a gap analysis for implementation.

## Workflow-by-Workflow Breakdown

The system is composed of nine core workflows, each responsible for a specific stage of the content pipeline.

| Workflow | Inputs | Outputs | Produces Data Model Object(s) |
| :--- | :--- | :--- | :--- |
| **1. Ingest & Normalize Data** | `source_feeds` (list) | `normalized_events` (list) | `event` |
| **2. Detect Storylines** | `events` (list) | `detected_storylines` (list) | `storyline` |
| **3. Rank Storylines** | `storylines` (list) | `ranked_storylines` (list) | `storyline` (with updated urgency) |
| **4. Generate Program Rundown** | `ranked_storylines` (list) | `program_segments` (list) | `segment` |
| **5. Generate Segment Script** | `segment` (object) | `generated_script` (object) | `script` |
| **6. Live Desk Update** | `live_event` (object) | `live_update_script` (object) | `storyline`, `segment`, `script` |
| **7. Breaking News Alert** | `news_item` (object) | `breaking_alert_script` (object) | `storyline`, `segment`, `script` |
| **8. Post-Game Recap** | `completed_event` (object) | `recap_script` (object) | `storyline`, `segment`, `script` |
| **9. Generate Social Derivatives** | `script` (object) | `social_posts` (list) | `clip_candidate`, `social_post` |

## Agent Inventory

Three primary agents will orchestrate the workflows:

*   **`desk-program-agent` (Scheduled)**: This agent is responsible for creating scheduled content, such as daily briefings and pre-game shows. It runs on a fixed schedule, executing workflows 1 through 5 to generate a full program rundown and script.
*   **`desk-reactive-agent` (Event-Driven)**: This agent listens for real-time triggers from live games or breaking news feeds. It executes workflows 6, 7, and 8 to generate immediate, in-the-moment content.
*   **`desk-executor` (Operator-Driven)**: An optional agent that allows for human-in-the-loop (HITL) control. An operator can use this agent to manually trigger workflows, override storyline rankings, or approve generated scripts before publishing.

## Prompt Inventory

The content generation is powered by a set of specialized prompts:

| Prompt | Purpose |
| :--- | :--- |
| **1. `detect-storylines`** | Analyzes raw event data to identify potentially newsworthy storylines. |
| **2. `rank-storylines`** | Evaluates a list of storylines against editorial rules and assigns an urgency score. |
| **3. `generate-script`** | Creates a full script for a segment based on a set of storylines. |
| **4. `live-desk-update`** | Generates a concise script for a live game event. |
| **5. `breaking-news-headline`** | Crafts a compelling headline for a breaking news alert. |
| **6. `generate-title-options`** | Produces several engaging YouTube titles for a given script. |
| **7. `generate-clip-hooks`** | Writes short, attention-grabbing hooks for social media clips. |
| **8. `generate-social-posts`** | Creates formatted posts for various social media platforms from a source script. |

## Gap Analysis: REUSE vs. NEW

We will leverage existing Machina templates and skills where possible to accelerate development.

### REUSE
*   **Connectors (`sports-skills`)**: We will heavily reuse the existing sports data connectors.
    *   `football-data`, `nfl-data`, `nba-data` for core game data.
    *   `sports-news` for breaking news and off-field events.
    *   `kalshi`, `polymarket` for betting market data.
    *   `metadata` for team and player information.
*   **Prompt Invocation (`machina-templates/chat-completion`)**: The basic pattern of invoking LLMs via `machina-ai` or `google-genai` connectors will be reused from the `chat-completion` template.
*   **Scheduling & Orchestration (`machina-templates/template-superbowl-lix`, `nfl-podcast-generator`)**: The agent patterns for scheduled execution and chaining workflows will be adapted from these templates.
*   **Script Generation (`machina-templates/psg-podcast-generator`, `daily-football-recap`)**: The fundamental structure of generating scripts from data inputs will be based on these templates.
*   **Social Derivatives (`machina-templates/social-media-generator`)**: The workflow for creating social media posts from a primary piece of content will be adapted from this template.

### NEW
*   **Editorial Orchestration (`detect-storylines`, `rank-storylines`)**: The core logic for identifying and prioritizing what's newsworthy is a novel component of this project. This will require new workflows and sophisticated prompts.
*   **Live Content Workflows (`live-desk-update`, `breaking-news-alert`)**: The reactive workflows for handling real-time events are net-new.
*   **Shared Content Data Model**: The specific data model (`event`, `storyline`, `segment`, etc.) is custom to this project and will need to be implemented in the mappings and workflow outputs.
*   **Desk Agents**: The specific configurations and logic for the `desk-program-agent` and `desk-reactive-agent` will be new.
