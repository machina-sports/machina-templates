# Strict image receipts

`invoke_image` preserves existing defaults for legacy callers. New governed
workflows opt in with the boolean `strict_image: true`, an explicit provider,
model name and nonempty prompt. Invalid size/aspect/reference inputs fail closed.

The Machina AI router allows the explicit Vertex image model
`gemini-3.1-flash-image` and forwards `strict_image` and `image_size` as options.
This is an image capability allowance, not a text default or fallback change.
Deployment-level model allowlists can still restrict it; verify the actual pod.

Strict mode uses image-only response modalities, 1K by default, the supplied
aspect ratio and a 120-second SDK timeout. A non-success finish reason, provider
block, text-only response, unsupported image MIME or undecodable bytes cannot
produce a success receipt. Empty prompt feedback without a block is not a refusal.
Thought parts are not treated as image assets. The creative prompt is not logged.

Successful data contains the existing image path/format/prompt/model plus
`provider`, `model_version`, `synthetic: true`, UTC `generated_at`, `width`,
`height`, and `sha256` of the actual WebP bytes. `model_version` uses the provider
reported version when supplied, otherwise the requested model ID; it is not a
claim that the provider supplied an immutable model version.

Product consumers remain responsible for event/revision binding, safe storage,
uploaded-byte verification, durable retries and operator review. This connector
does not approve assets or implement product-specific persistence.

Offline tests: `python -m pytest tests/test_google_image_contract.py
connectors/machina-ai/tests -q`. The CI image job also loads the full connector
with Python 3.11, google-genai 1.49.0, langchain-google-vertexai 3.0.1,
langchain-google-genai 3.0.0 and Pillow 10.4.0. Tests use no model credentials.

For the Broadcast release, import only reviewed shared connector definitions.
Do not import the repository root or migrate the independently versioned
canonical package along with this image capability.
