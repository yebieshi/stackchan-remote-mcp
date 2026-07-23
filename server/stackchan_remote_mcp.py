#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""StackChan remote MCP server."""

from __future__ import annotations

import hashlib
import json
import os
import time

import paho.mqtt.client as mqtt
import paho.mqtt.publish as publish
import requests
from mcp.server.fastmcp import FastMCP, Image

from touch_store import InvalidTouchEvent, TouchEventStore


def _env(name: str, default: str | None = None, *, required: bool = False) -> str:
    value = os.getenv(name, default)
    if required and not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value or ""


MQTT_BROKER = _env("STACKCHAN_MQTT_BROKER", "127.0.0.1")
MQTT_PORT = int(_env("STACKCHAN_MQTT_PORT", "1883"))
MQTT_USER = _env("STACKCHAN_MQTT_USER", required=True)
MQTT_PASS = _env("STACKCHAN_MQTT_PASS", required=True)
MQTT_TOPIC_FACE = _env("STACKCHAN_MQTT_TOPIC_FACE", "stackchan/face")
MQTT_TOPIC_CAPTURE = _env("STACKCHAN_MQTT_TOPIC_CAPTURE", "stackchan/capture")
MQTT_TOPIC_TOUCH = _env("STACKCHAN_MQTT_TOPIC_TOUCH", "stackchan/touch")
MQTT_TOUCH_CLIENT_ID = _env(
    "STACKCHAN_MQTT_TOUCH_CLIENT_ID", "stackchan-mcp-touch-listener"
)

RELAY_URL = _env("STACKCHAN_RELAY_URL", "http://127.0.0.1:18090").rstrip("/")
RELAY_TOKEN = _env("STACKCHAN_RELAY_TOKEN", required=True)

MCP_HOST = _env("STACKCHAN_MCP_HOST", "0.0.0.0")
MCP_PORT = int(_env("STACKCHAN_MCP_PORT", "18003"))

TOUCH_EVENT_PATH = _env(
    "STACKCHAN_TOUCH_EVENT_PATH",
    "/var/lib/stackchan-remote-mcp/touch-events.jsonl",
)
TOUCH_MAX_EVENTS = int(_env("STACKCHAN_TOUCH_MAX_EVENTS", "1000"))

mcp = FastMCP("stackchan", host=MCP_HOST, port=MCP_PORT)
touch_store = TouchEventStore(TOUCH_EVENT_PATH, max_events=TOUCH_MAX_EVENTS)

_ALLOWED_EXPRESSIONS = {"neutral", "happy", "sleepy", "doubt", "sad", "angry"}
_touch_listener: mqtt.Client | None = None
_touch_listener_connected = False


def _mqtt_pub(topic: str, payload: str) -> None:
    publish.single(
        topic,
        payload,
        hostname=MQTT_BROKER,
        port=MQTT_PORT,
        auth={"username": MQTT_USER, "password": MQTT_PASS},
    )


def _get_latest_photo() -> requests.Response:
    return requests.get(
        f"{RELAY_URL}/latest.jpg",
        headers={
            "X-Relay-Token": RELAY_TOKEN,
            "Cache-Control": "no-cache",
        },
        params={"_": time.time_ns()},
        timeout=5,
    )


def _on_touch_connect(
    client: mqtt.Client,
    userdata: object,
    flags: mqtt.ConnectFlags,
    reason_code: mqtt.ReasonCode,
    properties: mqtt.Properties | None,
) -> None:
    del userdata, flags, properties
    global _touch_listener_connected
    if reason_code == 0:
        client.subscribe(MQTT_TOPIC_TOUCH, qos=0)
        _touch_listener_connected = True
        print(f"[TOUCH] subscribed to {MQTT_TOPIC_TOUCH}")
    else:
        _touch_listener_connected = False
        print(f"[TOUCH] MQTT connection failed: {reason_code}")


def _on_touch_disconnect(
    client: mqtt.Client,
    userdata: object,
    disconnect_flags: mqtt.DisconnectFlags,
    reason_code: mqtt.ReasonCode,
    properties: mqtt.Properties | None,
) -> None:
    del client, userdata, disconnect_flags, properties
    global _touch_listener_connected
    _touch_listener_connected = False
    print(f"[TOUCH] MQTT disconnected: {reason_code}")


def _on_touch_message(
    client: mqtt.Client, userdata: object, message: mqtt.MQTTMessage
) -> None:
    del client, userdata
    try:
        event = touch_store.add_payload(message.payload)
    except InvalidTouchEvent as exc:
        print(f"[TOUCH] rejected malformed event: {exc}")
        return
    except OSError as exc:
        print(f"[TOUCH] could not persist event: {exc}")
        return

    print(
        f"[TOUCH] stored id={event['id']} device={event['device']} "
        f"zone={event['zone']} gesture={event['gesture']}"
    )


def _start_touch_listener() -> mqtt.Client:
    global _touch_listener
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=MQTT_TOUCH_CLIENT_ID,
        protocol=mqtt.MQTTv311,
    )
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.on_connect = _on_touch_connect
    client.on_disconnect = _on_touch_disconnect
    client.on_message = _on_touch_message
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    client.connect_async(MQTT_BROKER, MQTT_PORT, keepalive=60)
    client.loop_start()
    _touch_listener = client
    return client


@mcp.tool()
def stackchan_face(expression: str) -> str:
    """Change StackChan's expression: neutral, happy, sleepy, doubt, sad, or angry."""
    normalized = expression.strip().lower()
    if normalized not in _ALLOWED_EXPRESSIONS:
        allowed = ", ".join(sorted(_ALLOWED_EXPRESSIONS))
        raise ValueError(f"Unsupported expression: {expression!r}. Allowed: {allowed}")
    _mqtt_pub(MQTT_TOPIC_FACE, normalized)
    return f"StackChan expression changed to {normalized}."


@mcp.tool()
def stackchan_see() -> Image:
    """Trigger a photo capture and return the newest JPEG image."""
    old_version = None
    old_hash = None

    try:
        previous = _get_latest_photo()
        if previous.status_code == 200:
            old_version = previous.headers.get("X-Photo-Version")
            old_hash = hashlib.sha256(previous.content).digest()
    except requests.RequestException:
        pass

    _mqtt_pub(MQTT_TOPIC_CAPTURE, "1")

    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        time.sleep(0.25)
        try:
            response = _get_latest_photo()
        except requests.RequestException:
            continue

        if response.status_code != 200:
            continue

        new_version = response.headers.get("X-Photo-Version")
        new_hash = hashlib.sha256(response.content).digest()

        version_changed = (
            new_version is not None
            and new_version != old_version
        )
        content_changed = (
            old_hash is not None
            and new_hash != old_hash
        )
        first_photo_arrived = old_hash is None and bool(response.content)

        if version_changed or content_changed or first_photo_arrived:
            return Image(data=response.content, format="jpeg")

    raise TimeoutError(
        "Timed out waiting for a new photo. "
        "Check StackChan Wi-Fi, MQTT, camera, relay logs, and relay version headers."
    )


@mcp.tool()
def stackchan_recent_touches(
    limit: int = 10,
    unread_only: bool = True,
) -> str:
    """Read the user's pending physical touches from StackChan.

    Call this tool only when the user says "摸摸" as an actual trigger. Do not
    call it at the start of every conversational turn, or when the trigger word
    is merely quoted or discussed. Use the default unread-only, non-marking read.
    Treat returned events as physical contact from the user, incorporate them
    naturally, then acknowledge the last returned id with stackchan_ack_touch.
    If no events are returned, continue silently.
    """
    events = touch_store.list_events(limit=limit, unread_only=unread_only)
    unread_before = touch_store.unread_count
    acknowledged_id = touch_store.acknowledged_id

    return json.dumps(
        {
            "events": events,
            "returned": len(events),
            "unread_before": unread_before,
            "unread_after": unread_before,
            "acknowledged_id": acknowledged_id,
        },
        ensure_ascii=False,
    )


@mcp.tool()
def stackchan_ack_touch(up_to_event_id: int) -> str:
    """Mark touches through this event id read after incorporating them."""
    acknowledged_id = touch_store.acknowledge(up_to_event_id)
    return json.dumps(
        {
            "acknowledged_id": acknowledged_id,
            "unread": touch_store.unread_count,
        }
    )


@mcp.tool()
def stackchan_status() -> str:
    """Check the photo relay and the touch bridge listener on the VPS."""
    try:
        response = requests.get(f"{RELAY_URL}/health", timeout=5)
    except requests.RequestException as exc:
        return f"relay unreachable: {exc}"

    if response.status_code == 200:
        listener = "connected" if _touch_listener_connected else "connecting"
        return (
            f"relay alive; touch listener {listener}; "
            f"unread touches={touch_store.unread_count}"
        )
    return f"relay status {response.status_code}"


if __name__ == "__main__":
    _start_touch_listener()
    mcp.run(transport="streamable-http")
