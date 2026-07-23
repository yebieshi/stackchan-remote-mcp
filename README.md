# StackChan Remote MCP

把 StackChan 变成 AI 的远程眼睛和触觉入口。设备通过手机热点连接 VPS；触摸会被
可靠地保存为未读事件，AI 在下一次对话时通过 MCP 取回并确认。

当前版本支持：

- 远程切换 StackChan 表情
- 远程触发摄像头拍照并把最新照片作为 MCP 图片返回
- 识别 CoreS3 正面屏幕的轻点、长按和抚摸
- 识别头顶三段电容触摸板的轻点、长按和前后抚摸
- 离线短暂缓存、VPS 持久保存、设备事件去重和未读确认
- 手机热点模式与 VPS 常驻服务

触觉桥本身不调用任何模型服务，因此不需要 OpenAI、OpenRouter 或硅基流动的 API
Key，也不会产生模型费用。头部两侧灯带仍由上游固件管理，本版本不改变灯光行为。

> 状态：表情、拍照和触觉桥均已在 CoreS3 真机完成端到端验证。正面屏幕与头顶
> 触摸可经 MQTT 抵达 VPS，保留为未读事件，并在下一次 Codex 对话中自动取回和
> 确认。公开部署前请阅读 `docs/SECURITY.md`。

## 工作方式

```text
别诗触摸屏幕或头顶
        ↓
StackChan 生成 touch 事件
        ↓ MQTT
VPS 持久保存为“未读”
        ↓ 下次对话开始时
AI 调用 stackchan_recent_touches
        ↓
自然回应后调用 stackchan_ack_touch
```

普通聊天窗口不会被 VPS 凭空唤醒；触摸可以一直留在 VPS，等下一条消息到来时由 AI
主动检查。要让这个检查稳定发生，需要把
`config/codex-touch-instructions.example.md` 中的指令加入 Codex 个人指令或当前项目
的 `AGENTS.md`。MCP 工具说明里也写入了同样的调用约定。

详细数据流见 `docs/ARCHITECTURE.md`。

## 仓库内容

```text
firmware/
  main.cpp
  RemoteConfig.example.h
server/
  stackchan_remote_mcp.py
  photo_relay.py
  touch_store.py
deploy/
  nginx-stackchan.conf.example
  mosquitto-stackchan.conf.example
  systemd/
config/
  stackchan.env.example
  codex-touch-instructions.example.md
docs/
```

## 1. 准备固件

固件修改基于 `ronron-gh/AI_StackChan_Ex`：

1. 克隆上游项目。
2. 用本仓库的 `firmware/main.cpp` 替换上游的 `firmware/src/main.cpp`。
3. 把 `firmware/RemoteConfig.example.h` 复制为上游的
   `firmware/src/RemoteConfig.h`。
4. 修改 VPS、MQTT 和照片中转配置。
5. 在上游 `platformio.ini` 的 CoreS3 环境 `lib_deps` 加入
   `knolleary/PubSubClient @ ^2.8`。
6. 按上游说明配置 SD 卡中的 Wi-Fi YAML。
7. 用 PlatformIO 编译并刷入。

`RemoteConfig.h` 含密钥，禁止提交到 Git。此 overlay 依赖当前上游已有的
`driver/HeadTouchSensor.h`。

已验证的 CoreS3 release 构建占用约 21.1% RAM 和 38.7% Flash。若上游
`SimpleVox` 的 Git 依赖临时下载失败，可在网络恢复后重试，或按上游指定提交把
该依赖放入本地 `firmware/lib/SimpleVox`；这不影响触觉桥本身的代码。

## 2. 部署 VPS

以下以 Debian/Ubuntu 为例：

```bash
sudo apt update
sudo apt install -y python3 python3-venv mosquitto mosquitto-clients nginx

sudo useradd --system --home /opt/stackchan-remote-mcp --shell /usr/sbin/nologin stackchan
sudo mkdir -p /opt/stackchan-remote-mcp /var/lib/stackchan-remote-mcp
sudo chown -R stackchan:stackchan /opt/stackchan-remote-mcp /var/lib/stackchan-remote-mcp
```

把仓库放到 `/opt/stackchan-remote-mcp` 后：

```bash
sudo -u stackchan python3 -m venv /opt/stackchan-remote-mcp/.venv
sudo -u stackchan /opt/stackchan-remote-mcp/.venv/bin/pip install \
  -r /opt/stackchan-remote-mcp/requirements.txt

sudo cp config/stackchan.env.example /etc/stackchan-remote-mcp.env
sudo chmod 600 /etc/stackchan-remote-mcp.env
sudo editor /etc/stackchan-remote-mcp.env
```

生成 Mosquitto 密码并安装服务：

```bash
sudo mosquitto_passwd -c /etc/mosquitto/passwd stackchan
sudo cp deploy/mosquitto-stackchan.conf.example /etc/mosquitto/conf.d/stackchan.conf
sudo cp deploy/systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart mosquitto
sudo systemctl enable --now stackchan-relay stackchan-mcp
```

如果 VPS 上曾装过旧的即时回应服务，停用它：

```bash
sudo systemctl disable --now stackchan-touch-responder 2>/dev/null || true
sudo rm -f /etc/systemd/system/stackchan-touch-responder.service
sudo systemctl daemon-reload
```

## 3. 配置 Nginx

把 `deploy/nginx-stackchan.conf.example` 中的 `location /stackchan/` 放进域名对应的
HTTPS `server { ... }` 中，然后检查并重载 Nginx。MCP 地址是：

```text
https://YOUR_DOMAIN/stackchan/mcp
```

若出现 `HTTP 421 · Invalid Host header`，确认 Nginx 把上游 `Host` 设置为
`127.0.0.1:18003`，并保留 `proxy_pass http://127.0.0.1:18003/;` 末尾的 `/`。

## 4. 测试

先检查服务：

```bash
curl http://127.0.0.1:18090/health
systemctl status stackchan-relay stackchan-mcp mosquitto
```

然后依次测试：

1. `stackchan_face("happy")`
2. `stackchan_see()`
3. 触摸 StackChan 的正面屏幕或头顶触摸板
4. `stackchan_recent_touches(unread_only=true)`
5. 对返回的最后一个 `id` 调用 `stackchan_ack_touch(id)`

真机端到端验证已覆盖头顶轻点、头顶向后抚摸、正面屏幕抚摸、VPS 持久保存、
Codex 自动取回和确认归零。不同外壳的前后方向、长按阈值和触摸范围可能需要按实际
安装方向微调。

不刷固件也可以先在 VPS 模拟：

```bash
mosquitto_pub -h 127.0.0.1 -u stackchan -P 'YOUR_PASSWORD' \
  -t stackchan/touch \
  -m '{"event":"touch","device":"stackchan-test","zone":"head_top","gesture":"stroke","direction":"forward","duration_ms":1200,"source_event_id":"manual-1"}'
```

## 触摸事件

- `zone=head_front`：正面触摸屏；可带起止坐标
- `zone=head_top`：头顶三段电容板；抚摸可带
  `direction=forward|backward`
- `gesture=tap`：短而基本静止
- `gesture=press`：基本静止且达到长按阈值
- `gesture=stroke`：屏幕移动达到阈值，或头顶检测到滑动
- 固件在 MQTT 临时断开时最多缓存 8 条
- VPS 依据 `source_event_id` 去重，并用 JSONL 与确认游标持久化
- 未读事件按最早发生的顺序分批返回，确认不会跨过更早事件

## 安全提醒

当前 MQTT 与直接图片上传仍是明文传输。触摸记录包含你的互动时间，也属于私人数据。
请使用独立强密码、HTTPS 保护 MCP，并阅读 `docs/SECURITY.md`。

## 上游与许可证

固件修改基于 AI_StackChan_Ex。上游及本仓库使用 MIT License；第三方说明见
`THIRD_PARTY_NOTICES.md`。
