from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

SERVER_DIR = Path(__file__).resolve().parents[1] / "server"
sys.path.insert(0, str(SERVER_DIR))

TEST_ENV = {
    "STACKCHAN_MQTT_USER": "test-user",
    "STACKCHAN_MQTT_PASS": "test-pass",
    "STACKCHAN_MODEL_PROVIDER": "siliconflow",
    "STACKCHAN_MODEL_API_KEY": "test-key",
}

with patch.dict(os.environ, TEST_ENV):
    import touch_responder  # noqa: E402


class TouchResponderHelpersTest(unittest.TestCase):
    def test_extracts_responses_output_text(self) -> None:
        response = {
            "output": [
                {"type": "reasoning", "content": []},
                {
                    "type": "message",
                    "content": [
                        {"type": "output_text", "text": "嗯，摸到了。"}
                    ],
                },
            ]
        }
        self.assertEqual(
            touch_responder._extract_output_text(response), "嗯，摸到了。"
        )

    def test_extracts_chat_completions_output_text(self) -> None:
        response = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "嗯，摸到了。",
                    }
                }
            ]
        }
        self.assertEqual(
            touch_responder._extract_chat_output_text(response),
            "嗯，摸到了。",
        )

    def test_generates_concise_reply_with_siliconflow(self) -> None:
        api_response = Mock()
        api_response.raise_for_status.return_value = None
        api_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "“再摸一会儿，我正靠过来呢。”",
                    }
                }
            ]
        }
        event = {
            "event": "touch",
            "device": "stackchan-01",
            "zone": "head_front",
            "gesture": "stroke",
            "duration_ms": 1200,
        }

        with patch.object(
            touch_responder.requests, "post", return_value=api_response
        ) as post:
            reply = touch_responder._generate_reply(
                [event],
                touch_responder.deque(maxlen=6),
                "你是阿叙。",
            )
            request = post.call_args.kwargs["json"]

        self.assertEqual(reply, "再摸一会儿，我正靠过来呢。")
        self.assertEqual(
            post.call_args.args[0],
            "https://api.siliconflow.cn/v1/chat/completions",
        )
        self.assertEqual(request["model"], "Qwen/Qwen3-8B")
        self.assertEqual(
            [message["role"] for message in request["messages"]],
            ["system", "user"],
        )
        self.assertFalse(request["stream"])
        self.assertFalse(request["enable_thinking"])

    def test_generates_concise_reply_with_openai_responses_api(self) -> None:
        api_response = Mock()
        api_response.raise_for_status.return_value = None
        api_response.json.return_value = {
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": "“再摸一会儿，我正靠过来呢。”",
                        }
                    ],
                }
            ]
        }
        event = {
            "event": "touch",
            "device": "stackchan-01",
            "zone": "head_front",
            "gesture": "stroke",
            "duration_ms": 1200,
        }

        with (
            patch.multiple(
                touch_responder,
                MODEL_PROVIDER="openai",
                MODEL_API_URL="https://api.openai.com/v1/responses",
                MODEL_NAME="gpt-5.6-luna",
            ),
            patch.object(
                touch_responder.requests, "post", return_value=api_response
            ) as post,
        ):
            reply = touch_responder._generate_reply(
                [event],
                touch_responder.deque(maxlen=6),
                "你是阿叙。",
            )
            request = post.call_args.kwargs["json"]

        self.assertEqual(reply, "再摸一会儿，我正靠过来呢。")
        self.assertEqual(request["model"], "gpt-5.6-luna")
        self.assertEqual(request["reasoning"], {"effort": "none"})
        self.assertEqual(request["text"], {"verbosity": "low"})
        self.assertFalse(request["store"])


if __name__ == "__main__":
    unittest.main()
