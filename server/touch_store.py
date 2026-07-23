#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Persistent, thread-safe storage for StackChan touch events."""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class InvalidTouchEvent(ValueError):
    """Raised when a device publishes a malformed touch event."""


_ALLOWED_GESTURES = {"tap", "press", "stroke"}
_ALLOWED_DIRECTIONS = {"forward", "backward"}
_MAX_TEXT_LENGTH = 96


def _bounded_text(value: Any, field: str, *, required: bool = True) -> str:
    if value is None and not required:
        return ""
    if not isinstance(value, str):
        raise InvalidTouchEvent(f"{field} must be a string")
    normalized = value.strip()
    if required and not normalized:
        raise InvalidTouchEvent(f"{field} must not be empty")
    if len(normalized) > _MAX_TEXT_LENGTH:
        raise InvalidTouchEvent(f"{field} is too long")
    return normalized


def normalize_touch_event(value: Any) -> dict[str, Any]:
    """Validate an untrusted MQTT payload and return its canonical fields."""
    if not isinstance(value, dict):
        raise InvalidTouchEvent("touch payload must be a JSON object")
    if value.get("event") != "touch":
        raise InvalidTouchEvent("event must be 'touch'")

    gesture = _bounded_text(value.get("gesture"), "gesture").lower()
    if gesture not in _ALLOWED_GESTURES:
        allowed = ", ".join(sorted(_ALLOWED_GESTURES))
        raise InvalidTouchEvent(f"unsupported gesture {gesture!r}; allowed: {allowed}")

    duration = value.get("duration_ms")
    if isinstance(duration, bool) or not isinstance(duration, int):
        raise InvalidTouchEvent("duration_ms must be an integer")
    if not 0 <= duration <= 60_000:
        raise InvalidTouchEvent("duration_ms must be between 0 and 60000")

    normalized: dict[str, Any] = {
        "event": "touch",
        "device": _bounded_text(value.get("device"), "device"),
        "zone": _bounded_text(value.get("zone"), "zone"),
        "gesture": gesture,
        "duration_ms": duration,
    }

    direction = _bounded_text(value.get("direction"), "direction", required=False).lower()
    if direction:
        if gesture != "stroke":
            raise InvalidTouchEvent("direction is only valid for stroke gestures")
        if direction not in _ALLOWED_DIRECTIONS:
            allowed = ", ".join(sorted(_ALLOWED_DIRECTIONS))
            raise InvalidTouchEvent(
                f"unsupported direction {direction!r}; allowed: {allowed}"
            )
        normalized["direction"] = direction

    for field in ("x_start", "y_start", "x_end", "y_end"):
        coordinate = value.get(field)
        if coordinate is None:
            continue
        if isinstance(coordinate, bool) or not isinstance(coordinate, int):
            raise InvalidTouchEvent(f"{field} must be an integer")
        if not -4096 <= coordinate <= 4096:
            raise InvalidTouchEvent(f"{field} is outside the accepted range")
        normalized[field] = coordinate

    for field in ("timestamp", "source_event_id"):
        text = _bounded_text(value.get(field), field, required=False)
        if text:
            normalized[field] = text

    return normalized


class TouchEventStore:
    """Append touch events to JSONL and track a durable acknowledgement cursor."""

    def __init__(self, path: str | Path, *, max_events: int = 1000) -> None:
        if max_events < 1:
            raise ValueError("max_events must be positive")

        self.path = Path(path)
        self.ack_path = self.path.with_suffix(self.path.suffix + ".ack")
        self.max_events = max_events
        self._lock = threading.RLock()
        self._events: list[dict[str, Any]] = []
        self._acknowledged_id = 0
        self._next_id = 1

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._load()

    def _load(self) -> None:
        with self._lock:
            if self.path.exists():
                for line in self.path.read_text(encoding="utf-8").splitlines():
                    try:
                        event = json.loads(line)
                    except (json.JSONDecodeError, TypeError):
                        continue
                    if not isinstance(event, dict) or not isinstance(event.get("id"), int):
                        continue
                    self._events.append(event)

            self._events.sort(key=lambda item: item["id"])
            self._events = self._events[-self.max_events :]
            if self._events:
                self._next_id = self._events[-1]["id"] + 1

            if self.ack_path.exists():
                try:
                    self._acknowledged_id = max(
                        0, int(self.ack_path.read_text(encoding="utf-8").strip())
                    )
                except ValueError:
                    self._acknowledged_id = 0

    def _rewrite_events(self) -> None:
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        content = "".join(
            json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
            for event in self._events
        )
        temporary.write_text(content, encoding="utf-8")
        os.replace(temporary, self.path)

    def _write_acknowledgement(self) -> None:
        temporary = self.ack_path.with_suffix(self.ack_path.suffix + ".tmp")
        temporary.write_text(str(self._acknowledged_id), encoding="utf-8")
        os.replace(temporary, self.ack_path)

    def add_payload(self, payload: bytes | str) -> dict[str, Any]:
        try:
            decoded = payload.decode("utf-8") if isinstance(payload, bytes) else payload
            value = json.loads(decoded)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise InvalidTouchEvent(f"invalid touch JSON: {exc}") from exc
        return self.add_event(value)

    def add_event(self, value: Any) -> dict[str, Any]:
        normalized = normalize_touch_event(value)
        with self._lock:
            source_event_id = normalized.get("source_event_id")
            if source_event_id:
                for existing in reversed(self._events):
                    if existing.get("source_event_id") == source_event_id:
                        return dict(existing)

            stored = {
                "id": self._next_id,
                **normalized,
                "received_at": datetime.now(timezone.utc)
                .isoformat(timespec="milliseconds")
                .replace("+00:00", "Z"),
            }
            self._next_id += 1
            self._events.append(stored)

            with self.path.open("a", encoding="utf-8") as output:
                output.write(
                    json.dumps(stored, ensure_ascii=False, separators=(",", ":")) + "\n"
                )

            if len(self._events) > self.max_events:
                self._events = self._events[-self.max_events :]
                self._rewrite_events()

            return dict(stored)

    def list_events(
        self, *, limit: int = 10, unread_only: bool = True
    ) -> list[dict[str, Any]]:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        with self._lock:
            events = self._events
            if unread_only:
                events = [
                    event for event in events if event["id"] > self._acknowledged_id
                ]
                # Return the oldest unread items first. Acknowledging the final
                # returned id must never skip older unread events.
                events = events[:limit]
            else:
                events = events[-limit:]
            return [dict(event) for event in events]

    def acknowledge(self, up_to_event_id: int) -> int:
        if isinstance(up_to_event_id, bool) or not isinstance(up_to_event_id, int):
            raise ValueError("up_to_event_id must be an integer")
        if up_to_event_id < 0:
            raise ValueError("up_to_event_id must not be negative")

        with self._lock:
            highest_known = self._events[-1]["id"] if self._events else 0
            if up_to_event_id > highest_known:
                raise ValueError(
                    f"event {up_to_event_id} does not exist; highest known id is {highest_known}"
                )
            self._acknowledged_id = max(self._acknowledged_id, up_to_event_id)
            self._write_acknowledgement()
            return self._acknowledged_id

    @property
    def unread_count(self) -> int:
        with self._lock:
            return sum(
                event["id"] > self._acknowledged_id for event in self._events
            )

    @property
    def acknowledged_id(self) -> int:
        with self._lock:
            return self._acknowledged_id
