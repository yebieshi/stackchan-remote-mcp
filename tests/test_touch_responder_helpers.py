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

    def test_generates_concise_reply_with_openrouter(self) -> None:
        api_response = Mock()
        api_response.raise_for_status.return_value = None
        api_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "“嗯，摸到了，我正靠过来。”",
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

        with (
            patch.multiple(
                touch_responder,
                MODEL_PROVIDER="openrouter",
                MODEL_API_URL=(
                    "https://openrouter.ai/api/v1/chat/completions"
                ),
                MODEL_NAME="openai/gpt-4.1-nano",
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
            headers = post.call_args.kwargs["headers"]

        self.assertEqual(reply, "嗯，摸到了，我正靠过来。")
        self.assertEqual(request["model"], "openai/gpt-4.1-nano")
        self.assertEqual(
            [message["role"] for message in request["messages"]],
            ["system", "user"],
        )
        self.assertFalse(request["stream"])
        self.assertNotIn("enable_thinking", request)
        self.assertEqual(
            headers["X-OpenRouter-Title"], "StackChan Tactile Bridge"
        )
        system_prompt = request["messages"][0]["content"]
        self.assertIn("不要表演深情", system_prompt)
        self.assertIn("油腻套话", system_prompt)
        self.assertIn("这不是按摩或服务体验", system_prompt)
        self.assertIn("认出她并接住她的靠近", system_prompt)
        self.assertIn("历史回复只用于保持连续", system_prompt)

    def test_retries_a_touch_reply_that_rates_the_users_technique(
        self,
    ) -> None:
        first_response = Mock()
        first_response.raise_for_status.return_value = None
        first_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "你这手法轻得刚刚好。",
                    }
                }
            ]
        }
        second_response = Mock()
        second_response.raise_for_status.return_value = None
        second_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "知道是你，我回头啦。",
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

        with (
            patch.multiple(
                touch_responder,
                MODEL_PROVIDER="openrouter",
                MODEL_API_URL=(
                    "https://openrouter.ai/api/v1/chat/completions"
                ),
                MODEL_NAME="openai/gpt-4.1-nano",
            ),
            patch.object(
                touch_responder.requests,
                "post",
                side_effect=[first_response, second_response],
            ) as post,
        ):
            reply = touch_responder._generate_reply(
                [event],
                touch_responder.deque(maxlen=6),
                "你是阿叙。",
            )

        self.assertEqual(reply, "知道是你，我回头啦。")
        self.assertEqual(post.call_count, 2)
        retry_prompt = post.call_args.kwargs["json"]["messages"][0]["content"]
        self.assertIn("候选回复错误地评价了触摸体验", retry_prompt)


if __name__ == "__main__":
    unittest.main()
