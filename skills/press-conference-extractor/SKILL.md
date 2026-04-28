# Press Conference Extractor Skill

This skill processes a raw transcript from a press conference and extracts structured insights.

## Use Case

Use this skill when you have a long text of a press conference and need to quickly identify the key topics discussed, who said what, and which quotes are the most impactful for news reporting or analysis.

## Inputs

- `transcript`: A single long string containing the full text of the press conference.

## Example Output

The skill returns a JSON object containing:
- A list of topics discussed with summaries.
- A detailed list of quotes, each with a speaker, topic, sentiment, and a calculated "newsworthiness" score.
- A ranked list of the top 5 most newsworthy quotes with a justification for their ranking.

This structured output allows content teams to efficiently build narratives, create social media content, or perform deeper analysis without manually parsing the entire transcript.
