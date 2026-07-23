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
   |          |
   |          +---- reads/acks ---- touch event JSONL
   |                                  ^
   | MQTT publish                     | MQTT subscribe
   v                                  |
Mosquitto on VPS  <------------ StackChan on phone hotspot
   |       ^                              |
   |       |                              +-- local touch expression
   |       +---- stackchan/reply ---------+
   |                                      |
   +-- stackchan/touch --> touch responder
                              |
                              | configured model API
                              v
                 OpenRouter / SiliconFlow / OpenAI

StackChan -- HTTP JPEG upload --> photo relay :18090
                                      |
                                      | localhost GET latest.jpg
                                      v
                                FastMCP returns image
```

## MQTT topics

- `stackchan/face`: payload is one of `neutral`, `happy`, `sleepy`, `doubt`, `sad`, `angry`.
- `stackchan/capture`: any payload triggers a photo capture.
- `stackchan/touch`: device-to-VPS JSON event with `event`, `device`, `zone`,
  `gesture`, `duration_ms`, optional coordinates/timestamp, and a deduplication ID.
- `stackchan/reply`: VPS-to-device JSON containing model-generated `text`,
  `expression`, and `display_ms`.

## Touch lifecycle

1. The CoreS3 firmware recognizes a touch in the configured face zone.
2. StackChan changes expression immediately, before any network operation.
3. On release, the firmware classifies the gesture and queues a JSON event.
4. The MCP service persists the event. It remains unread until explicitly acknowledged.
5. The responder batches a short burst of touches, calls the configured model API
   (OpenRouter or SiliconFlow Chat Completions, or OpenAI Responses), and
   publishes a concise reply.
6. StackChan displays the reply and later restores the last remotely commanded face.

The persistent MCP path and immediate response path are deliberately independent.
If the model call fails, the touch is still recorded. If the MCP client is not
open, the responder can still answer on the physical device.

## Tested recovery behavior

If the phone hotspot is turned off and later turned back on, press StackChan's reboot button to reconnect.
Automatic reconnect after hotspot loss is not implemented in v0.1.
