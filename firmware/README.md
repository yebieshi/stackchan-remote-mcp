# Firmware overlay

This directory contains the modified `main.cpp` used for the tested remote-control setup.

## Apply it to AI_StackChan_Ex

1. Clone the upstream repository: `ronron-gh/AI_StackChan_Ex`.
2. Back up `firmware/src/main.cpp`.
3. Copy this repository's `firmware/main.cpp` to upstream `firmware/src/main.cpp`.
4. Copy `RemoteConfig.example.h` to upstream `firmware/src/RemoteConfig.h`.
5. Edit `RemoteConfig.h`.
6. Configure Wi-Fi in the SD card YAML as required by AI_StackChan_Ex.
7. Build and upload with PlatformIO.

`RemoteConfig.h` is ignored by Git and must never be committed.

## Tested behavior

- Uses the YAML Wi-Fi credentials instead of preferring an old saved network.
- Waits up to 30 seconds per Wi-Fi attempt and retries three times.
- Receives expression commands from `stackchan/face`.
- Receives capture commands from `stackchan/capture`.
- Uploads the captured JPEG to the VPS photo relay.
- Treats the configurable upper screen region as the tactile face surface.
- Responds locally on contact, then classifies tap, press, or stroke on release.
- Queues touch JSON to `stackchan/touch` and retries after MQTT reconnection.
- Receives model replies on `stackchan/reply` and displays them as speech text.

## Touch calibration

Copy all `STACKCHAN_TOUCH_*` values from `RemoteConfig.example.h` into the private
`RemoteConfig.h`. The default face zone leaves the bottom 48 pixels to the original
UI. Adjust the zone first, then tune stroke distance and press duration after
testing on the actual enclosure.
