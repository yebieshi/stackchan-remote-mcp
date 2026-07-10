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

