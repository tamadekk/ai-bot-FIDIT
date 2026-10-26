const input = document.getElementById("input");
const sendBtn = document.getElementById("sendBtn");
const chatbox = document.getElementById("chatbox");
const fileInput = document.getElementById("fileInput");
const fileNameLabel = document.getElementById("fileName");

const CHAT_URL = "/chat";
const UPLOAD_URL = "/upload";
const SESSION_STORAGE_KEY = "architectChatSessionId";
const USER_AVATAR = "assets/user-icon.png";
const BOT_AVATAR = "assets/bot.svg";
const DETAIL_BUTTON_LABEL = "Prikaži detaljno objašnjenje";
const DETAIL_BUTTON_USER_MESSAGE = "Želim detaljno objašnjenje.";
const DETAIL_OFFER_TEXT = "Želite li detaljnije objašnjenje? Kliknite gumb ili odgovorite s „da” ili „ne”.";
const THINKING_TEXT = "Razmišljam";
const THINKING_DOT_COUNT = 3;

const sessionId = localStorage.getItem(SESSION_STORAGE_KEY) || crypto.randomUUID();
localStorage.setItem(SESSION_STORAGE_KEY, sessionId);

const scrollChatToBottom = () => {
    chatbox.scrollTop = chatbox.scrollHeight;
};

const appendMessage = (sender, content, { isHtml = false } = {}) => {
    const message = document.createElement("div");
    message.className = `message ${sender}`;

    const avatar = document.createElement("img");
    avatar.className = "avatar";
    avatar.src = sender === "user" ? USER_AVATAR : BOT_AVATAR;

    const bubble = document.createElement("div");
    bubble.className = "bubble";
    if (isHtml) {
        bubble.innerHTML = content;
    } else {
        bubble.textContent = content;
    }

    message.append(avatar, bubble);
    chatbox.appendChild(message);
    scrollChatToBottom();
    return bubble;
};

const postJson = async (url, requestOptions, fallbackErrorMessage) => {
    const response = await fetch(url, { method: "POST", ...requestOptions });
    const responseData = await response.json();
    if (!response.ok) throw new Error(responseData.error || fallbackErrorMessage);
    return responseData;
};

const closeDetailOffers = () => {
    document.querySelectorAll(".detail-btn").forEach((detailButton) => {
        detailButton.disabled = true;
    });
};

const appendDetailOffer = (bubble) => {
    const detailOffer = document.createElement("div");
    detailOffer.className = "detail-offer";

    const offerText = document.createElement("p");
    offerText.textContent = DETAIL_OFFER_TEXT;

    const detailButton = document.createElement("button");
    detailButton.className = "detail-btn";
    detailButton.textContent = DETAIL_BUTTON_LABEL;
    detailButton.addEventListener("click", requestDetailedAnswer);

    detailOffer.append(offerText, detailButton);
    bubble.appendChild(detailOffer);
    scrollChatToBottom();
};

const showThinkingIndicator = () => {
    const thinkingBubble = appendMessage("bot", THINKING_TEXT);
    thinkingBubble.classList.add("thinking");

    for (let dotIndex = 0; dotIndex < THINKING_DOT_COUNT; dotIndex += 1) {
        const dot = document.createElement("span");
        dot.className = "thinking-dot";
        dot.textContent = ".";
        thinkingBubble.appendChild(dot);
    }

    return thinkingBubble.closest(".message");
};

const setChatInputEnabled = (isEnabled) => {
    input.disabled = !isEnabled;
    sendBtn.disabled = !isEnabled;
};

const sendChatRequest = async (payload) => {
    setChatInputEnabled(false);
    const thinkingMessage = showThinkingIndicator();

    try {
        const chatResponse = await postJson(
            CHAT_URL,
            {
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ ...payload, session_id: sessionId }),
            },
            "Greška na serveru",
        );
        thinkingMessage.remove();

        const replyBubble = appendMessage("bot", chatResponse.reply, { isHtml: true });
        if (chatResponse.offer_detail) {
            appendDetailOffer(replyBubble);
        }
    } catch (error) {
        thinkingMessage.remove();
        console.error("CHAT ERROR:", error);
        appendMessage("bot", `Greška: ${error.message}`);
    } finally {
        setChatInputEnabled(true);
        input.focus();
    }
};

const requestDetailedAnswer = () => {
    closeDetailOffers();
    appendMessage("user", DETAIL_BUTTON_USER_MESSAGE);
    sendChatRequest({ detail: true });
};

const sendMessage = () => {
    const message = input.value.trim();
    if (!message) return;

    input.value = "";
    closeDetailOffers();
    appendMessage("user", message);
    sendChatRequest({ message });
};

const uploadDocument = async (file) => {
    const formData = new FormData();
    formData.append("file", file);

    try {
        const uploadResponse = await postJson(UPLOAD_URL, { body: formData }, "Greška pri uploadu dokumenta");
        appendMessage("bot", `Dokument je uploadan. ${uploadResponse.message}`);
    } catch (error) {
        appendMessage("bot", `Greška pri uploadu: ${error.message}`);
    }
};

sendBtn.addEventListener("click", sendMessage);

input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
        sendMessage();
    }
});

fileInput.addEventListener("change", () => {
    const selectedFile = fileInput.files[0];
    if (!selectedFile) return;

    fileNameLabel.textContent = selectedFile.name;
    uploadDocument(selectedFile);
});
