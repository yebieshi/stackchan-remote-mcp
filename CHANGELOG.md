# Changelog

## v0.1.1

- Fixed repeated remote photo captures timing out after the JPEG had already
  reached the relay.
- Added `X-Photo-Version` to the relay.
- Added image hash fallback and cache-busting requests to the MCP server.
- Extended the photo polling window to 15 seconds.
- Added defensive camera frame-acquisition retries.
- Kept the camera preview subwindow enabled.
