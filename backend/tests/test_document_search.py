import os
import unittest
from unittest.mock import patch

import numpy as np

os.environ.setdefault("MISTRAL_API_KEY", "test-key")
os.environ["LLM_PROVIDER"] = "mistral"

import server

FAKE_EMBEDDINGS = {
    "drvo i kamen": [1.0, 0.0],
    "svijetle boje": [0.0, 1.0],
    "vikendica": [0.9, 0.1],
}


def fake_embed_text(text: str) -> np.ndarray:
    return np.asarray(FAKE_EMBEDDINGS[text], dtype="float32")


class TestDocumentSearch(unittest.TestCase):
    def tearDown(self):
        server.DOCUMENT_STORE["chunks"] = []
        server.DOCUMENT_STORE["embeddings"] = None

    def test_chunk_text_skips_blank_chunks(self):
        text = "a" * server.CHUNK_SIZE + " " * server.CHUNK_SIZE

        chunks = server.chunk_text(text)

        self.assertTrue(all(chunk.strip() for chunk in chunks))

    def test_chunk_text_overlaps_neighbouring_chunks(self):
        text = "".join(str(index % 10) for index in range(server.CHUNK_SIZE * 2))

        first_chunk, second_chunk, *_ = server.chunk_text(text)

        self.assertEqual(first_chunk[-server.CHUNK_OVERLAP:], second_chunk[:server.CHUNK_OVERLAP])

    def test_without_document_uses_default_context(self):
        self.assertEqual(server.find_relevant_context("vikendica", top_k=1), server.ARCHITECTURE_CONTEXT)

    def test_returns_closest_chunk(self):
        with patch.object(server, "embed_text", side_effect=fake_embed_text):
            server.index_document(["drvo i kamen", "svijetle boje"])
            context = server.find_relevant_context("vikendica", top_k=1)

        self.assertEqual(context, "drvo i kamen")


if __name__ == "__main__":
    unittest.main()
