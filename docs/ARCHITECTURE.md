# Architecture

```text
AI client / MCP host
        |
        | HTTPS: /stackchan/mcp
        v
      Nginx
        |
        | localhost:18003/mcp
        v
FastMCP server -------- reads / acknowledges -------- touch event JSONL
   |                                                   ^
   | MQTT publish                                      | MQTT subscribe
   v                                                   |
Mosquitto on VPS <------------------------------- StackChan

StackChan -- HTTP JPEG upload --> photo relay :18090
                                      |
                                      v
                                FastMCP returns image
```

## MQTT topics

- `stackchan/face`：远程表情名称。
- `stackchan/capture`：任意消息触发拍照。
- `stackchan/touch`：设备到 VPS 的触摸 JSON。

触摸 JSON 的必需字段是 `event`、`device`、`zone`、`gesture` 和
`duration_ms`。屏幕触摸可带坐标；头顶抚摸可带
`direction=forward|backward`；`source_event_id` 用于去重。

## Touch lifecycle

1. 固件从正面屏幕或头顶三段电容板识别一次接触。
2. 松开后，固件分类为 `tap`、`press` 或 `stroke` 并生成设备事件 ID。
3. 若 MQTT 暂时断开，事件留在设备的 8 条内存队列中。
4. MCP 服务订阅触摸主题、校验并保存 JSONL；重复发送不会产生重复记录。
5. 下一次用户发消息时，AI 先读取最早的未读触摸。
6. AI 把触摸自然融入回应后，确认这一批最后一个服务器事件 ID。

这是“至少处理一次”的设计：如果一次对话中断在确认之前，事件下次仍会返回；相比
静默丢失，偶尔重复感知更容易发现和恢复。

普通 Chat/Codex 对话不能由 MQTT 主动唤醒。因此自动取回由 MCP 工具说明与用户的
持久个人指令共同触发，而不是 VPS 主动推送。

## Recovery

如果手机热点关闭后再开启，当前已验证的恢复方式是按 StackChan 重启键。自动恢复
热点连接尚未验证。
