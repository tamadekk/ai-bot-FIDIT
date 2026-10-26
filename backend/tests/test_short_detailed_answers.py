import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("MISTRAL_API_KEY", "test-key")
os.environ["LLM_PROVIDER"] = "mistral"

import server

SESSION_ID = "detail-session"
QUESTION = "Kako urediti interijer vikendice?"
SHORT_REPLY = "Koristite drvo i velike prozore."
DETAILED_REPLY = "## Detaljno\nPrimjer: planinska vikendica s drvenim gredama."


def build_mistral_response(content: str):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


class TestShortAndDetailedAnswers(unittest.TestCase):
    def setUp(self):
        server.CONVERSATION_MEMORY.clear()
        server.PENDING_DETAIL_QUESTIONS.clear()
        self.http_client = server.app.test_client()

    def post_chat(self, payload: dict):
        return self.http_client.post("/chat", json={**payload, "session_id": SESSION_ID})

    def test_classify_detail_reply(self):
        self.assertEqual(server.classify_detail_reply("Da!"), server.DETAIL_REPLY_YES)
        self.assertEqual(server.classify_detail_reply("ne, hvala"), server.DETAIL_REPLY_NO)
        self.assertIsNone(server.classify_detail_reply("A stana?"))

    def test_question_gets_short_answer_with_detail_offer(self):
        with patch.object(server.client.chat, "complete", return_value=build_mistral_response(SHORT_REPLY)) as complete:
            response = self.post_chat({"message": QUESTION})

        body = response.get_json()
        self.assertTrue(body["offer_detail"])
        self.assertEqual(complete.call_args.kwargs["max_tokens"], server.SHORT_ANSWER_MAX_TOKENS)
        self.assertIn(server.SHORT_ANSWER_INSTRUCTION, complete.call_args.kwargs["messages"][0]["content"])
        self.assertEqual(server.PENDING_DETAIL_QUESTIONS[SESSION_ID], QUESTION)

    def test_yes_reply_returns_detailed_answer_for_pending_question(self):
        server.PENDING_DETAIL_QUESTIONS[SESSION_ID] = QUESTION

        with patch.object(server.client.chat, "complete", return_value=build_mistral_response(DETAILED_REPLY)) as complete:
            response = self.post_chat({"message": "da"})

        body = response.get_json()
        sent_messages = complete.call_args.kwargs["messages"]
        self.assertFalse(body["offer_detail"])
        self.assertEqual(complete.call_args.kwargs["max_tokens"], server.DETAILED_ANSWER_MAX_TOKENS)
        self.assertIn(server.DETAILED_ANSWER_INSTRUCTION, sent_messages[0]["content"])
        self.assertEqual(sent_messages[-1]["content"], QUESTION)
        self.assertNotIn(SESSION_ID, server.PENDING_DETAIL_QUESTIONS)

    def test_button_click_returns_detailed_answer(self):
        server.PENDING_DETAIL_QUESTIONS[SESSION_ID] = QUESTION

        with patch.object(server.client.chat, "complete", return_value=build_mistral_response(DETAILED_REPLY)):
            response = self.post_chat({"detail": True})

        history = server.CONVERSATION_MEMORY[SESSION_ID]
        self.assertFalse(response.get_json()["offer_detail"])
        self.assertEqual(history[-2]["content"], server.DETAIL_BUTTON_USER_MESSAGE)

    def test_no_reply_declines_without_calling_api(self):
        server.PENDING_DETAIL_QUESTIONS[SESSION_ID] = QUESTION

        with patch.object(server.client.chat, "complete") as complete:
            response = self.post_chat({"message": "ne"})

        complete.assert_not_called()
        self.assertFalse(response.get_json()["offer_detail"])
        self.assertNotIn(SESSION_ID, server.PENDING_DETAIL_QUESTIONS)

    def test_yes_without_pending_question_is_treated_as_normal_message(self):
        with patch.object(server.client.chat, "complete", return_value=build_mistral_response(SHORT_REPLY)) as complete:
            self.post_chat({"message": "da"})

        self.assertEqual(complete.call_args.kwargs["max_tokens"], server.SHORT_ANSWER_MAX_TOKENS)

    def test_button_click_without_pending_question_is_rejected(self):
        response = self.post_chat({"detail": True})
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
