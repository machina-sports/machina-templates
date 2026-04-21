# Architecture

## LLM Provider

The prompts in this template use `google-genai` as the LLM provider, specifically with `provider: vertex_ai` and `location: global`. The model used is `gemini-2.5-flash`. This choice was made for its balance of performance, cost, and availability.

The connector is configured as follows in all prompt tasks:

```yaml
connector:
  name: google-genai
  command: invoke_prompt
  model: gemini-2.5-flash
  provider: vertex_ai
  location: global
```

This ensures consistency across all content generation workflows within the `machina-media` template.
