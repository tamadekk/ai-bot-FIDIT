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
app.config["UPLOAD_FOLDER"] = str(UPLOAD_FOLDER)

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

with open(APP_DIR / "architecture_context.md", "r", encoding="utf-8") as f:
    ARCHITECTURE_CONTEXT = f.read()

CHUNK_SIZE = 800
CHUNK_OVERLAP = 120

DOCUMENT_STORE = {
    "chunks": [],
    "embeddings": None,
}

CONVERSATION_MEMORY: dict[str, list[dict[str, str]]] = {}
MAX_CONVERSATION_HISTORY = 12

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
    session_id = session_id or "default"
    if session_id not in CONVERSATION_MEMORY:
        CONVERSATION_MEMORY[session_id] = []
    return CONVERSATION_MEMORY[session_id]


def trim_conversation_history(history: list[dict[str, str]]) -> list[dict[str, str]]:
    if len(history) > MAX_CONVERSATION_HISTORY:
        return history[-MAX_CONVERSATION_HISTORY:]
    return history


def format_conversation_history(history: list[dict[str, str]]) -> str:
    if not history:
        return "Nema prethodnog razgovora."

    lines = []
    for message in history:
        role = "Korisnik" if message["role"] == "user" else "Asistent"
        lines.append(f"{role}: {message['content']}")
    return "\n".join(lines)


def classify_detail_reply(user_message: str) -> str | None:
    normalized_message = re.sub(r"[^\w\s]", "", user_message.lower()).strip()
    if normalized_message in AFFIRMATIVE_REPLIES:
        return DETAIL_REPLY_YES
    if normalized_message in NEGATIVE_REPLIES:
        return DETAIL_REPLY_NO
    return None


def build_chat_messages(
    user_message: str,
    session_id: str,
    answer_mode: str = ANSWER_MODE_SHORT,
) -> list[dict[str, str]]:
    history = trim_conversation_history(get_session_history(session_id))
    mode_settings = ANSWER_MODE_SETTINGS[answer_mode]
    context = find_relevant_context(user_message, top_k=mode_settings["context_chunks"])

    system_prompt = (
        "Odgovaraj kao arhitektonski savjetnik. "
        "Pazi na kontekst razgovora i zapamti posljednje poruke korisnika. "
        "Ako korisnik postavlja follow-up pitanje poput 'što o stanu?', 'a kako sa kućom?' ili 'daj primjer', "
        "odgovori uzimajući u obzir prethodni razgovor i temu koja je već bila spomenuta. "
        "Koristi informacije iz dokumenta ako su relevantne. "
        f"{mode_settings['instruction']}\n\n"
        f"Prethodni razgovor:\n{format_conversation_history(history)}\n\n"
        f"Kontekst dokumenta:\n{context}"
    )

    messages = [{"role": "system", "content": system_prompt}]
    for previous in history:
        messages.append({"role": previous["role"], "content": previous["content"]})
    messages.append({"role": "user", "content": user_message})
    return messages


def extract_text(file_path: str, extension: str) -> str:
    extension = extension.lower()

    if extension == "txt":
        with open(file_path, "r", encoding="utf-8", errors="ignore") as file:
            return file.read()

    if extension == "pdf":
        reader = PdfReader(file_path)
        return "\n".join(
            page.extract_text() or ""
            for page in reader.pages
        )

    if extension == "docx":
        document = Document(file_path)
        return "\n".join(paragraph.text for paragraph in document.paragraphs)

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


@app.route("/")
def serve_frontend_page():
    return app.send_static_file(FRONTEND_PAGE)


@app.route("/upload", methods=["POST"])
def upload_document():
    if "file" not in request.files:
        return jsonify({"error": "Nijedan dokument nije poslan."}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "Datoteka nema naziv."}), 400

    filename = secure_filename(file.filename)
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    allowed_extensions = {"txt", "pdf", "docx"}

    if extension not in allowed_extensions:
        return jsonify({"error": "Podržani formati: TXT, PDF i DOCX. Stari DOC format nije podržan."}), 400

    upload_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(upload_path)

    text = extract_text(upload_path, extension)
    chunks = chunk_text(text)

    try:
        index_document(chunks)
    except Exception as error:
        return build_provider_error_response(error)

    return jsonify({
        "message": "Dokument je uspješno uploadan i obrađen.",
        "chunks": len(chunks),
        "filename": filename,
    })


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

    if is_gemini_provider:
        return complete_with_gemini(messages, max_tokens)

    response = client.chat.complete(
        model=chat_model,
        messages=messages,
        temperature=CHAT_TEMPERATURE,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content or ""


def remember_exchange(session_id: str, user_message: str, assistant_reply: str):
    history = get_session_history(session_id)
    history.append({"role": "user", "content": user_message})
    history.append({"role": "assistant", "content": assistant_reply})
    CONVERSATION_MEMORY[session_id] = trim_conversation_history(history)


@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    user_message = data.get("message", "").strip()
    session_id = str(data.get("session_id") or "default")
    is_detail_button_click = data.get("detail") is True

    if not user_message and not is_detail_button_click:
        return jsonify({"error": "Nije poslan tekst poruke."}), 400

    pending_question = PENDING_DETAIL_QUESTIONS.get(session_id)
    detail_reply = classify_detail_reply(user_message)
    wants_detailed_answer = is_detail_button_click or (bool(pending_question) and detail_reply == DETAIL_REPLY_YES)
    declines_detailed_answer = bool(pending_question) and detail_reply == DETAIL_REPLY_NO

    if is_detail_button_click and not pending_question:
        return jsonify({"error": "Nema pitanja za koje bi se dalo detaljno objašnjenje."}), 400

    if declines_detailed_answer:
        PENDING_DETAIL_QUESTIONS.pop(session_id, None)
        remember_exchange(session_id, user_message, DETAIL_DECLINED_REPLY)
        return jsonify({"reply": markdown.markdown(DETAIL_DECLINED_REPLY), "offer_detail": False})

    try:
        if wants_detailed_answer:
            reply_raw = generate_reply(pending_question, session_id, ANSWER_MODE_DETAILED)
            PENDING_DETAIL_QUESTIONS.pop(session_id, None)
            remember_exchange(session_id, user_message or DETAIL_BUTTON_USER_MESSAGE, reply_raw)
        else:
            reply_raw = generate_reply(user_message, session_id, ANSWER_MODE_SHORT)
            PENDING_DETAIL_QUESTIONS[session_id] = user_message
            remember_exchange(session_id, user_message, reply_raw)

        reply_html = markdown.markdown(reply_raw)
        return jsonify({"reply": reply_html, "offer_detail": not wants_detailed_answer})

    except Exception as error:
        return build_provider_error_response(error)


if __name__ == "__main__":
    app.run(debug=True)