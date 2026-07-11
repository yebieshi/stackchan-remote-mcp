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
