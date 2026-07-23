# Firmware overlay

`main.cpp` 用于覆盖 `ronron-gh/AI_StackChan_Ex` 的
`firmware/src/main.cpp`。复制 `RemoteConfig.example.h` 为同目录下的私有
`RemoteConfig.h`，填写配置后用 PlatformIO 编译和刷写。

在上游 `platformio.ini` 的目标 CoreS3 环境 `lib_deps` 中加入：

```ini
knolleary/PubSubClient @ ^2.8
```

## 触觉桥

- 正面屏幕：在配置区域内识别 `tap`、`press`、`stroke`
- 头顶三段电容板：通过上游 `driver/HeadTouchSensor.h` 识别按下、松开与前后滑动
- 事件发布到 `stackchan/touch`
- MQTT 断开时最多缓存 8 条，恢复后重试
- 本 overlay 不接收模型回复，也不控制头部两侧灯带

屏幕区域、移动距离和长按时长可在 `RemoteConfig.h` 中调整。头顶触摸由实体传感器
直接识别，不使用屏幕坐标。

`RemoteConfig.h` 含密钥且已被 Git 忽略，不要提交。
