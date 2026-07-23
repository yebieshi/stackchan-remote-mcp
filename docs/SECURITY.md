# Security notes

The tested v0.1 setup prioritizes a small, reproducible proof of concept.

## Important limitations

1. MQTT on port 1883 is plaintext. The username, password, topics, and payloads can be observed by anyone able to intercept that traffic.
2. The direct photo relay uses HTTP. The relay token and uploaded images are not encrypted in transit.
3. The relay stores the newest camera image on disk.
4. AI clients connected to the MCP endpoint can trigger the camera. Treat access to the MCP URL as camera access.
5. The upstream firmware starts an FTP server with default credentials unless you change or disable that upstream behavior.
6. Touch events reveal presence and physical interaction timing. Treat the touch
   JSONL, acknowledgement cursor, and reply history as private data.
7. Immediate replies send a minimized touch description and the configured persona
   prompt to the selected model provider. For OpenAI, the responder sets
   `store: false`; every provider's processing and account-level data controls
   still apply.
8. The model API key and private persona file are high-value secrets on the VPS.

## Before public or long-term use

- Generate new, unique MQTT and relay credentials.
- Never commit `RemoteConfig.h` or `/etc/stackchan-remote-mcp.env`.
- Restrict firewall ports as much as possible.
- Prefer TLS for MQTT and HTTPS for photo uploads in a future hardened deployment.
- Keep the MCP endpoint behind HTTPS and access controls supported by your MCP client/platform.
- Review camera consent and privacy before using the device around other people.
- Keep `/etc/stackchan-remote-mcp.env` mode `600`, keep the persona file readable
  only by root and the `stackchan` group, and never commit either file.
- When using OpenAI, use a stable privacy-preserving
  `STACKCHAN_MODEL_SAFETY_IDENTIFIER`; do not use a name, email address, or other
  direct identifier.
- Keep the touch prompt lean and avoid copying unrelated conversation history.
- Set retention appropriate to the relationship context, and periodically remove
  old touch/reply history from `/var/lib/stackchan-remote-mcp`.

This repository documents the currently tested setup; it does not claim the network transport is hardened.
