# Security notes

当前方案是可复现的私人原型，还没有完成网络安全加固：

1. MQTT 1883 是明文，凭据和触摸消息可能被链路上的第三方看到。
2. 图片中转使用 HTTP，relay token 和照片在传输中未加密。
3. relay 会在磁盘保存最新照片。
4. 能访问 MCP 的客户端可以触发摄像头。
5. 上游固件可能以默认凭据启动 FTP；请修改或关闭。
6. 触摸 JSONL 和确认游标会暴露互动时间，应当视为私人数据。

触觉桥不调用第三方模型 API，不需要模型 Key，也不会把触摸和 persona 另行发送给
OpenAI、OpenRouter 或硅基流动。AI 客户端取回事件后的数据处理仍受该客户端自身的
隐私条款约束。

长期使用前：

- 为 MQTT、relay 和 MCP 使用互不相同的强凭据
- 不提交 `RemoteConfig.h` 或 `/etc/stackchan-remote-mcp.env`
- 防火墙只开放确实需要的端口
- 让 MCP 保持在 HTTPS 和访问控制之后
- 后续为 MQTT 和图片上传加入 TLS
- 定期清理 `/var/lib/stackchan-remote-mcp/touch-events.jsonl`
- 在他人在场时，考虑摄像头和触摸记录的知情与隐私
