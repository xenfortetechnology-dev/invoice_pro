// static/js/voice-commands.js

document.addEventListener("DOMContentLoaded", () => {

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!SpeechRecognition) {
        console.error("❌ Speech Recognition not supported");
        return;
    }

    const recognition = new SpeechRecognition();
    recognition.lang = "ta-IN";        // Tamil + English both work
    recognition.continuous = true;
    recognition.interimResults = false;

    let isListening = false;

    const voiceBtn = document.getElementById("voiceCreateBtn");

    if (!voiceBtn) {
        console.warn("🎤 Voice button not found");
        return;
    }

    voiceBtn.addEventListener("click", () => {
        if (!isListening) {
            recognition.start();
            isListening = true;
            console.log("🎤 Voice listening started");
        } else {
            recognition.stop();
            isListening = false;
            console.log("🛑 Voice stopped");
        }
    });

    recognition.onresult = (event) => {
        const transcript = event.results[event.results.length - 1][0].transcript.trim();
        console.log("🗣 Spoken:", transcript);

        fetch("/api/voice-command", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text: transcript })
        })
        .then(res => res.json())
        .then(handleVoiceResponse)
        .catch(err => console.error("Voice API error:", err));
    };

    recognition.onerror = (event) => {
        console.error("Speech error:", event.error);
    };

    recognition.onend = () => {
        if (isListening) recognition.start();
    };
});

/* =========================
   Handle AI Response
========================= */
function handleVoiceResponse(data) {
    console.log("🧠 AI Response:", data);

    if (!data.success) {
        alert(data.message || "Voice command failed");
        return;
    }

    switch (data.intent) {

        case "add_item":
            addItemRow();
            setTimeout(() => {
                const row = getLastItemRow();
                if (!row) return;

                row.querySelector('[name="description"]').value = data.entities.item_description;
                row.querySelector('[name="quantity"]').value = data.entities.quantity || 1;
                row.querySelector('[name="unit_price"]').value = data.entities.amount || 0;

                updateInvoiceSummary();
            }, 50);
            break;

        case "save_invoice":
            document.getElementById("saveInvoiceBtn")?.click();
            break;

        case "create_invoice":
            alert(data.message);
            break;

        default:
            console.log("ℹ Unhandled intent:", data.intent);
    }
}

/* =========================
   Helpers
========================= */
function getLastItemRow() {
    const rows = document.querySelectorAll(".item-row");
    return rows[rows.length - 1];
}
