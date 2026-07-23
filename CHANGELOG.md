# Changelog

## Unreleased

- Added screen and head-top tactile input to a durable VPS event queue.
- Added MCP tools to read and acknowledge pending touches.
- Added head-touch swipe direction while preserving screen coordinates.
- Added validation, deduplication, retention, ordered unread pagination, and tests.
- Documented the required PlatformIO `PubSubClient` dependency for clean builds.
- Removed the immediate model responder and `stackchan/reply` path; the tactile
  bridge now needs no model API key.
- Added a persistent Codex instruction template for checking pending touches at
  the start of each conversational turn.

## v0.1.1

- Fixed repeated remote photo captures timing out after the JPEG reached the relay.
- Added `X-Photo-Version`, image-hash fallback, cache-busting requests, a longer
  photo polling window, and camera frame-acquisition retries.
