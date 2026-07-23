# Changelog

## Unreleased

- Added the tactile bridge from CoreS3 touch input to a durable VPS event queue.
- Added MCP tools to read and acknowledge touch events.
- Added an optional immediate model worker using a private persona.
- Added native OpenRouter Chat Completions support with GPT-4.1 nano as the
  low-latency example configuration.
- Added a concise, understated touch-reply style guard and prevented prior
  replies from becoming accidental style examples.
- Added SiliconFlow Chat Completions support alongside OpenAI Responses support.
- Added `stackchan/reply` display handling and non-blocking local touch feedback.
- Added touch validation, deduplication, retention, and helper tests.

## v0.1.1

- Fixed repeated remote photo captures timing out after the JPEG had already
  reached the relay.
- Added `X-Photo-Version` to the relay.
- Added image hash fallback and cache-busting requests to the MCP server.
- Extended the photo polling window to 15 seconds.
- Added defensive camera frame-acquisition retries.
- Kept the camera preview subwindow enabled.
