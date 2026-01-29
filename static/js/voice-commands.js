// static/js/voice-commands.js
// Script-based voice recognition - No AI dependencies
// Supports English and Tamil/Tanglish commands

document.addEventListener("DOMContentLoaded", () => {

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!SpeechRecognition) {
        console.error("❌ Speech Recognition not supported in this browser");
        return;
    }

    const recognition = new SpeechRecognition();
    let currentLanguage = "en-IN";  // Default to English
    let isListening = false;

    // Language toggle
    const langToggle = document.getElementById("voiceLangToggle");
    if (langToggle) {
        langToggle.addEventListener("change", (e) => {
            currentLanguage = e.target.value;
            recognition.lang = currentLanguage;
            console.log(`🌐 Language switched to: ${currentLanguage}`);

            // Update button text
            const voiceBtn = document.getElementById("voiceCreateBtn");
            if (voiceBtn) {
                voiceBtn.textContent = currentLanguage === "ta-IN" ? "🎤 குரல்" : "🎤 Voice";
            }
        });
    }

    // Configure recognition
    recognition.lang = currentLanguage;
    recognition.continuous = true;
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;

    const voiceBtn = document.getElementById("voiceCreateBtn");

    if (!voiceBtn) {
        console.warn("🎤 Voice button not found on this page");
        return;
    }

    // Voice button click handler
    voiceBtn.addEventListener("click", () => {
        if (!isListening) {
            try {
                recognition.start();
                isListening = true;
                voiceBtn.classList.add("listening");
                voiceBtn.textContent = "🔴 Listening...";
                console.log("🎤 Voice listening started");
            } catch (e) {
                console.error("Error starting recognition:", e);
            }
        } else {
            recognition.stop();
            isListening = false;
            voiceBtn.classList.remove("listening");
            voiceBtn.textContent = currentLanguage === "ta-IN" ? "🎤 குரல்" : "🎤 Voice";
            console.log("🛑 Voice stopped");
        }
    });

    // Recognition result handler
    recognition.onresult = (event) => {
        const transcript = event.results[event.results.length - 1][0].transcript.trim();
        console.log("🗣 Spoken:", transcript);

        // Show visual feedback
        showVoiceFeedback(transcript);

        // Send to backend
        fetch("/api/voice-command", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                text: transcript,
                language: currentLanguage
            })
        })
            .then(res => res.json())
            .then(handleVoiceResponse)
            .catch(err => {
                console.error("Voice API error:", err);
                showError("Failed to process voice command");
            });
    };

    recognition.onerror = (event) => {
        console.error("Speech recognition error:", event.error);
        isListening = false;
        voiceBtn.classList.remove("listening");
        voiceBtn.textContent = currentLanguage === "ta-IN" ? "🎤 குரல்" : "🎤 Voice";

        if (event.error === "no-speech") {
            showError("No speech detected. Please try again.");
        } else if (event.error === "not-allowed") {
            showError("Microphone access denied. Please enable microphone permissions.");
        }
    };

    recognition.onend = () => {
        if (isListening) {
            try {
                recognition.start();
            } catch (e) {
                console.log("Recognition ended");
                isListening = false;
                voiceBtn.classList.remove("listening");
                voiceBtn.textContent = currentLanguage === "ta-IN" ? "🎤 குரல்" : "🎤 Voice";
            }
        }
    };
});

/* =========================
   Handle Voice Response
========================= */
function handleVoiceResponse(data) {
    console.log("🧠 Voice Response:", data);

    if (!data.success) {
        showError(data.message || "Voice command failed");

        // Show suggestions if available
        if (data.suggestions && data.suggestions.length > 0) {
            showSuggestions(data.suggestions);
        }
        return;
    }

    // Show success message
    showSuccess(data.message);

    // Handle different intents
    switch (data.intent) {

        case "create_invoice":
            if (data.client_id) {
                // Redirect to create invoice page with client pre-selected
                setTimeout(() => {
                    window.location.href = `/create_invoice?client_id=${data.client_id}`;
                }, 1000);
            }
            break;

        case "add_item":
            if (typeof addItemRow === "function") {
                addItemRow();
                setTimeout(() => {
                    const row = getLastItemRow();
                    if (!row) return;

                    // Populate the row with voice data
                    if (data.entities.hsn_code) {
                        const hsnInput = row.querySelector('[name="hsn_code"]');
                        if (hsnInput) hsnInput.value = data.entities.hsn_code;
                    }

                    const descInput = row.querySelector('[name="description"]');
                    if (descInput) descInput.value = data.entities.item_description || "";

                    const qtyInput = row.querySelector('[name="quantity"]');
                    if (qtyInput) qtyInput.value = data.entities.quantity || 1;

                    const priceInput = row.querySelector('[name="unit_price"]');
                    if (priceInput) priceInput.value = data.entities.amount || 0;

                    // Set unit if available
                    if (data.entities.unit) {
                        const unitSelect = row.querySelector('[name="unit"]');
                        if (unitSelect) {
                            for (let i = 0; i < unitSelect.options.length; i++) {
                                if (unitSelect.options[i].value.toLowerCase() === data.entities.unit.toLowerCase()) {
                                    unitSelect.selectedIndex = i;
                                    break;
                                }
                            }
                        }
                    }

                    // Set tax if available
                    if (data.entities.tax) {
                        const taxInput = row.querySelector('[name="tax_percentage"]');
                        if (taxInput) taxInput.value = data.entities.tax;
                    }

                    // Update summary
                    if (typeof updateInvoiceSummary === "function") {
                        updateInvoiceSummary();
                    }
                }, 100);
            } else {
                console.log("Not on create page, item added to backend session");
            }
            break;

        case "save_invoice":
            const saveBtn = document.getElementById("saveInvoiceBtn");
            if (saveBtn) {
                saveBtn.click();
            } else if (data.invoice_id) {
                // Redirect to invoice detail page
                setTimeout(() => {
                    window.location.href = `/invoice/${data.invoice_id}`;
                }, 1500);
            }
            break;

        case "calculate_total":
            // Show total in a prominent way
            if (data.total_amount !== undefined) {
                showSuccess(`Total: ₹${data.total_amount} (${data.item_count} items)`);
            }
            break;

        case "search_client":
            if (data.client) {
                showSuccess(`Found: ${data.client.name} - ${data.client.email}`);
            } else if (data.clients) {
                const names = data.clients.map(c => c.name).join(", ");
                showSuccess(`Found clients: ${names}`);
            }
            break;

        default:
            console.log("ℹ Unhandled intent:", data.intent);
    }
}

/* =========================
   Helper Functions
========================= */
function getLastItemRow() {
    const rows = document.querySelectorAll(".item-row");
    return rows[rows.length - 1];
}

function showVoiceFeedback(text) {
    // Create or update feedback element
    let feedback = document.getElementById("voiceFeedback");
    if (!feedback) {
        feedback = document.createElement("div");
        feedback.id = "voiceFeedback";
        feedback.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: #4CAF50;
            color: white;
            padding: 15px 20px;
            border-radius: 8px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            z-index: 10000;
            max-width: 300px;
            animation: slideIn 0.3s ease-out;
        `;
        document.body.appendChild(feedback);
    }

    feedback.textContent = `🗣 "${text}"`;
    feedback.style.background = "#2196F3";

    // Auto-hide after 3 seconds
    setTimeout(() => {
        if (feedback.parentNode) {
            feedback.remove();
        }
    }, 3000);
}

function showSuccess(message) {
    showNotification(message, "success");
}

function showError(message) {
    showNotification(message, "error");
}

function showNotification(message, type = "info") {
    const colors = {
        success: "#4CAF50",
        error: "#f44336",
        info: "#2196F3"
    };

    const notification = document.createElement("div");
    notification.style.cssText = `
        position: fixed;
        top: 80px;
        right: 20px;
        background: ${colors[type]};
        color: white;
        padding: 15px 20px;
        border-radius: 8px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        z-index: 10000;
        max-width: 350px;
        animation: slideIn 0.3s ease-out;
    `;
    notification.textContent = message;
    document.body.appendChild(notification);

    setTimeout(() => {
        notification.remove();
    }, 4000);
}

function showSuggestions(suggestions) {
    const suggestionBox = document.createElement("div");
    suggestionBox.style.cssText = `
        position: fixed;
        top: 150px;
        right: 20px;
        background: white;
        color: #333;
        padding: 15px;
        border-radius: 8px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.2);
        z-index: 10000;
        max-width: 350px;
    `;

    let html = "<strong>Try these commands:</strong><ul style='margin: 10px 0; padding-left: 20px;'>";
    suggestions.forEach(s => {
        html += `<li style='margin: 5px 0;'>${s}</li>`;
    });
    html += "</ul>";

    suggestionBox.innerHTML = html;
    document.body.appendChild(suggestionBox);

    setTimeout(() => {
        suggestionBox.remove();
    }, 8000);
}

// Add CSS animation
const style = document.createElement("style");
style.textContent = `
    @keyframes slideIn {
        from {
            transform: translateX(400px);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }
    
    .listening {
        animation: pulse 1.5s infinite;
        background-color: #f44336 !important;
    }
    
    @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.6; }
    }
`;
document.head.appendChild(style);
