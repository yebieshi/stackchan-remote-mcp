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

// Tested v0.1 setup uses a direct HTTP photo relay.
// Replace the example IP and keep the token identical to the VPS environment file.
#define STACKCHAN_PHOTO_RELAY_URL "http://203.0.113.10:18090/upload"
#define STACKCHAN_PHOTO_RELAY_TOKEN "CHANGE_ME"
