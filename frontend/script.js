const input = document.getElementById("input");
const sendBtn = document.getElementById("sendBtn");
const chatbox = document.getElementById("chatbox");
const fileInput = document.getElementById("fileInput");
const fileNameLabel = document.getElementById("fileName");

const CHAT_URL = "http://localhost:5000/chat";
const DETAIL_BUTTON_LABEL = "Prikaži detaljno objašnjenje";
const DETAIL_BUTTON_USER_MESSAGE = "Želim detaljno objašnjenje.";
const DETAIL_OFFER_TEXT = "Želite li detaljnije objašnjenje? Kliknite gumb ili odgovorite s „da” ili „ne”.";

const sessionId = localStorage.getItem("architectChatSessionId") || crypto.randomUUID();
localStorage.setItem("architectChatSessionId", sessionId);

function appendMessage(sender, text) {
    const msg = document.createElement("div");
    msg.className = "message " + sender;

    const avatar = document.createElement("img");
    avatar.className = "avatar";
    avatar.src = sender === "user" ? "assets/user-icon.png" : "assets/bot.png";

    const bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.innerHTML = text;

    msg.appendChild(avatar);
    msg.appendChild(bubble);
    chatbox.appendChild(msg);
    chatbox.scrollTop = chatbox.scrollHeight;
    return bubble;
}

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

    detailOffer.appendChild(offerText);
    detailOffer.appendChild(detailButton);
    bubble.appendChild(detailOffer);
    chatbox.scrollTop = chatbox.scrollHeight;
};

const postChatRequest = async (payload) => {
    try {
        const response = await fetch(CHAT_URL, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ...payload, session_id: sessionId }),
        });

        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Greška na serveru");

        const replyBubble = appendMessage("bot", data.reply);
        if (data.offer_detail) {
            appendDetailOffer(replyBubble);
        }
    } catch (error) {
        console.error("CHAT ERROR:", error);
        appendMessage("bot", "Greška: " + error.message);
    }
};

const requestDetailedAnswer = () => {
    closeDetailOffers();
    appendMessage("user", DETAIL_BUTTON_USER_MESSAGE);
    postChatRequest({ detail: true });
};

async function uploadDocument(file) {
    if (!file) return;

    const formData = new FormData();
    formData.append("file", file);

    try {
        const response = await fetch("http://localhost:5000/upload", {
            method: "POST",
            body: formData,
        });

        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || "Greška pri uploadu dokumenta");
        }

        appendMessage("bot", `<strong>Dokument je uploadan.</strong><br>${data.message}`);
    } catch (error) {
        appendMessage("bot", "Greška pri uploadu: " + error.message);
    }
}

const sendMessage = () => {
    const message = input.value.trim();
    if (!message) return;

    input.value = "";
    closeDetailOffers();
    appendMessage("user", message);
    postChatRequest({ message });
};

sendBtn.addEventListener("click", sendMessage);

input.addEventListener("keypress", function (e) {
    if (e.key === "Enter") {
        sendMessage();
    }
});

fileInput.addEventListener("change", function () {
    const file = fileInput.files[0];
    if (!file) return;

    fileNameLabel.textContent = file.name;
    uploadDocument(file);
});
