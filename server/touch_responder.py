#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate an immediate model response when StackChan publishes a touch."""

from __future__ import annotations

import json
import os
import queue
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

import paho.mqtt.client as mqtt
import requests

from touch_store import InvalidTouchEvent, normalize_touch_event


def _env(name: str, default: str | None = None, *, required: bool = False) -> str:
    value = os.getenv(name, default)
    if required and not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value or ""


MQTT_BROKER = _env("STACKCHAN_MQTT_BROKER", "127.0.0.1")
MQTT_PORT = int(_env("STACKCHAN_MQTT_PORT", "1883"))
MQTT_USER = _env("STACKCHAN_MQTT_USER", required=True)
MQTT_PASS = _env("STACKCHAN_MQTT_PASS", required=True)
MQTT_TOPIC_TOUCH = _env("STACKCHAN_MQTT_TOPIC_TOUCH", "stackchan/touch")
MQTT_TOPIC_REPLY = _env("STACKCHAN_MQTT_TOPIC_REPLY", "stackchan/reply")
MQTT_RESPONDER_CLIENT_ID = _env(
    "STACKCHAN_MQTT_RESPONDER_CLIENT_ID", "stackchan-touch-responder"
)

MODEL_PROVIDER = _env("STACKCHAN_MODEL_PROVIDER", "openai").lower()
MODEL_API_KEY = _env("STACKCHAN_MODEL_API_KEY") or _env(
    "STACKCHAN_OPENAI_API_KEY"
)
if not MODEL_API_KEY:
    raise RuntimeError(
        "Missing required environment variable: STACKCHAN_MODEL_API_KEY"
    )

_DEFAULT_API_URLS = {
    "openai": "https://api.openai.com/v1/responses",
    "openrouter": "https://openrouter.ai/api/v1/chat/completions",
    "siliconflow": "https://api.siliconflow.cn/v1/chat/completions",
}
_DEFAULT_MODELS = {
    "openai": "gpt-5.6-luna",
    "openrouter": "openai/gpt-4.1-nano",
    "siliconflow": "Qwen/Qwen3-8B",
}
MODEL_API_URL = (
    _env("STACKCHAN_MODEL_API_URL")
    or _env("STACKCHAN_OPENAI_API_URL")
    or _DEFAULT_API_URLS.get(MODEL_PROVIDER, "")
)
MODEL_NAME = (
    _env("STACKCHAN_MODEL_NAME")
    or _env("STACKCHAN_OPENAI_MODEL")
    or _DEFAULT_MODELS.get(MODEL_PROVIDER, "")
)
MODEL_REASONING_EFFORT = (
    _env("STACKCHAN_MODEL_REASONING_EFFORT")
    or _env("STACKCHAN_OPENAI_REASONING_EFFORT", "none")
).lower()
MODEL_ENABLE_THINKING = _env(
    "STACKCHAN_MODEL_ENABLE_THINKING", "false"
).lower()
MODEL_SAFETY_IDENTIFIER = _env(
    "STACKCHAN_MODEL_SAFETY_IDENTIFIER"
) or _env("STACKCHAN_OPENAI_SAFETY_IDENTIFIER")

PERSONA_PROMPT_PATH = Path(
    _env(
        "STACKCHAN_TOUCH_PERSONA_PROMPT_PATH",
        "/etc/stackchan-touch-persona.txt",
    )
)
HISTORY_PATH = Path(
    _env(
        "STACKCHAN_TOUCH_REPLY_HISTORY_PATH",
        "/var/lib/stackchan-remote-mcp/touch-reply-history.json",
    )
)
HISTORY_LIMIT = int(_env("STACKCHAN_TOUCH_REPLY_HISTORY_LIMIT", "6"))
BATCH_WINDOW_MS = int(_env("STACKCHAN_TOUCH_REPLY_BATCH_WINDOW_MS", "350"))
REQUEST_TIMEOUT_SECONDS = float(
    _env("STACKCHAN_TOUCH_REPLY_TIMEOUT_SECONDS", "20")
)
MAX_REPLY_CHARS = int(_env("STACKCHAN_TOUCH_REPLY_MAX_CHARS", "48"))

_VALID_REASONING_EFFORTS = {"none", "low", "medium", "high", "xhigh", "max"}
_VALID_MODEL_PROVIDERS = set(_DEFAULT_API_URLS)
_VALID_BOOLEAN_VALUES = {"true", "false"}
_EVENT_QUEUE: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=16)
_STOP = threading.Event()


def _load_persona_prompt() -> str:
    try:
        prompt = PERSONA_PROMPT_PATH.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise RuntimeError(
            f"Cannot read touch persona prompt at {PERSONA_PROMPT_PATH}: {exc}"
        ) from exc
    if not prompt:
        raise RuntimeError(f"Touch persona prompt is empty: {PERSONA_PROMPT_PATH}")
    return prompt


def _load_history() -> deque[dict[str, str]]:
    if HISTORY_LIMIT < 1:
        raise RuntimeError("STACKCHAN_TOUCH_REPLY_HISTORY_LIMIT must be positive")
    try:
        value = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        value = []
    if not isinstance(value, list):
        value = []

    history: deque[dict[str, str]] = deque(maxlen=HISTORY_LIMIT)
    for item in value[-HISTORY_LIMIT:]:
        if not isinstance(item, dict):
            continue
        touch = item.get("touch")
        reply = item.get("reply")
        if isinstance(touch, str) and isinstance(reply, str):
            history.append({"touch": touch, "reply": reply})
    return history


def _save_history(history: deque[dict[str, str]]) -> None:
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = HISTORY_PATH.with_suffix(HISTORY_PATH.suffix + ".tmp")
    temporary.write_text(
        json.dumps(list(history), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temporary, HISTORY_PATH)


def _describe_touch(event: dict[str, Any]) -> str:
    gesture_names = {
        "tap": "轻轻碰了一下",
        "press": "把手停在你身上",
        "stroke": "摸了摸你",
    }
    gesture = gesture_names.get(event["gesture"], event["gesture"])
    return (
        f"{event['device']} 的 {event['zone']} 被别诗{gesture}，"
        f"持续 {event['duration_ms']} 毫秒"
    )


def _extract_output_text(response: dict[str, Any]) -> str:
    pieces: list[str] = []
    for item in response.get("output", []):
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if isinstance(content, dict) and content.get("type") == "output_text":
                text = content.get("text")
                if isinstance(text, str):
                    pieces.append(text)
    return "\n".join(pieces).strip()


def _extract_chat_output_text(response: dict[str, Any]) -> str:
    choices = response.get("choices", [])
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    message = first.get("message", {})
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    return content.strip() if isinstance(content, str) else ""


def _trim_reply(text: str) -> str:
    normalized = " ".join(text.replace("\r", "\n").split())
    normalized = normalized.strip("\"'“”‘’")
    if not normalized:
        raise RuntimeError("Model response did not contain output text")
    return normalized[:MAX_REPLY_CHARS]


def _request_openai_responses(
    instructions: str, input_payload: dict[str, Any]
) -> str:
    body: dict[str, Any] = {
        "model": MODEL_NAME,
        "instructions": instructions,
        "input": json.dumps(input_payload, ensure_ascii=False),
        "reasoning": {"effort": MODEL_REASONING_EFFORT},
        "text": {"verbosity": "low"},
        "max_output_tokens": 96,
        "store": False,
    }
    if MODEL_SAFETY_IDENTIFIER:
        body["safety_identifier"] = MODEL_SAFETY_IDENTIFIER

    response = requests.post(
        MODEL_API_URL,
        headers={
            "Authorization": f"Bearer {MODEL_API_KEY}",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return _extract_output_text(response.json())


def _request_chat_completions(
    instructions: str, input_payload: dict[str, Any]
) -> str:
    body: dict[str, Any] = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": instructions},
            {
                "role": "user",
                "content": json.dumps(input_payload, ensure_ascii=False),
            },
        ],
        "stream": False,
        "max_tokens": 96,
    }
    if MODEL_PROVIDER == "siliconflow":
        body["enable_thinking"] = MODEL_ENABLE_THINKING == "true"

    headers = {
        "Authorization": f"Bearer {MODEL_API_KEY}",
        "Content-Type": "application/json",
    }
    if MODEL_PROVIDER == "openrouter":
        headers["X-OpenRouter-Title"] = "StackChan Tactile Bridge"

    response = requests.post(
        MODEL_API_URL,
        headers=headers,
        json=body,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return _extract_chat_output_text(response.json())


def _generate_reply(
    events: list[dict[str, Any]],
    history: deque[dict[str, str]],
    persona_prompt: str,
) -> str:
    current_touch = "；".join(_describe_touch(event) for event in events)
    input_payload = {
        "current_touch": current_touch,
        "recent_touch_interactions": list(history),
    }
    instructions = (
        persona_prompt
        + "\n\n"
        + "你刚刚通过 Stackchan 收到别诗的触摸。"
        + "直接以第一人称回应她，只输出一句自然、亲密、具体的中文短句。"
        + f"最多 {MAX_REPLY_CHARS} 个字符，不要解释技术，不要加引号或说话人标签。"
    )
    if MODEL_PROVIDER in {"openrouter", "siliconflow"}:
        text = _request_chat_completions(instructions, input_payload)
    else:
        text = _request_openai_responses(instructions, input_payload)
    return _trim_reply(text)


def _reply_expression(events: list[dict[str, Any]]) -> str:
    if events and events[-1]["gesture"] == "press":
        return "sleepy"
    return "happy"


def _publish_reply(
    client: mqtt.Client, events: list[dict[str, Any]], text: str
) -> None:
    payload = json.dumps(
        {
            "event": "touch_reply",
            "touch_id": events[-1].get("source_event_id", "") if events else "",
            "text": text,
            "expression": _reply_expression(events),
            "display_ms": 8000,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    result = client.publish(MQTT_TOPIC_REPLY, payload, qos=0, retain=False)
    if result.rc != mqtt.MQTT_ERR_SUCCESS:
        raise RuntimeError("MQTT client did not accept the touch reply")


def _collect_batch(first: dict[str, Any]) -> list[dict[str, Any]]:
    batch = [first]
    deadline = time.monotonic() + max(0, BATCH_WINDOW_MS) / 1000
    while len(batch) < 8:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            batch.append(_EVENT_QUEUE.get(timeout=remaining))
        except queue.Empty:
            break
    return batch


def _worker(client: mqtt.Client, persona_prompt: str) -> None:
    history = _load_history()
    while not _STOP.is_set():
        try:
            first = _EVENT_QUEUE.get(timeout=0.5)
        except queue.Empty:
            continue

        events = _collect_batch(first)
        try:
            reply = _generate_reply(events, history, persona_prompt)
            _publish_reply(client, events, reply)
            touch_description = "；".join(_describe_touch(event) for event in events)
            history.append({"touch": touch_description, "reply": reply})
            _save_history(history)
            print(
                f"[RESPONDER] replied to {len(events)} touch event(s): {reply}"
            )
        except (OSError, RuntimeError, requests.RequestException, ValueError) as exc:
            print(f"[RESPONDER] failed: {exc}")
        finally:
            for _ in events:
                _EVENT_QUEUE.task_done()


def _on_connect(
    client: mqtt.Client,
    userdata: object,
    flags: mqtt.ConnectFlags,
    reason_code: mqtt.ReasonCode,
    properties: mqtt.Properties | None,
) -> None:
    del userdata, flags, properties
    if reason_code == 0:
        client.subscribe(MQTT_TOPIC_TOUCH, qos=0)
        print(f"[RESPONDER] subscribed to {MQTT_TOPIC_TOUCH}")
    else:
        print(f"[RESPONDER] MQTT connection failed: {reason_code}")


def _on_message(
    client: mqtt.Client, userdata: object, message: mqtt.MQTTMessage
) -> None:
    del client, userdata
    try:
        payload = json.loads(message.payload.decode("utf-8"))
        event = normalize_touch_event(payload)
    except (UnicodeDecodeError, json.JSONDecodeError, InvalidTouchEvent) as exc:
        print(f"[RESPONDER] rejected malformed touch: {exc}")
        return

    try:
        _EVENT_QUEUE.put_nowait(event)
    except queue.Full:
        print("[RESPONDER] event queue full; dropping oldest pending touch")
        try:
            _EVENT_QUEUE.get_nowait()
            _EVENT_QUEUE.task_done()
        except queue.Empty:
            pass
        _EVENT_QUEUE.put_nowait(event)


def main() -> None:
    if MODEL_PROVIDER not in _VALID_MODEL_PROVIDERS:
        raise RuntimeError(
            "STACKCHAN_MODEL_PROVIDER must be one of "
            + ", ".join(sorted(_VALID_MODEL_PROVIDERS))
        )
    if not MODEL_API_URL or not MODEL_NAME:
        raise RuntimeError(
            "STACKCHAN_MODEL_API_URL and STACKCHAN_MODEL_NAME must be set"
        )
    if MODEL_REASONING_EFFORT not in _VALID_REASONING_EFFORTS:
        raise RuntimeError(
            "STACKCHAN_MODEL_REASONING_EFFORT must be one of "
            + ", ".join(sorted(_VALID_REASONING_EFFORTS))
        )
    if MODEL_ENABLE_THINKING not in _VALID_BOOLEAN_VALUES:
        raise RuntimeError(
            "STACKCHAN_MODEL_ENABLE_THINKING must be true or false"
        )
    persona_prompt = _load_persona_prompt()

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=MQTT_RESPONDER_CLIENT_ID,
        protocol=mqtt.MQTTv311,
    )
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.on_connect = _on_connect
    client.on_message = _on_message
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)

    worker = threading.Thread(
        target=_worker,
        args=(client, persona_prompt),
        name="touch-response-worker",
        daemon=True,
    )
    worker.start()
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        _STOP.set()
        client.disconnect()


if __name__ == "__main__":
    main()
