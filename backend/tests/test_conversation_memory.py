import os
import unittest

os.environ.setdefault("MISTRAL_API_KEY", "test-key")
os.environ["LLM_PROVIDER"] = "mistral"

import server


class TestConversationMemory(unittest.TestCase):
    def setUp(self):
        server.CONVERSATION_MEMORY.clear()

    def test_trims_history_to_latest_messages(self):
        history = [
            {"role": "user", "content": "one"},
            {"role": "assistant", "content": "two"},
            {"role": "user", "content": "three"},
            {"role": "assistant", "content": "four"},
            {"role": "user", "content": "five"},
            {"role": "assistant", "content": "six"},
            {"role": "user", "content": "seven"},
            {"role": "assistant", "content": "eight"},
            {"role": "user", "content": "nine"},
            {"role": "assistant", "content": "ten"},
            {"role": "user", "content": "eleven"},
            {"role": "assistant", "content": "twelve"},
        ]

        trimmed = server.trim_conversation_history(history)
        self.assertEqual(len(trimmed), 12)
        self.assertEqual(trimmed[0]["content"], "one")
        self.assertEqual(trimmed[-1]["content"], "twelve")

    def test_build_chat_messages_includes_previous_context(self):
        session_id = "demo-session"
        server.CONVERSATION_MEMORY[session_id] = [
            {"role": "user", "content": "Do you have an example of interior design for a holiday house?"},
            {"role": "assistant", "content": "Yes, a mountain holiday house with warm wood and large windows."},
        ]

        messages = server.build_chat_messages("What about an apartment?", session_id)

        self.assertIn("holiday house", messages[0]["content"].lower())
        self.assertIn("What about an apartment?", messages[-1]["content"])


if __name__ == "__main__":
    unittest.main()
