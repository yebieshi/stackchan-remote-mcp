from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1] / "server"
sys.path.insert(0, str(SERVER_DIR))

from touch_store import InvalidTouchEvent, TouchEventStore  # noqa: E402


def touch_event(source_event_id: str = "boot-1") -> dict[str, object]:
    return {
        "event": "touch",
        "device": "stackchan-01",
        "zone": "head_front",
        "gesture": "stroke",
        "duration_ms": 1200,
        "x_start": 100,
        "y_start": 80,
        "x_end": 160,
        "y_end": 85,
        "timestamp": "2026-07-23T07:00:00Z",
        "source_event_id": source_event_id,
    }


class TouchEventStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "touch-events.jsonl"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_persists_and_restores_unread_events(self) -> None:
        store = TouchEventStore(self.path)
        first = store.add_event(touch_event("boot-1"))
        second = store.add_payload(json.dumps(touch_event("boot-2")))

        self.assertEqual(first["id"], 1)
        self.assertEqual(second["id"], 2)
        self.assertEqual(store.unread_count, 2)

        store.acknowledge(first["id"])
        restored = TouchEventStore(self.path)
        self.assertEqual(restored.acknowledged_id, 1)
        self.assertEqual(
            [event["source_event_id"] for event in restored.list_events()],
            ["boot-2"],
        )

    def test_deduplicates_retried_device_event(self) -> None:
        store = TouchEventStore(self.path)
        first = store.add_event(touch_event("same-id"))
        duplicate = store.add_event(touch_event("same-id"))

        self.assertEqual(duplicate["id"], first["id"])
        self.assertEqual(store.unread_count, 1)
        self.assertEqual(len(self.path.read_text(encoding="utf-8").splitlines()), 1)

    def test_rejects_invalid_payload(self) -> None:
        store = TouchEventStore(self.path)
        invalid = touch_event()
        invalid["gesture"] = "surprise"

        with self.assertRaises(InvalidTouchEvent):
            store.add_event(invalid)
        with self.assertRaises(InvalidTouchEvent):
            store.add_payload(b"not-json")

    def test_prunes_old_events(self) -> None:
        store = TouchEventStore(self.path, max_events=2)
        store.add_event(touch_event("one"))
        store.add_event(touch_event("two"))
        store.add_event(touch_event("three"))

        self.assertEqual(
            [event["source_event_id"] for event in store.list_events(unread_only=False)],
            ["two", "three"],
        )
        self.assertEqual(len(self.path.read_text(encoding="utf-8").splitlines()), 2)


if __name__ == "__main__":
    unittest.main()
