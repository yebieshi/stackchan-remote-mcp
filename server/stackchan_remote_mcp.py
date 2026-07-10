#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""StackChan remote MCP server."""

from __future__ import annotations

import os
import time

import paho.mqtt.publish as publish
import requests
from mcp.server.fastmcp import FastMCP, Image


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

RELAY_URL = _env("STACKCHAN_RELAY_URL", "http://127.0.0.1:18090").rstrip("/")
RELAY_TOKEN = _env("STACKCHAN_RELAY_TOKEN", required=True)

MCP_HOST = _env("STACKCHAN_MCP_HOST", "0.0.0.0")
MCP_PORT = int(_env("STACKCHAN_MCP_PORT", "18003"))

mcp = FastMCP("stackchan", host=MCP_HOST, port=MCP_PORT)

_ALLOWED_EXPRESSIONS = {"neutral", "happy", "sleepy", "doubt", "sad", "angry"}


def _mqtt_pub(topic: str, payload: str) -> None:
    publish.single(
        topic,
        payload,
        hostname=MQTT_BROKER,
        port=MQTT_PORT,
        auth={"username": MQTT_USER, "password": MQTT_PASS},
    )


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
    headers = {"X-Relay-Token": RELAY_TOKEN}

    old_mtime = None
    try:
        previous = requests.get(
            f"{RELAY_URL}/latest.jpg",
            headers=headers,
            timeout=5,
        )
        if previous.status_code == 200:
            old_mtime = previous.headers.get("X-Photo-Mtime")
    except requests.RequestException:
        pass

    _mqtt_pub(MQTT_TOPIC_CAPTURE, "1")

    for _ in range(16):
        time.sleep(0.5)
        try:
            response = requests.get(
                f"{RELAY_URL}/latest.jpg",
                headers=headers,
                timeout=5,
            )
        except requests.RequestException:
            continue

        if response.status_code == 200:
            new_mtime = response.headers.get("X-Photo-Mtime")
            if new_mtime != old_mtime:
                return Image(data=response.content, format="jpeg")

    raise TimeoutError(
        "Timed out waiting for a new photo. "
        "Check StackChan Wi-Fi, MQTT, camera, and relay logs."
    )


@mcp.tool()
def stackchan_status() -> str:
    """Check the VPS photo relay. This does not prove that StackChan itself is online."""
    try:
        response = requests.get(f"{RELAY_URL}/health", timeout=5)
    except requests.RequestException as exc:
        return f"relay unreachable: {exc}"

    if response.status_code == 200:
        return "relay alive"
    return f"relay status {response.status_code}"


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
