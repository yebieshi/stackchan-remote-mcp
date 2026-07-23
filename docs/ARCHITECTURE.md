# 架构

```text
AI / MCP 客户端
      |
      | HTTPS: /stackchan/mcp
      v
    Nginx
      |
      | localhost:18003/mcp
      v
FastMCP 服务
  |        |                                  |
  |        | 读取最新 JPEG                    | 读取 / 确认未读触摸
  |        v                                  v
  |   Photo Relay :18090                 touch event JSONL
  |        ^                                  ^
  |        | HTTP JPEG 上传                   | MQTT 订阅
  |        |                                  |
  |        +----------- StackChan ------------+
  |                       ^
  | MQTT 发布             | MQTT 接收
  v                       |
Mosquitto broker ----------+
  |
  +-- stackchan/face ------> StackChan 更新表情
  +-- stackchan/capture ---> StackChan 拍照并上传
  <--- stackchan/touch ----- StackChan 上报屏幕 / 头顶触摸
```

三类功能共用同一台 VPS，但数据方向不同：

1. 表情控制是 AI 经 FastMCP 和 MQTT 向 StackChan 下发。
2. 拍照命令同样经 MQTT 下发，JPEG 则由 StackChan 直接上传到 Photo Relay，再由
   FastMCP 取回并返回给 AI 客户端。
3. 触摸事件从 StackChan 经 MQTT 反向上报，FastMCP 后台监听并持久保存；下一次
   对话读取后才确认。

## MQTT 主题

- `stackchan/face`：载荷为 `neutral`、`happy`、`sleepy`、`doubt`、`sad` 或
  `angry`，用于远程切换表情。
- `stackchan/capture`：任意消息触发摄像头拍照。
- `stackchan/touch`：设备向 VPS 上报触摸 JSON。

触摸 JSON 的必需字段是 `event`、`device`、`zone`、`gesture` 和
`duration_ms`。屏幕触摸可带坐标；头顶抚摸可带
`direction=forward|backward`；`source_event_id` 用于去重。

## 拍照生命周期

1. AI 调用 `stackchan_see`。
2. FastMCP 记录当前照片版本和内容哈希，再向 `stackchan/capture` 发布命令。
3. StackChan 获取新帧，通过 HTTP 把 JPEG 上传到 Photo Relay。
4. Photo Relay 保存最新图片并递增 `X-Photo-Version`。
5. FastMCP 轮询新版本；版本号或内容哈希变化后，把新 JPEG 返回给 AI 客户端。

版本号、纳秒修改时间、缓存规避参数和 SHA-256 内容比较共同避免连续拍照时误取旧图。

## 触摸生命周期

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

## 恢复行为

如果手机热点关闭后再开启，当前已验证的恢复方式是按 StackChan 重启键。自动恢复
热点连接尚未验证。
