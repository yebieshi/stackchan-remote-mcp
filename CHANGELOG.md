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
- Verified the complete CoreS3-to-VPS-to-Codex touch path on hardware, including
  head taps, a backward head stroke, a screen stroke, unread retrieval, and
  acknowledgement.

## v0.1.1

- Fixed repeated remote photo captures timing out after the JPEG had already
  reached the relay.
- Added `X-Photo-Version` to the relay.
- Added image hash fallback and cache-busting requests to the MCP server.
- Extended the photo polling window to 15 seconds.
- Added defensive camera frame-acquisition retries.
- Kept the camera preview subwindow enabled.
