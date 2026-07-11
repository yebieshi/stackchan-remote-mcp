/*
 * StackChan Remote MCP firmware integration
 *
 * Based on AI_StackChan_Ex firmware/src/main.cpp:
 * https://github.com/ronron-gh/AI_StackChan_Ex
 *
 * Upstream license: MIT
 * Copyright (c) 2024 motoh
 *
 * Main modifications in this version:
 * - Connect to the Wi-Fi credentials loaded from YAML, with hotspot-friendly retries
 * - Subscribe to MQTT topics for expression changes and photo capture
 * - Upload captured JPEG images to a VPS relay
 *
 * See THIRD_PARTY_NOTICES.md for attribution and license details.
 */

#include <Arduino.h>
//#include <FS.h>
#include <SD.h>
#include <SPIFFS.h>
#include "share/Version.h"
#include "share/Mutex.h"
#include "share/SDUtil.h"
#include "share/DefaultParams.h"
#include <M5Unified.h>
#include <nvs.h>
#include <Avatar.h>
#include <faces/CatFace.h>
#include "StackchanExConfig.h" 
#include "Robot.h"
#include "mod/ModManager.h"
#include "mod/ModBase.h"
#include "mod/AiStackChan/AiStackChanMod.h"
#include "mod/AiStackChan/RealtimeAiMod.h"
#include "mod/Pomodoro/PomodoroMod.h"
#include "mod/PhotoFrame/PhotoFrameMod.h"
#include "mod/StatusMonitor/StatusMonitorMod.h"
#include "mod/VolumeSetting/VolumeSettingMod.h"
#include "mod/QRdisplay/QRdisplayMod.h"
#include "mod/EspNowRemote/EspNowRemoteMod.h"

#include "driver/PlayMP3.h"   //lipSync
#include "driver/TapDetect.h"

#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include <ArduinoJson.h>
#include <PubSubClient.h>
#include "SpiRamJsonDocument.h"
#include <ESP8266FtpServer.h>

#include "llm/ChatGPT/ChatGPT.h"
#include "llm/ChatGPT/FunctionCall.h"
#include "llm/ChatHistory.h"
#include "llm/Gemini/GeminiLive.h"

#include "WebAPI.h"

#if defined( ENABLE_CAMERA )
#include "driver/Camera.h"
#endif    //ENABLE_CAMERA

#include "driver/WatchDog.h"
#include "SDUpdater.h"
#include "DebugTools.h"
#include "RemoteConfig.h"

#if defined(USE_AUDIO_MODULE)
#include "driver/M5AudioModule.h"
#endif

StackchanExConfig system_config;
Robot* robot;
bool isOffline = false;

// ============================================================
// MQTT 设置（带出门用：StackChan 主动连 VPS broker，订阅表情指令）
// ============================================================
const char*    MQTT_BROKER        = STACKCHAN_MQTT_BROKER;
const uint16_t MQTT_PORT          = STACKCHAN_MQTT_PORT;
const char*    MQTT_USER          = STACKCHAN_MQTT_USER;
const char*    MQTT_PASS          = STACKCHAN_MQTT_PASS;
const char*    MQTT_TOPIC_FACE    = STACKCHAN_MQTT_TOPIC_FACE;
const char*    MQTT_TOPIC_CAPTURE = STACKCHAN_MQTT_TOPIC_CAPTURE;
const char*    MQTT_CLIENT_ID     = STACKCHAN_MQTT_CLIENT_ID;

// 照片上传到 VPS 中转服务（photo_relay.py）
const char*    PHOTO_RELAY_URL    = STACKCHAN_PHOTO_RELAY_URL;
const char*    PHOTO_RELAY_TOKEN  = STACKCHAN_PHOTO_RELAY_TOKEN;

WiFiClient   mqttWifiClient;
PubSubClient mqttClient(mqttWifiClient);
// ============================================================



// NTP接続情報　NTP connection information.
const char* NTPSRV      = "ntp.jst.mfeed.ad.jp";    // NTPサーバーアドレス NTP server address.
const long  GMT_OFFSET  = 9 * 3600;                 // GMT-TOKYO(時差９時間）9 hours time difference.
const int   DAYLIGHT_OFFSET = 0;                    // サマータイム設定なし No daylight saving time setting

//bool servo_home = false;
bool servo_home = true;
volatile bool espnow_remote_servo_override = false;

using namespace m5avatar;
Avatar avatar;
Face* customFace;
const Expression expressions_table[] = {
  Expression::Neutral,
  Expression::Happy,
  Expression::Sleepy,
  Expression::Doubt,
  Expression::Sad,
  Expression::Angry
};

FtpServer ftpSrv;   //set #define FTP_DEBUG in ESP8266FtpServer.h to see ftp verbose on serial


void lipSync(void *args)
{
  float gazeX, gazeY;
  int level = 0;
  DriveContext *ctx = (DriveContext *)args;
  Avatar *avatar = ctx->getAvatar();
  for (;;)
  {
#ifdef REALTIME_API
#ifdef REALTIME_API_WITH_TTS
    level = robot->tts->getLevel();
#else
    level = ((RealtimeLLMBase*)(robot->llm))->getAudioLevel();
#endif
#else
    level = robot->tts->getLevel();
#endif
    if(level<100) level = 0;
    if(level > 15000)
    {
      level = 15000;
    }
    float open = (float)level/15000.0;
    avatar->setMouthOpenRatio(open);
    avatar->getGaze(&gazeY, &gazeX);
    avatar->setRotation(gazeX * 5);
    delay(100);
  }
}


void servo(void *args)
{
  float gazeX, gazeY;
  DriveContext *ctx = (DriveContext *)args;
  Avatar *avatar = ctx->getAvatar();
  for (;;)
  {
#ifdef USE_SERVO
    if(espnow_remote_servo_override)
    {
      delay(100);
      continue;
    }

    if(!servo_home)
    {
      avatar->getGaze(&gazeY, &gazeX);
      robot->servo->moveTo((int)(15.0 * gazeX), (int)(10.0 * gazeY));
    } else {
      robot->servo->moveToOrigin();
    }
#endif
    delay(5000);
  }
}

void battery_check(void *args) {
  DriveContext *ctx = (DriveContext *)args;
  Avatar *avatar = ctx->getAvatar();
  for (;;)
  {
    int32_t batteryLevel = M5.Power.getBatteryLevel();
    if((batteryLevel < 95) && (batteryLevel != 0)){
      avatar->setBatteryIcon(true);
      avatar->setBatteryStatus(M5.Power.isCharging(), M5.Power.getBatteryLevel());
    }
    else{
      avatar->setBatteryIcon(false);    
    }
    delay(60000);
  }
}

bool Wifi_connection_check(unsigned long timeout_ms = 30000) {
  unsigned long start_millis = millis();

  while (WiFi.status() != WL_CONNECTED) {
    M5.Display.print(".");
    Serial.print(".");
    delay(500);

    if ((millis() - start_millis) >= timeout_ms) {
      Serial.println("");
      Serial.printf(
        "WiFi connection timeout. status=%d, elapsed=%lu ms\n",
        (int)WiFi.status(),
        millis() - start_millis
      );
      return false;
    }
  }

  Serial.println("");
  Serial.printf(
    "WiFi connected. SSID=%s, IP=%s, RSSI=%d dBm\n",
    WiFi.SSID().c_str(),
    WiFi.localIP().toString().c_str(),
    WiFi.RSSI()
  );
  return true;
}

bool WifiSmartConfig() {
#if defined(USE_LLM_MODULE)
  // LLMモジュール使用時は普通はオフラインが前提のため、Smart Config待ちはしない
  return false;
#else
  unsigned long start_millis = millis();
  WiFi.mode(WIFI_STA);
  WiFi.beginSmartConfig();
  M5.Display.println("Waiting for SmartConfig");
  Serial.println("Waiting for SmartConfig");
  while (!WiFi.smartConfigDone()) {
    delay(1000);
    M5.Display.print("#");
    Serial.print("#");
    // 30秒以上接続できなかったら抜ける
    if ( 30000 < millis() - start_millis) {
      Serial.println("");
      //Serial.println("Reset");
      //ESP.restart();
      return false;
    }
  }
  return true;
#endif
}

void time_sync(const char* ntpsrv, long gmt_offset, int daylight_offset) {
  struct tm timeInfo; 
  char buf[60];

  configTime(gmt_offset, daylight_offset, ntpsrv);          // NTPサーバと同期

  if (getLocalTime(&timeInfo)) {                            // timeinfoに現在時刻を格納
    Serial.print("NTP : ");                                 // シリアルモニターに表示
    Serial.println(ntpsrv);                                 // シリアルモニターに表示

    sprintf(buf, "%04d-%02d-%02d %02d:%02d:%02d\n",     // 表示内容の編集
    timeInfo.tm_year + 1900, timeInfo.tm_mon + 1, timeInfo.tm_mday,
    timeInfo.tm_hour, timeInfo.tm_min, timeInfo.tm_sec);

    Serial.println(buf);                                    // シリアルモニターに表示
  }
  else {
    Serial.print("NTP Sync Error ");                        // シリアルモニターに表示
  }
}


// ============================================================
// MQTT 回调 / 表情映射 / 重连
// ============================================================
#if defined(ENABLE_CAMERA)
void captureAndUpload();  // 前向声明，实体在 mqttReconnect 之后
#endif

void setFaceByName(const String& raw) {
  String n = raw;
  n.trim();
  n.toLowerCase();
  if      (n == "neutral") avatar.setExpression(Expression::Neutral);
  else if (n == "happy")   avatar.setExpression(Expression::Happy);
  else if (n == "sleepy")  avatar.setExpression(Expression::Sleepy);
  else if (n == "doubt")   avatar.setExpression(Expression::Doubt);
  else if (n == "sad")     avatar.setExpression(Expression::Sad);
  else if (n == "angry")   avatar.setExpression(Expression::Angry);
  else {
    // 也接受数字 0-5（对应 expressions_table 顺序）
    int idx = n.toInt();
    int total = sizeof(expressions_table) / sizeof(expressions_table[0]);
    if (idx >= 0 && idx < total) {
      avatar.setExpression(expressions_table[idx]);
    } else {
      Serial.printf("[MQTT] unknown face: %s\n", raw.c_str());
    }
  }
}

void mqttCallback(char* topic, byte* payload, unsigned int length) {
  String msg;
  msg.reserve(length);
  for (unsigned int i = 0; i < length; i++) msg += (char)payload[i];
  Serial.printf("[MQTT] %s => %s\n", topic, msg.c_str());
  if (String(topic) == MQTT_TOPIC_FACE) {
    setFaceByName(msg);
  } else if (String(topic) == MQTT_TOPIC_CAPTURE) {
#if defined(ENABLE_CAMERA)
    captureAndUpload();   // 收到拍照指令，拍一张传给VPS
#else
    Serial.println("[MQTT] capture requested but camera disabled");
#endif
  }
}

void mqttReconnect() {
  if (mqttClient.connect(MQTT_CLIENT_ID, MQTT_USER, MQTT_PASS)) {
    Serial.println("[MQTT] connected");
    mqttClient.subscribe(MQTT_TOPIC_FACE);
    mqttClient.subscribe(MQTT_TOPIC_CAPTURE);
    Serial.printf("[MQTT] subscribed: %s , %s\n", MQTT_TOPIC_FACE, MQTT_TOPIC_CAPTURE);
  } else {
    Serial.printf("[MQTT] connect failed, rc=%d (retry in 5s)\n", mqttClient.state());
  }
}

#if defined(ENABLE_CAMERA)
#include "esp_camera.h"
// 拍一张照片并 POST 到 VPS 中转服务
void captureAndUpload() {
  M5.In_I2C.release();

  // The camera preview may briefly hold a frame buffer. Retry for a short
  // period instead of failing the remote capture after a single attempt.
  camera_fb_t *fb = nullptr;
  const int maxAttempts = 20;

  for (int attempt = 1; attempt <= maxAttempts; attempt++) {
    fb = esp_camera_fb_get();
    if (fb) {
      Serial.printf("[CAM] frame acquired on attempt %d/%d\n", attempt, maxAttempts);
      break;
    }

    Serial.printf("[CAM] frame unavailable, retry %d/%d\n", attempt, maxAttempts);
    delay(100);
    yield();
  }

  if (!fb) {
    Serial.println("[CAM] capture failed after retries");
    return;
  }

  size_t jpg_len = 0;
  uint8_t *jpg_buf = NULL;
  bool ok = frame2jpg(fb, 80, &jpg_buf, &jpg_len);
  esp_camera_fb_return(fb);
  if (!ok) {
    Serial.println("[CAM] jpeg convert failed");
    return;
  }

  HTTPClient http;
  http.begin(PHOTO_RELAY_URL);
  http.addHeader("Content-Type", "image/jpeg");
  http.addHeader("X-Relay-Token", PHOTO_RELAY_TOKEN);
  int code = http.POST(jpg_buf, jpg_len);
  if (code == 200) {
    Serial.printf("[CAM] uploaded %u bytes -> relay OK\n", (unsigned)jpg_len);
  } else {
    Serial.printf("[CAM] upload failed, http=%d\n", code);
  }
  http.end();
  free(jpg_buf);
}
#endif

// ============================================================


ModBase* init_mod(void)
{
  ModBase* mod;
  if(!isOffline || robot->isAllOfflineService()){
#if defined(REALTIME_API)
    add_mod(new RealtimeAiMod(isOffline));
#else
    add_mod(new AiStackChanMod(isOffline));
#endif
  }
  add_mod(new StatusMonitorMod());
  add_mod(new VolumeSettingMod());
  //add_mod(new EspNowRemoteMod());
  //add_mod(new PomodoroMod(isOffline));
  //add_mod(new PhotoFrameMod(isOffline));
  //add_mod(new QRdisplayMod());
  mod = get_current_mod();
  mod->init();
  return mod;
}


void sw_tone()
{
  enterMutexAudio();
  M5.Mic.end();
  M5.Speaker.begin();
  delay(300);     // AtomS3Rはこのdelayがないと鳴らないときがある
  M5.Speaker.tone(1000, 100);
  delay(500);

  M5.Speaker.end();
  M5.Mic.begin();
  exitMutexAudio();
}
  
void alarm_tone()
{
  enterMutexAudio();
  M5.Mic.end();
  M5.Speaker.begin();

  for(int i=0; i<5; i++){
    M5.Speaker.tone(1200, 50);
    delay(100);
    M5.Speaker.tone(1200, 50);
    delay(100);
    M5.Speaker.tone(1200, 50);
    delay(1000);  
  }

  M5.Speaker.end();
  M5.Mic.begin();
  exitMutexAudio();
}

void init_mic_spk()
{
#if defined(USE_AUDIO_MODULE)
  initAudioModule();
#endif

  {
    auto micConfig = M5.Mic.config();
    //micConfig.stereo = false;
    micConfig.sample_rate = 16000;
#if defined(USE_AUDIO_MODULE)
    micConfig.pin_data_in = SYS_I2S_DIN_PIN;
    micConfig.pin_bck = SYS_I2S_SCLK_PIN;
    micConfig.pin_mck = SYS_I2S_MCLK_PIN;
    micConfig.pin_ws = SYS_I2S_LRCK_PIN;
#endif
    M5.Mic.config(micConfig);
  }
  M5.Mic.begin();

  { /// custom setting
    auto spk_cfg = M5.Speaker.config();
    /// Increasing the sample_rate will improve the sound quality instead of increasing the CPU load.
    spk_cfg.sample_rate = 64000; // default:64000 (64kHz)  e.g. 48000 , 50000 , 80000 , 96000 , 100000 , 128000 , 144000 , 192000 , 200000
    spk_cfg.task_pinned_core = APP_CPU_NUM;

#if defined(USE_AUDIO_MODULE)
    spk_cfg.pin_data_out = SYS_I2S_DOUT_PIN;
    spk_cfg.pin_bck = SYS_I2S_SCLK_PIN;
    spk_cfg.pin_mck = SYS_I2S_MCLK_PIN;
    spk_cfg.pin_ws = SYS_I2S_LRCK_PIN;
#endif
    M5.Speaker.config(spk_cfg);
  }
  //M5.Speaker.begin();
}

void setup()
{
  /// シリアル出力のログレベルを VERBOSEに設定
  //M5.Log.setLogLevel(m5::log_target_serial, ESP_LOG_VERBOSE);

  auto cfg = M5.config();

#if defined(ARDUINO_M5STACK_ATOMS3R)
  cfg.internal_spk = false;
  cfg.internal_mic = false;
  cfg.external_speaker.atomic_echo = true;
#endif
  cfg.serial_baudrate = 115200;   //M5Unified 0.1.17からデフォルトが0になったため設定
  M5.begin(cfg);

  ///// Debug /////
#if 0
  check_board();
  Wire.begin(); 
  i2c_scan(Wire);
  Wire1.begin(); 
  i2c_scan(Wire1);
#endif
  /////////////////

#if defined(ARDUINO_M5STACK_ATOMS3R)
  M5.Lcd.setTextSize(2);
  M5.Lcd.printf("Ver.%s\n", FW_VERSION);
#else
  M5.Lcd.setFont(&fonts::lgfxJapanGothic_20);
  M5.Lcd.setTextSize(1);
  M5.Lcd.println("AI Stack-chan Ex [・＿・]");
  M5.Lcd.printf("Firmware Version: %s\n", FW_VERSION);
#endif

  initMutex();

#if defined(ENABLE_SD_UPDATER)
  // ***** for SD-Updater *********************
  SDU_lobby("AiStackChanEx");
  // ******************************************
#endif

  //auto brightness = M5.Display.getBrightness();
  //Serial.printf("Brightness: %d\n", brightness);

  init_mic_spk();

  /// settings
#if defined(ARDUINO_M5STACK_ATOMS3R)
  if (SPIFFS.begin()) {
    // この関数ですべてのYAMLファイル(Basic, Secret, Extend)を読み込む
    system_config.loadConfig(SPIFFS, "/SC_ExConfig.yaml", 2048,
                                     "/SC_SecConfig.yaml", 2048,
                                     "/SC_BasicConfig.yaml", 2048);
#else
  if (SD.begin(GPIO_NUM_4, SPI, 25000000)) {
    // この関数ですべてのYAMLファイル(Basic, Secret, Extend)を読み込む
    system_config.loadConfig(SD, "/app/AiStackChanEx/SC_ExConfig.yaml");
#endif
    // Wifi設定読み込み
    wifi_s* wifi_info = system_config.getWiFiSetting();
    Serial.printf("\nSSID: %s\n",wifi_info->ssid.c_str());
    Serial.printf("WiFi password loaded: %s
", wifi_info->password.length() ? "yes" : "no");

    // Wi-Fi接続：YAMLの設定だけを使用する。
    // スマホのテザリングは起動直後に見つかるまで時間がかかることがあるため、
    // 最大30秒待ち、失敗時は3回まで再試行する。
    Serial.println("Connecting to WiFi using YAML settings");

    if(wifi_info->ssid.length() == 0){
      Serial.println("ERROR: SSID is empty. Check /yaml/SC_SecConfig.yaml");
      M5.Lcd.println("WiFi YAML SSID is empty");
      isOffline = true;
    }else{
      Serial.printf("Target SSID: [%s]\n", wifi_info->ssid.c_str());
      Serial.printf("SSID length: %u\n", (unsigned)wifi_info->ssid.length());
      M5.Lcd.printf("WiFi: %s\n", wifi_info->ssid.c_str());

      // 以前保存されたアクセスポイント情報を消去し、
      // YAMLに書かれたSSID/パスワードで明示的に接続する。
      WiFi.disconnect(true, true);
      WiFi.softAPdisconnect(true);
      delay(1000);
      WiFi.mode(WIFI_STA);
      WiFi.setAutoReconnect(true);
      WiFi.setSleep(false);

      bool wifiConnected = false;
      for(int attempt = 1; attempt <= 3 && !wifiConnected; attempt++){
        Serial.printf("WiFi attempt %d/3\n", attempt);
        M5.Lcd.printf("Attempt %d/3 ", attempt);

        WiFi.begin(wifi_info->ssid.c_str(), wifi_info->password.c_str());
        wifiConnected = Wifi_connection_check(30000);

        if(!wifiConnected){
          Serial.printf(
            "Attempt %d failed. status=%d. Retrying...\n",
            attempt,
            (int)WiFi.status()
          );
          M5.Lcd.println(" failed");
          WiFi.disconnect(false, false);
          delay(2000);
        }
      }

      if(wifiConnected){
        Serial.println("Successfully connected using the YAML Wi-Fi settings.");
        M5.Lcd.println(" connected");
      }else{
        Serial.println("ERROR: Could not connect to YAML Wi-Fi after 3 attempts.");
        Serial.println("Check hotspot visibility, SSID, password and 2.4 GHz compatibility.");
        M5.Lcd.println("WiFi connection failed");
        isOffline = true;
      }
    }

    if(!isOffline){
      Serial.println(WiFi.localIP());
      M5.Lcd.println(WiFi.localIP());
      delay(1000);

      //Webサーバ設定
      init_web_server();
      //FTPサーバ設定（SPIFFS用）
      ftpSrv.begin("stackchan","stackchan");    //username, password for ftp.  set ports in ESP8266FtpServer.h  (default 21, 50009 for PASV)
      Serial.println("FTP server started");
      M5.Lcd.println("FTP server started");

      //時刻同期
      time_sync(NTPSRV, GMT_OFFSET, DAYLIGHT_OFFSET);

      //MQTT設定（表情リモート）
      mqttClient.setServer(MQTT_BROKER, MQTT_PORT);
      mqttClient.setCallback(mqttCallback);
      Serial.println("MQTT client configured");
    }else{
      M5.Lcd.print("Can't connect to WiFi. Start offline mode.\n");
    }

    robot = new Robot(system_config);

    //SD.end();
  } else {
    M5.Lcd.print("Failed to load SD card settings. System reset after 5 seconds.");
    delay(5000);
    ESP.restart();
    //WiFi.begin();
  }
  
  mp3_init();

  //mod設定
  init_mod();

#if defined(ARDUINO_M5STACK_ATOMS3R)
#if defined(CAT_FACE)
  customFace = new CatFace();
  avatar.setFace(customFace);
#endif
  avatar.setScale(0.5);
  avatar.setPosition(-56, -96);
  avatar.init();
#else
  //avatar.init();
  avatar.init(16);
#endif

  avatar.addTask(lipSync, "lipSync", 2048, 2);
  avatar.addTask(servo, "servo", 2048);
  avatar.addTask(battery_check, "battery_check", 2048);
  avatar.setSpeechFont(&fonts::efontJA_16);

  Serial.printf("Speaker volume (yaml): %d\n", system_config.getExConfig().audio.speaker_volume);
  if(0 != system_config.getExConfig().audio.speaker_volume){
    robot->spk_volume = system_config.getExConfig().audio.speaker_volume;
  }else{
    robot->spk_volume = DEFAULT_SPEAKER_VOLUME;
  }
  Serial.printf("Speaker volume (set): %d\n", robot->spk_volume);
  M5.Speaker.setVolume(robot->spk_volume);

#if defined(ENABLE_CAMERA)
  camera_init();
  avatar.set_isSubWindowEnable(true);
#endif

#if defined(ENABLE_TAP_DETECT)
  invokeDoubleTapDetectTask();
#endif

  //init_watchdog();

  //ヒープメモリ残量確認(デバッグ用)
  check_heap_free_size();
  check_heap_largest_free_block();

}



void loop()
{
  //get_elapsed_time_micro("loop() start");
  M5.update();
  //get_elapsed_time_micro("M5.update time");
  ModBase* mod = get_current_mod();
  mod->idle();
  //get_elapsed_time_micro("Mod idle time");

  if (M5.BtnA.wasPressed())
  {
    mod->btnA_pressed();
  }

  if (M5.BtnA.pressedFor(2000))
  {
    mod->btnA_longPressed();
  }

  if (M5.BtnB.wasPressed())
  {
    mod->btnB_pressed();
  }

  if (M5.BtnB.pressedFor(2000))
  {
    mod->btnB_longPressed();
  }

  if (M5.BtnC.wasPressed())
  {
    mod->btnC_pressed();
  }

#if defined(ARDUINO_M5STACK_Core2) || defined( ARDUINO_M5STACK_CORES3 )
  auto count = M5.Touch.getCount();
  if (count)
  {
    auto t = M5.Touch.getDetail();
    if (t.wasPressed())
    {
      mod->display_touched(t.x, t.y);
    }

    if (t.wasFlicked())
    {
      int16_t dx = t.distanceX();
      int16_t dy = t.distanceY();

      // detect flick right/left
      if(abs(dx) >= abs(dy))
      {
        if(dx > 0){
          //Serial.println("Right flicked");
          change_mod(true);
        }
        else{
          //Serial.println("Left flicked");
          change_mod();
        }
      }
    }
  }
#endif

#if defined(ENABLE_TAP_DETECT)
  if(doubleTapDetected){
    Serial.println("loop(): Double tap detected");
    mod->doubleTapped(detectedAcc[0], detectedAcc[1], detectedAcc[2]);
    doubleTapDetected = false;
  }

  // Modで重い処理をしている場合はダブルタップ検出を停止する
  if(mod->isBusy()){
    stopDoubleTapDetectTask();
  }else{
    resumeDoubleTapDetectTask();
  }
#endif
  //get_elapsed_time_micro("Callback process time");

  if(!isOffline){
    web_server_handle_client();
    ftpSrv.handleFTP();

    // MQTT：非阻塞维护连接。断开时每5秒重连一次，避免卡住loop
    static unsigned long lastMqttReconnect = 0;
    if (!mqttClient.connected()) {
      unsigned long now = millis();
      if (now - lastMqttReconnect > 5000) {
        lastMqttReconnect = now;
        mqttReconnect();
      }
    } else {
      mqttClient.loop();
    }
  }

  //get_elapsed_time_micro("Web event process time");
  
  //reset_watchdog();
}
