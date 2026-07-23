#pragma once

// Copy this file to RemoteConfig.h, place it next to main.cpp,
// and replace every placeholder before building.

// Public IP address or hostname of the VPS running Mosquitto.
#define STACKCHAN_MQTT_BROKER "203.0.113.10"
#define STACKCHAN_MQTT_PORT 1883
#define STACKCHAN_MQTT_USER "stackchan"
#define STACKCHAN_MQTT_PASS "CHANGE_ME"
#define STACKCHAN_MQTT_CLIENT_ID "stackchan-01"

#define STACKCHAN_MQTT_TOPIC_FACE "stackchan/face"
#define STACKCHAN_MQTT_TOPIC_CAPTURE "stackchan/capture"
#define STACKCHAN_MQTT_TOPIC_TOUCH "stackchan/touch"
#define STACKCHAN_MQTT_TOPIC_REPLY "stackchan/reply"

// The default bridge zone covers the face while leaving the bottom control
// strip available to the original firmware UI. Coordinates are for 320x240.
#define STACKCHAN_TOUCH_ZONE_X_MIN 0
#define STACKCHAN_TOUCH_ZONE_X_MAX 319
#define STACKCHAN_TOUCH_ZONE_Y_MIN 0
#define STACKCHAN_TOUCH_ZONE_Y_MAX 191

// A movement of at least 24 pixels is a stroke. A mostly stationary touch held
// for at least 800 ms is a press. Shorter stationary contact is a tap.
#define STACKCHAN_TOUCH_STROKE_DISTANCE_PX 24
#define STACKCHAN_TOUCH_PRESS_MS 800

// Tested v0.1 setup uses a direct HTTP photo relay.
// Replace the example IP and keep the token identical to the VPS environment file.
#define STACKCHAN_PHOTO_RELAY_URL "http://203.0.113.10:18090/upload"
#define STACKCHAN_PHOTO_RELAY_TOKEN "CHANGE_ME"
