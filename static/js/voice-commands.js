// static/js/voice-commands.js

document.addEventListener("DOMContentLoaded", () => {

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!SpeechRecognition) {
        console.error("❌ Speech Recognition not supported");
        return;
    }

    const recognition = new SpeechRecognition();
    recognition.lang = "en-IN";        // English (India) for better command recognition
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
            if (typeof addItemRow === "function") {
                addItemRow();
                setTimeout(() => {
                    const row = getLastItemRow();
                    if (!row) return;

                    if (data.entities.hsn_code) {
                        row.querySelector('[name="hsn_code"]').value = data.entities.hsn_code;
                    }
                    row.querySelector('[name="description"]').value = data.entities.item_description;
                    row.querySelector('[name="quantity"]').value = data.entities.quantity || 1;
                    row.querySelector('[name="unit_price"]').value = data.entities.amount || 0;

                    if (data.entities.unit) {
                        // Attempt to set unit if it matches one of the options (Nos, Kg, etc)
                        // Simple matching
                        const unitSelect = row.querySelector('[name="unit"]');
                        // iterate options to find case-insensitive match
                        for (let i = 0; i < unitSelect.options.length; i++) {
                            if (unitSelect.options[i].value.toLowerCase() === data.entities.unit.toLowerCase()) {
                                unitSelect.selectedIndex = i;
                                break;
                            }
                        }
                    }

                    if (data.entities.tax) {
                        row.querySelector('[name="tax_percentage"]').value = data.entities.tax;
                    }

                    if (typeof updateInvoiceSummary === "function") {
                        updateInvoiceSummary();
                    }
                }, 50);
            } else {
                console.log("Not on create page, using backend state");
                alert(data.message);
            }
            break;

        case "save_invoice":
            const saveBtn = document.getElementById("saveInvoiceBtn");
            if (saveBtn) {
                saveBtn.click();
            } else {
                alert(data.message);
                if (data.invoice_id) {
                    window.location.href = `/invoice/${data.invoice_id}`;
                }
            }
            break;

        case "create_invoice":
            if (data.client_id) {
                // Redirects to create invoice page with client pre-selected (requires backend support or just navigation)
                // Assuming we want to just go to the page:
                window.location.href = `/create_invoice?client_id=${data.client_id}`;
            } else {
                alert(data.message);
            }
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
