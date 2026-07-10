# Architecture

```text
AI client / MCP host
        |
        | HTTPS: /stackchan/mcp
        v
      Nginx
        |
        | HTTP localhost:18003/mcp
        v
FastMCP server
        |
        | MQTT publish
        v
Mosquitto on VPS  <---------- StackChan on phone hotspot
        |                              |
        | face/capture topics           | HTTP JPEG upload
        v                              v
 expression/camera              photo relay :18090
                                      |
                                      | localhost GET latest.jpg
                                      v
                                FastMCP returns image
```

## MQTT topics

- `stackchan/face`: payload is one of `neutral`, `happy`, `sleepy`, `doubt`, `sad`, `angry`.
- `stackchan/capture`: any payload triggers a photo capture.

## Tested recovery behavior

If the phone hotspot is turned off and later turned back on, press StackChan's reboot button to reconnect.
Automatic reconnect after hotspot loss is not implemented in v0.1.
