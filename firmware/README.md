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
