# Machina Media: AI Sports Desk

## Product Thesis

Machina Media is an always-on AI sports desk designed for a new generation of content consumption. Our primary focus is on producing engaging, timely, and relevant sports content for YouTube-first distribution. This is not a traditional blog engine or a wire service; it's a fully automated content factory, leveraging Machina's AI capabilities to create a proprietary media channel. We own the distribution and the narrative.

## 5-Layer Architecture

The system is designed as a five-layer content pipeline, ensuring a structured and scalable approach to content creation:

1.  **Data Ingestion**: Raw data from various sports feeds (scores, stats, news, betting markets) is ingested into the system.
2.  **Normalization**: The raw data is transformed into a canonical `Event` object, our shared internal representation of a sporting event. This ensures consistency for all downstream processes.
3.  **Editorial Orchestration**: This is the core of our system. AI agents analyze the normalized data to identify and rank interesting `Storylines`. This layer acts as an automated executive producer, deciding what's newsworthy.
4.  **Content Generation**: Based on prioritized storylines, the system generates various content formats, from `Segments` and `Scripts` to social media `Clip Candidates`.
5.  **Publishing Outputs**: The generated content is formatted and published to our target platforms, primarily YouTube Live, with derivatives for YouTube Shorts, X, TikTok, and Instagram.

## v1 Scope

The initial version (v1) will focus on establishing the core content pipeline with the following scope:

*   **Sports Coverage**: Football (NFL) and Basketball (NBA).
*   **Content Formats**:
    *   **Scheduled Briefing Blocks**: Daily or pre-game shows covering the latest news and updates.
    *   **Triggered Live Desk Hits**: Automated updates and analysis during live games based on significant events (e.g., score changes, injuries).
    *   **Post-Game Recaps**: Summaries and highlights generated shortly after a game concludes.
    *   **Breaking News Alerts**: Rapid responses to major off-the-field events like trades or injuries.
*   **Operating Model**: The system is not a literal 24/7 live stream on day one. It operates in scheduled blocks and reacts to live events as they happen.
*   **Data Sources**: We will rely on publicly available and free-tier sports data feeds. No paid or rights-dependent workflows will be implemented in v1.

## Primary Surface

*   **YouTube Live**: The main destination for our long-form content, such as briefings and live game coverage.
*   **Secondary Surfaces**: YouTube Shorts, X, TikTok, and Instagram will be used for short-form content and promotional clips derived from the main broadcast.

## Editorial Rules

The following rules govern the editorial prioritization of storylines:

*   **Prioritize game-changing moments**: Big plays, scoring swings, and lead changes are top priority.
*   **Highlight player milestones**: Records, significant achievements, and notable performances.
*   **Cover injuries to key players**: Especially those with significant fantasy sports or betting market implications.
*   **Track betting market movements**: Significant line shifts or odds changes are newsworthy.
*   **Identify potential upsets**: When an underdog is outperforming expectations, that's a story.
*   **Ignore minor stats**: Avoid routine plays or stats that don't contribute to a larger narrative.
*   **Deprioritize non-essential news**: Off-field stories without immediate impact on the game are secondary.

## Non-Goals

*   **24/7 Live Streaming (v1)**: Continuous live broadcasting is a future goal, not a v1 requirement.
*   **Paid Data Feeds**: We will not integrate with premium, rights-encumbered data sources initially.
*   **Human-in-the-Loop (HITL) Operation**: While the system will allow for manual overrides, the primary goal is full automation.
*   **In-depth analysis and opinion**: The initial focus is on factual, timely reporting. Deep analysis and opinionated takes are out of scope for v1.
