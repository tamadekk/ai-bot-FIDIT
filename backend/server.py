import os
import re
from http import HTTPStatus
from pathlib import Path

import markdown
import numpy as np
from dotenv import load_dotenv
from docx import Document
from flask import Flask, jsonify, request
from google import genai
from google.genai import types as genai_types
from mistralai.client.sdk import Mistral
from PyPDF2 import PdfReader
from werkzeug.utils import secure_filename

APP_DIR = Path(__file__).resolve().parent
PROJECT_DIR = APP_DIR.parent
FRONTEND_DIR = PROJECT_DIR / "frontend"
FRONTEND_PAGE = "index.html"
UPLOAD_FOLDER = APP_DIR / "uploads"
UPLOAD_FOLDER.mkdir(exist_ok=True)

load_dotenv(PROJECT_DIR / ".env")

app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path="")

PROVIDER_MISTRAL = "mistral"
PROVIDER_GEMINI = "gemini"
CHAT_TEMPERATURE = 0.5

llm_provider = os.getenv("LLM_PROVIDER", PROVIDER_MISTRAL).lower()
is_gemini_provider = llm_provider == PROVIDER_GEMINI

if is_gemini_provider:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("MISSING_ENV: Dodaj GEMINI_API_KEY u .env datoteku.")

    provider_name = "Gemini"
    chat_model = os.getenv("GEMINI_CHAT_MODEL", "gemini-3.5-flash-lite")
    embedding_model = "gemini-embedding-001"
    client = genai.Client(api_key=api_key)
else:
    api_key = os.getenv("MISTRAL_API_KEY")
    if not api_key:
        raise RuntimeError("MISSING_ENV: Dodaj MISTRAL_API_KEY u .env datoteku.")

    provider_name = "Mistral"
    chat_model = os.getenv("MISTRAL_CHAT_MODEL", "mistral-small-latest")
    embedding_model = "mistral-embed"
    client = Mistral(api_key=api_key)

ARCHITECTURE_CONTEXT = (APP_DIR / "architecture_context.md").read_text(encoding="utf-8")

ALLOWED_EXTENSIONS = {"txt", "pdf", "docx"}
CHUNK_SIZE = 800
CHUNK_OVERLAP = 120

DOCUMENT_STORE = {
    "chunks": [],
    "embeddings": None,
}

DEFAULT_SESSION_ID = "default"
MAX_CONVERSATION_HISTORY = 12
CONVERSATION_MEMORY: dict[str, list[dict[str, str]]] = {}
PENDING_DETAIL_QUESTIONS: dict[str, str] = {}

ANSWER_MODE_SHORT = "short"
ANSWER_MODE_DETAILED = "detailed"

SHORT_ANSWER_MAX_TOKENS = 200
DETAILED_ANSWER_MAX_TOKENS = 2000
SHORT_ANSWER_CONTEXT_CHUNKS = 3
DETAILED_ANSWER_CONTEXT_CHUNKS = 8

AFFIRMATIVE_REPLIES = {"da", "da molim", "moze", "može", "naravno", "svakako", "yes", "ok"}
NEGATIVE_REPLIES = {"ne", "ne hvala", "nema potrebe", "no"}
DETAIL_REPLY_YES = "yes"
DETAIL_REPLY_NO = "no"

DETAIL_BUTTON_USER_MESSAGE = "Želim detaljno objašnjenje."
DETAIL_DECLINED_REPLY = "U redu. Slobodno postavite novo pitanje."

BASE_INSTRUCTION = (
    "Odgovaraj kao arhitektonski savjetnik. "
    "Pazi na kontekst razgovora i zapamti posljednje poruke korisnika. "
    "Ako korisnik postavlja follow-up pitanje poput 'što o stanu?', 'a kako sa kućom?' ili 'daj primjer', "
    "odgovori uzimajući u obzir prethodni razgovor i temu koja je već bila spomenuta. "
    "Koristi informacije iz dokumenta ako su relevantne. "
)
SHORT_ANSWER_INSTRUCTION = (
    "Odgovori KRATKO: najviše 1–2 rečenice, bez naslova, lista i primjera. "
    "Nemoj nuditi detaljnije objašnjenje, to će sučelje ponuditi samo."
)
DETAILED_ANSWER_INSTRUCTION = (
    "Korisnik je zatražio DETALJNO objašnjenje pitanja na koje je već dobio kratki odgovor. "
    "Daj opširan odgovor koji uključuje sve relevantne informacije iz dokumenta, "
    "uključujući primjere i objašnjenja. Koristi Markdown naslove i liste gdje pomažu preglednosti."
)
ANSWER_MODE_SETTINGS = {
    ANSWER_MODE_SHORT: {
        "instruction": SHORT_ANSWER_INSTRUCTION,
        "max_tokens": SHORT_ANSWER_MAX_TOKENS,
        "context_chunks": SHORT_ANSWER_CONTEXT_CHUNKS,
    },
    ANSWER_MODE_DETAILED: {
        "instruction": DETAILED_ANSWER_INSTRUCTION,
        "max_tokens": DETAILED_ANSWER_MAX_TOKENS,
        "context_chunks": DETAILED_ANSWER_CONTEXT_CHUNKS,
    },
}


def get_session_history(session_id: str) -> list[dict[str, str]]:
    return CONVERSATION_MEMORY.setdefault(session_id, [])


def trim_conversation_history(history: list[dict[str, str]]) -> list[dict[str, str]]:
    return history[-MAX_CONVERSATION_HISTORY:]


def remember_exchange(session_id: str, user_message: str, assistant_reply: str):
    history = get_session_history(session_id)
    history.append({"role": "user", "content": user_message})
    history.append({"role": "assistant", "content": assistant_reply})
    CONVERSATION_MEMORY[session_id] = trim_conversation_history(history)


def classify_detail_reply(user_message: str) -> str | None:
    normalized_message = re.sub(r"[^\w\s]", "", user_message.lower()).strip()
    if normalized_message in AFFIRMATIVE_REPLIES:
        return DETAIL_REPLY_YES
    if normalized_message in NEGATIVE_REPLIES:
        return DETAIL_REPLY_NO
    return None


def extract_text(file_path: Path, extension: str) -> str:
    if extension == "txt":
        return file_path.read_text(encoding="utf-8", errors="ignore")
    if extension == "pdf":
        return "\n".join(page.extract_text() or "" for page in PdfReader(str(file_path)).pages)
    if extension == "docx":
        return "\n".join(paragraph.text for paragraph in Document(str(file_path)).paragraphs)
    return ""


def chunk_text(text: str) -> list[str]:
    chunk_step = CHUNK_SIZE - CHUNK_OVERLAP
    chunks = [text[start:start + CHUNK_SIZE] for start in range(0, len(text), chunk_step)]
    return [chunk for chunk in chunks if chunk.strip()]


def embed_text(text: str) -> np.ndarray:
    if is_gemini_provider:
        response = client.models.embed_content(model=embedding_model, contents=[text])
        return np.asarray(response.embeddings[0].values, dtype="float32")

    response = client.embeddings.create(model=embedding_model, inputs=[text])
    return np.asarray(response.data[0].embedding, dtype="float32")


def index_document(chunks: list[str]):
    embeddings = np.vstack([embed_text(chunk) for chunk in chunks]) if chunks else None
    DOCUMENT_STORE["chunks"] = chunks
    DOCUMENT_STORE["embeddings"] = embeddings


def find_relevant_context(question: str, top_k: int) -> str:
    has_indexed_document = bool(DOCUMENT_STORE["chunks"])
    if not has_indexed_document:
        return ARCHITECTURE_CONTEXT

    distances = np.sum((DOCUMENT_STORE["embeddings"] - embed_text(question)) ** 2, axis=1)
    closest_chunk_indices = np.argsort(distances)[:top_k]
    return "\n\n".join(DOCUMENT_STORE["chunks"][index] for index in closest_chunk_indices)


def build_chat_messages(
    user_message: str,
    session_id: str,
    answer_mode: str = ANSWER_MODE_SHORT,
) -> list[dict[str, str]]:
    history = trim_conversation_history(get_session_history(session_id))
    mode_settings = ANSWER_MODE_SETTINGS[answer_mode]
    context = find_relevant_context(user_message, mode_settings["context_chunks"])

    system_prompt = (
        f"{BASE_INSTRUCTION}{mode_settings['instruction']}\n\n"
        f"Kontekst dokumenta:\n{context}"
    )
    return [
        {"role": "system", "content": system_prompt},
        *history,
        {"role": "user", "content": user_message},
    ]


def complete_with_mistral(messages: list[dict[str, str]], max_tokens: int) -> str:
    response = client.chat.complete(
        model=chat_model,
        messages=messages,
        temperature=CHAT_TEMPERATURE,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content or ""


def complete_with_gemini(messages: list[dict[str, str]], max_tokens: int) -> str:
    system_message, *conversation_messages = messages
    gemini_contents = [
        genai_types.Content(
            role="model" if message["role"] == "assistant" else "user",
            parts=[genai_types.Part(text=message["content"])],
        )
        for message in conversation_messages
    ]
    response = client.models.generate_content(
        model=chat_model,
        contents=gemini_contents,
        config=genai_types.GenerateContentConfig(
            system_instruction=system_message["content"],
            temperature=CHAT_TEMPERATURE,
            max_output_tokens=max_tokens,
        ),
    )
    return response.text or ""


def generate_reply(question: str, session_id: str, answer_mode: str) -> str:
    messages = build_chat_messages(question, session_id, answer_mode)
    max_tokens = ANSWER_MODE_SETTINGS[answer_mode]["max_tokens"]
    complete_chat = complete_with_gemini if is_gemini_provider else complete_with_mistral
    return complete_chat(messages, max_tokens)


def build_error_response(message: str, status: HTTPStatus):
    return jsonify({"error": message}), status


def build_provider_error_response(error: Exception):
    print(f"{provider_name} API greška:", error)
    status_code = getattr(error, "status_code", None) or getattr(error, "code", None)
    if status_code == HTTPStatus.TOO_MANY_REQUESTS:
        return build_error_response(
            f"{provider_name} API ograničio je broj zahtjeva. Pričekaj malo pa pokušaj ponovno.",
            HTTPStatus.TOO_MANY_REQUESTS,
        )
    return build_error_response(
        f"Došlo je do greške prilikom komunikacije s {provider_name} API-jem.",
        HTTPStatus.INTERNAL_SERVER_ERROR,
    )


def build_reply_response(reply_markdown: str, offer_detail: bool):
    return jsonify({"reply": markdown.markdown(reply_markdown), "offer_detail": offer_detail})


@app.route("/")
def serve_frontend_page():
    return app.send_static_file(FRONTEND_PAGE)


@app.route("/upload", methods=["POST"])
def upload_document():
    uploaded_file = request.files.get("file")
    if uploaded_file is None:
        return build_error_response("Nijedan dokument nije poslan.", HTTPStatus.BAD_REQUEST)

    filename = secure_filename(uploaded_file.filename or "")
    if not filename:
        return build_error_response("Datoteka nema naziv.", HTTPStatus.BAD_REQUEST)

    extension = Path(filename).suffix.lstrip(".").lower()
    if extension not in ALLOWED_EXTENSIONS:
        return build_error_response(
            "Podržani formati: TXT, PDF i DOCX. Stari DOC format nije podržan.",
            HTTPStatus.BAD_REQUEST,
        )

    upload_path = UPLOAD_FOLDER / filename
    uploaded_file.save(upload_path)
    chunks = chunk_text(extract_text(upload_path, extension))

    try:
        index_document(chunks)
    except Exception as error:
        return build_provider_error_response(error)

    return jsonify({
        "message": "Dokument je uspješno uploadan i obrađen.",
        "chunks": len(chunks),
        "filename": filename,
    })


@app.route("/chat", methods=["POST"])
def chat():
    request_data = request.get_json(silent=True) or {}
    user_message = request_data.get("message", "").strip()
    session_id = str(request_data.get("session_id") or DEFAULT_SESSION_ID)
    is_detail_button_click = request_data.get("detail") is True

    if not user_message and not is_detail_button_click:
        return build_error_response("Nije poslan tekst poruke.", HTTPStatus.BAD_REQUEST)

    pending_question = PENDING_DETAIL_QUESTIONS.get(session_id)
    if is_detail_button_click and not pending_question:
        return build_error_response(
            "Nema pitanja za koje bi se dalo detaljno objašnjenje.",
            HTTPStatus.BAD_REQUEST,
        )

    detail_reply = classify_detail_reply(user_message) if pending_question else None
    if detail_reply == DETAIL_REPLY_NO:
        PENDING_DETAIL_QUESTIONS.pop(session_id)
        remember_exchange(session_id, user_message, DETAIL_DECLINED_REPLY)
        return build_reply_response(DETAIL_DECLINED_REPLY, offer_detail=False)

    wants_detailed_answer = is_detail_button_click or detail_reply == DETAIL_REPLY_YES

    try:
        if wants_detailed_answer:
            reply = generate_reply(pending_question, session_id, ANSWER_MODE_DETAILED)
            PENDING_DETAIL_QUESTIONS.pop(session_id)
        else:
            reply = generate_reply(user_message, session_id, ANSWER_MODE_SHORT)
            PENDING_DETAIL_QUESTIONS[session_id] = user_message
    except Exception as error:
        return build_provider_error_response(error)

    remember_exchange(session_id, user_message or DETAIL_BUTTON_USER_MESSAGE, reply)
    return build_reply_response(reply, offer_detail=not wants_detailed_answer)


if __name__ == "__main__":
    app.run(debug=True)
