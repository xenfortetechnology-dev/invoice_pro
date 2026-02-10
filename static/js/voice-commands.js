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
    recognition.onresult = async (event) => {
        const transcript = event.results[event.results.length - 1][0].transcript.trim();
        console.log("🗣 Spoken:", transcript);

        // Show visual feedback
        showVoiceFeedback(transcript);

        // Process command directly in browser (with cloud DB integration)
        const response = await processVoiceCommand(transcript, currentLanguage);
        handleVoiceResponse(response);
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
   Process Voice Command (Client-Side with Cloud DB)
========================= */
async function processVoiceCommand(text, language) {
    const normalized = text.toLowerCase().trim();
    console.log("🧠 Processing command:", normalized);

    // Pattern 1: Simplified tax - "add HSN 1413 item soap quantity 5 units kg rate 500 tax 9 9 9"
    // Accepts: HSN/HSM (speech recognition), "tax" followed by 3 numbers (CGST SGST IGST)
    // Uses non-greedy match for item name to avoid capturing quantity/unit text
    let match = normalized.match(/(?:add\s+)?(?:hs[nm]\s+([\d\s]+?)\s+)?items?\s+(\w+(?:\s+\w+)?)\s+quantity\s+(\d+)\s+(?:units?\s+)?(\w+)\s+rate\s+(\d+)\s+tax\s+(\d+\.?\d*)\s+(\d+\.?\d*)\s+(\d+\.?\d*)/i);
    if (match) {
        const hsn = match[1] ? match[1].replace(/\s+/g, '') : '';
        const itemName = match[2].trim();
        const quantity = parseInt(match[3]);
        const unit = match[4].toUpperCase();
        const rate = parseInt(match[5]);
        const cgst = parseFloat(match[6]);
        const sgst = parseFloat(match[7]);
        const igst = cgst + sgst; // IGST = CGST + SGST

        return {
            success: true,
            intent: "add_item",
            message: `Adding ${itemName} - HSN: ${hsn || 'N/A'}, Qty: ${quantity} ${unit}, Rate: ₹${rate}, Tax: ${cgst}% + ${sgst}% + ${igst}%`,
            entities: {
                item_description: itemName,
                quantity: quantity,
                amount: rate,
                unit: unit,
                hsn_code: hsn,
                cgst_percentage: cgst,
                sgst_percentage: sgst,
                igst_percentage: igst,
                tax: cgst + sgst + igst
            }
        };
    }

    // Pattern 1b: Simplified tax fallback - "add HSN 1413 item soap quantity 5 units kg rate 500 tax 99"
    // Handles when speech recognition combines numbers: "99" -> split to "9" and "9" for CGST and SGST
    match = normalized.match(/(?:add\s+)?(?:hs[nm]\s+([\d\s]+?)\s+)?items?\s+(\w+(?:\s+\w+)?)\s+quantity\s+(\d+)\s+(?:units?\s+)?(\w+)\s+rate\s+(\d+)\s+tax\s+(\d{2})/i);
    if (match) {
        const hsn = match[1] ? match[1].replace(/\s+/g, '') : '';
        const itemName = match[2].trim();
        const quantity = parseInt(match[3]);
        const unit = match[4].toUpperCase();
        const rate = parseInt(match[5]);
        const taxDigits = match[6]; // e.g., "99"
        // Split into two digits: first digit for CGST, second for SGST
        const cgst = parseInt(taxDigits[0]);
        const sgst = parseInt(taxDigits[1]);
        const igst = cgst + sgst; // IGST = CGST + SGST

        return {
            success: true,
            intent: "add_item",
            message: `Adding ${itemName} - HSN: ${hsn || 'N/A'}, Qty: ${quantity} ${unit}, Rate: ₹${rate}, Tax: ${cgst}% + ${sgst}% (from "${taxDigits}")`,
            entities: {
                item_description: itemName,
                quantity: quantity,
                amount: rate,
                unit: unit,
                hsn_code: hsn,
                cgst_percentage: cgst,
                sgst_percentage: sgst,
                igst_percentage: igst,
                tax: cgst + sgst + igst
            }
        };
    }

    // Pattern 2: Detailed tax - "HSN 1413 item soap quantity 5 units kg rate 500 cgst 9 sgst 9 igst 0"
    // Accepts: HSN/HSM, "item" or "items", "IGST" or "GST"
    match = normalized.match(/(?:hs[nm]\s+([\d\s]+?)\s+)?items?\s+(.+?)\s+quantity\s+(?:(\d+)|by|five|for|to)\s+(?:units?\s+)?(\w+)\s+rate\s+(\d+)(?:\s+cgst\s+(\d+\.?\d*))?(?:\s+sgst\s+(\d+\.?\d*))?(?:\s+(?:i?gst)\s+(\d+\.?\d*))?/i);
    if (match) {
        // Remove spaces from HSN code (handles "14 13" -> "1413")
        const hsn = match[1] ? match[1].replace(/\s+/g, '') : '';
        const itemName = match[2].trim();
        // If quantity is missing (said "by" instead of number), default to 1
        const quantity = match[3] ? parseInt(match[3]) : 1;
        const unit = match[4].toUpperCase();
        const rate = parseInt(match[5]);
        const cgst = match[6] ? parseFloat(match[6]) : 9;
        const sgst = cgst ? parseFloat(match[7]) : 9;
        const igst = cgst + sgst; // IGST = CGST + SGST (auto-calculated)

        return {
            success: true,
            intent: "add_item",
            message: `Adding ${itemName} - HSN: ${hsn || 'N/A'}, Qty: ${quantity} ${unit}, Rate: ₹${rate}, CGST: ${cgst}%, SGST: ${sgst}%, IGST: ${igst}%`,
            entities: {
                item_description: itemName,
                quantity: quantity,
                amount: rate,
                unit: unit,
                hsn_code: hsn,
                cgst_percentage: cgst,
                sgst_percentage: sgst,
                igst_percentage: igst,
                tax: cgst + sgst + igst
            }
        };
    }

    // Pattern: Add item - "add pen quantity 2 price 10"
    match = normalized.match(/add\s+(.+?)\s+quantity\s+(\d+)\s+(?:price|rate)\s+(\d+)/i);
    if (match) {
        return {
            success: true,
            intent: "add_item",
            message: `Adding ${match[1]} - Qty: ${match[2]}, Price: ₹${match[3]}`,
            entities: {
                item_description: match[1],
                quantity: parseInt(match[2]),
                amount: parseInt(match[3]),
                unit: "Nos",
                tax: 18
            }
        };
    }

    // Pattern: Add item - "add pen 2 nos at 10"
    match = normalized.match(/add\s+(.+?)\s+(\d+)\s+(?:nos|kg|liters?|pieces?)\s+(?:at|rate|price)\s+(\d+)/i);
    if (match) {
        return {
            success: true,
            intent: "add_item",
            message: `Adding ${match[1]} - Qty: ${match[2]}, Price: ₹${match[3]}`,
            entities: {
                item_description: match[1],
                quantity: parseInt(match[2]),
                amount: parseInt(match[3]),
                unit: "Nos",
                tax: 18
            }
        };
    }

    // Pattern: Add item - "add pen 10 rupees" (qty=1)
    match = normalized.match(/add\s+(.+?)\s+(\d+)\s+(?:rupees?|rs)/i);
    if (match) {
        return {
            success: true,
            intent: "add_item",
            message: `Adding ${match[1]} - Price: ₹${match[2]}`,
            entities: {
                item_description: match[1],
                quantity: 1,
                amount: parseInt(match[2]),
                unit: "Nos",
                tax: 18
            }
        };
    }

    // Pattern: Save invoice
    if (normalized.match(/save\s+invoice|save\s+this|finish\s+invoice|complete\s+invoice/i)) {
        return {
            success: true,
            intent: "save_invoice",
            message: "Saving invoice..."
        };
    }

    // Pattern: Calculate total
    if (normalized.match(/calculate\s+total|total\s+amount|show\s+total|what'?s?\s+(?:the\s+)?total/i)) {
        return {
            success: true,
            intent: "calculate_total",
            message: "Calculating total..."
        };
    }

    // Pattern: Create invoice - "create invoice for [client]" - WITH CLOUD DB LOOKUP
    match = normalized.match(/(?:create|new|make|start)\s+invoice\s+for\s+(.+)/i);
    if (match) {
        const clientName = match[1].trim();

        try {
            // Fetch clients via local proxy (avoids CORS)
            const response = await fetch("/api/proxy/clients", {
                method: "GET",
                headers: { "Content-Type": "application/json" }
            });

            if (response.ok) {
                const clients = await response.json();

                // Search for matching client (case-insensitive)
                const matchedClient = clients.find(c =>
                    c.name.toLowerCase().includes(clientName.toLowerCase())
                );

                if (matchedClient) {
                    return {
                        success: true,
                        intent: "create_invoice",
                        message: `Creating invoice for ${matchedClient.name}`,
                        client_id: matchedClient.id,
                        client_name: matchedClient.name
                    };
                } else {
                    // Try partial match
                    const partialMatches = clients.filter(c =>
                        c.name.toLowerCase().includes(clientName.toLowerCase().split(' ')[0])
                    );

                    if (partialMatches.length > 0) {
                        const names = partialMatches.map(c => c.name).join(", ");
                        return {
                            success: false,
                            intent: "create_invoice",
                            message: `Client '${clientName}' not found. Did you mean: ${names}?`,
                            suggestions: partialMatches.map(c => `Create invoice for ${c.name}`)
                        };
                    } else {
                        return {
                            success: false,
                            intent: "create_invoice",
                            message: `Client '${clientName}' not found in cloud database. Please check the name.`,
                            suggestions: ["Try saying the full client name", "Check client list first"]
                        };
                    }
                }
            } else {
                return {
                    success: false,
                    intent: "create_invoice",
                    message: "Could not connect to cloud database. Please try again.",
                    error: "Cloud API unavailable"
                };
            }
        } catch (error) {
            console.error("Cloud DB error:", error);
            return {
                success: false,
                intent: "create_invoice",
                message: "Error connecting to cloud database. Please check your internet connection.",
                error: error.message
            };
        }
    }

    // Pattern: Search client - WITH CLOUD DB LOOKUP
    match = normalized.match(/(?:find|search)\s+(?:client\s+)?(.+)/i);
    if (match) {
        const clientName = match[1].trim();

        try {
            const response = await fetch("/api/proxy/clients", {
                method: "GET",
                headers: { "Content-Type": "application/json" }
            });

            if (response.ok) {
                const clients = await response.json();

                const matches = clients.filter(c =>
                    c.name.toLowerCase().includes(clientName.toLowerCase())
                );

                if (matches.length === 1) {
                    const client = matches[0];
                    return {
                        success: true,
                        intent: "search_client",
                        message: `Found: ${client.name} - Email: ${client.email || 'N/A'}, Phone: ${client.phone || 'N/A'}`,
                        client: client
                    };
                } else if (matches.length > 1) {
                    const names = matches.map(c => c.name).join(", ");
                    return {
                        success: true,
                        intent: "search_client",
                        message: `Found ${matches.length} clients: ${names}`,
                        clients: matches
                    };
                } else {
                    return {
                        success: false,
                        intent: "search_client",
                        message: `No clients found matching '${clientName}' in cloud database`
                    };
                }
            }
        } catch (error) {
            console.error("Cloud DB error:", error);
            return {
                success: false,
                intent: "search_client",
                message: "Error searching cloud database",
                error: error.message
            };
        }
    }

    // Unknown command
    return {
        success: false,
        intent: "unknown",
        message: "I didn't understand that command. Try: 'Add pen quantity 2 price 10' or 'Save invoice'",
        suggestions: [
            "Add pen quantity 2 price 10",
            "Add notebook 5 nos at 50",
            "Calculate total",
            "Save invoice",
            "Create invoice for [client name]"
        ]
    };
}

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

                    // Set individual tax fields (CGST, SGST, IGST)
                    if (data.entities.cgst_percentage !== undefined) {
                        const cgstInput = row.querySelector('[name="cgst_percentage"]');
                        if (cgstInput) cgstInput.value = data.entities.cgst_percentage;
                    }

                    if (data.entities.sgst_percentage !== undefined) {
                        const sgstInput = row.querySelector('[name="sgst_percentage"]');
                        if (sgstInput) sgstInput.value = data.entities.sgst_percentage;
                    }

                    if (data.entities.igst_percentage !== undefined) {
                        const igstInput = row.querySelector('[name="igst_percentage"]');
                        if (igstInput) igstInput.value = data.entities.igst_percentage;
                    }

                    // Calculate item amount and update summary
                    if (typeof calculateItemAmount === "function") {
                        calculateItemAmount(row);
                    }
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
