# Tested status

Tested on an M5Stack CoreS3 build environment with AI_StackChan_Ex.

Verified:

- StackChan connects to an iPhone hotspot with compatibility mode enabled.
- The hotspot connection remained stable for more than one hour.
- Remote MCP initialization succeeds through Nginx.
- `stackchan_face` changes expressions.
- `stackchan_see` triggers a photo and returns the new image.
- After hotspot interruption, turning the hotspot back on and rebooting StackChan restores the connection.

Not implemented:

- Speech topic such as `stackchan/say`.
- Automatic recovery without reboot after the hotspot disappears.
- TLS for MQTT and the direct photo-upload path.

## Touch bridge implementation status

Implemented:

- CoreS3 face-zone recognition for tap, press, and stroke.
- Immediate local expression before network delivery.
- Eight-event firmware queue for temporary MQTT disconnection.
- Durable JSONL event store, device-event deduplication, and acknowledgement cursor.
- MCP tools for reading and acknowledging touch events.
- Low-latency OpenRouter / SiliconFlow Chat Completions and OpenAI Responses
  worker with MQTT reply display.
- Short local history for continuity across consecutive touch responses.

Automated server tests cover validation, persistence, acknowledgement, pruning,
deduplication, all supported provider paths, both model request formats, and
output extraction.

Still requires production verification:

- Compile and flash against the exact AI_StackChan_Ex/CoreS3 environment.
- Calibrate the physical touch zone and gesture thresholds.
- Measure end-to-end model response latency over the phone hotspot.
- Confirm Chinese text wrapping and the preferred reply display duration.
- Verify systemd restart behavior and real API/MQTT failure recovery.

## Open-source package verification

The packaged v0.1 repository was tested in a separate Python virtual environment
and on a separate MCP port, without replacing the already-running production copy.

Verified:

- Dependencies install successfully after installing `python3-venv`.
- The environment-variable based configuration starts successfully.
- FastMCP listens on the separate test port.
- Nginx reverse proxy works when the upstream `Host` is set to the local MCP address.
- Remote expression changes succeed.
- Remote photo capture and image return succeed.

## v0.1.1 repeated-capture fix

A repeated-photo timeout was reproduced even though the device log showed both
`frame acquired` and `uploaded ... -> relay OK`. The cause was stale/new-photo
detection at the relay/MCP layer, not camera capture.

The fix adds:

- A monotonically increasing `X-Photo-Version` header for every upload.
- Nanosecond file modification time as additional metadata.
- Cache-busting requests and SHA-256 image-content comparison in the MCP server.
- A 15-second polling window for the new photo.
- Short camera frame-acquisition retries while keeping the preview subwindow enabled.

After the fix, three consecutive remote photo captures returned three distinct
images successfully.
