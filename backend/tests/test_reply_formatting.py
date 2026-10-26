import os
import unittest

os.environ.setdefault("MISTRAL_API_KEY", "test-key")
os.environ["LLM_PROVIDER"] = "mistral"

import server


class TestReplyFormatting(unittest.TestCase):
    def render(self, reply_markdown: str) -> str:
        with server.app.app_context():
            return server.build_reply_response(reply_markdown, offer_detail=False).get_json()["reply"]

    def test_bullet_list_after_paragraph_is_rendered_as_list(self):
        reply_html = self.render("Savjeti:\n* Svijetle boje\n* Ogledala")

        self.assertIn("<ul>", reply_html)
        self.assertIn("<li>Svijetle boje</li>", reply_html)

    def test_numbered_list_after_paragraph_is_rendered_as_list(self):
        reply_html = self.render("Koraci:\n1. Izmjeri prostor\n2. Odaberi namještaj")

        self.assertIn("<ol>", reply_html)
        self.assertIn("<li>Odaberi namještaj</li>", reply_html)

    def test_consecutive_list_items_stay_in_one_list(self):
        separated = server.separate_lists_from_paragraphs("Uvod\n* prvi\n* drugi")

        self.assertEqual(separated, "Uvod\n\n* prvi\n* drugi")


if __name__ == "__main__":
    unittest.main()
