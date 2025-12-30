{% raw %}
<script>
    // ----- Check browser support -----
    
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!SpeechRecognition) {
        console.error("Speech Recognition இந்த browserல் support இல்லை");
    } else {
        const recognition = new SpeechRecognition();
        recognition.lang = "ta-IN";
        recognition.interimResults = false;
        recognition.maxAlternatives = 1;
        recognition.continuous = true; // Keeps listening continuously

        let isListening = false;
        let voiceModal;

        // ----- DOMContentLoaded -----
        document.addEventListener("DOMContentLoaded", () => {
            const voiceBtn = document.getElementById("voiceCreateBtn");
            const modalEl = document.getElementById("voiceCommandModal");
            if (modalEl) voiceModal = new bootstrap.Modal(modalEl);

            if (voiceBtn) {
                console.log("🎤 Voice button found:", voiceBtn);
                voiceBtn.addEventListener("click", () => {
                    if (!isListening) {
                        recognition.start();
                        isListening = true;
                        console.log("🎤 Voice recognition தொடங்கியது");
                        if (voiceModal) voiceModal.show();
                        document.body.style.overflow = "hidden"; // Disable scroll
                    } else {
                        recognition.stop();
                        closeModal();
                    }
                });
            }
        });

        // ----- Recognition result handler -----
        recognition.onresult = (event) => {
            const transcript = event.results[event.results.length - 1][0].transcript.toLowerCase().trim();
            console.log("நீங்கள் சொன்னது:", transcript);

            // ----- Stop command -----
            if (["நிறுத்து", "முடிந்தது", "ஆமாம்", "stop"].includes(transcript)) {
                recognition.stop();
                closeModal();
                console.log("🎤 Voice session முடிந்தது");
                return;
            }

            // ----- Client selection -----
            if (transcript.startsWith("கிளையன்ட் ")) {
                const name = transcript.replace("கிளையன்ட்", "").trim();
                const clientSelect = document.getElementById("client_id");
                if (clientSelect) {
                    for (let i = 0; i < clientSelect.options.length; i++) {
                        if (clientSelect.options[i].text.toLowerCase().includes(name)) {
                            clientSelect.value = clientSelect.options[i].value;
                            clientSelect.dispatchEvent(new Event('change'));
                            console.log(`✅ Client set to: ${clientSelect.options[i].text}`);
                            break;
                        }
                    }
                }
            }

            // ----- Add item -----
            if (transcript.includes("ஐடம் சேர்க்க") || transcript.includes("ஐட்டம் சேர்க்க")) {
                console.log("🎤 Voice trigger detected → ஐடம் சேர்க்க");
                let itemsText = transcript.replace("ஐடம் சேர்க்க", "").replace("ஐட்டம் சேர்க்க", "").trim();
                const items = itemsText.split(" மற்றும் ").map(t => t.trim()).filter(Boolean);
                console.log("🧾 Items parsed:", items);

                items.forEach(itemText => {
                    const parts = itemText.split(" அளவு ");
                    const description = parts[0]?.trim() || "பொருள்";
                    let quantity = 1, rate = 0;

                    if (parts[1]) {
                        const qParts = parts[1].split(" விலை ");
                        const qtyText = qParts[0]?.trim() || "1";
                        quantity = parseInt(qtyText) || tamilTextToNumber(qtyText) || 1;

                        if (qParts[1]) {
                            const rateText = qParts[1].trim();
                            let base = parseFloat(rateText.replace(/[^\d.]/g, "")) || tamilTextToNumber(rateText) || 0;

                            if (rateText.includes("ஆயிரம்")) base *= 1000;
                            else if (rateText.includes("நூறு")) base *= 100;
                            else if (rateText.includes("லட்சம்")) base *= 100000;

                            rate = base;
                        }
                    }
addItemRow();

setTimeout(() => {
    const row = getLastItemRow();
    if (!row) {
        console.error("❌ No row found after addItemRow()");
        return;
    }

    row.querySelector('[name="description"]').value = description;
    row.querySelector('[name="quantity"]').value = quantity;
    row.querySelector('[name="unit_price"]').value = rate;

    calculateItemAmount(row);
    updateInvoiceSummary();

    console.log("✅ Voice autofilled:", description, quantity, rate);
}, 50);
    
                });
            }

            // ----- Save invoice -----
            if (transcript === "சேமி") {
                document.getElementById("saveInvoiceBtn")?.click();
            }

            // ----- Preview invoice -----
            if (transcript === "பார்க்க") {
                document.getElementById("previewBtn")?.click();
            }
        };

        // ----- Recognition error handler -----
        recognition.onerror = (event) => {
            console.error("Recognition பிழை:", event.error);
            if (event.error === "no-speech" && isListening) {
                console.log("⏳ No speech detected — restarting recognition...");
                recognition.start();
            }
        };

        // ----- Recognition end handler -----
        recognition.onend = () => {
            console.log("🎤 Recognition முடிந்தது");
            closeModal();
            if (isListening) {
                console.log("🔁 Restarting recognition...");
                recognition.start();
            }
        };
        function getLastItemRow() {
    const rows = document.querySelectorAll('.item-row');
    return rows[rows.length - 1];
}
    function calculateItemAmountFromInputs(row) {
    const qtyInput = row.querySelector('[name="quantity"]');
    const rateInput = row.querySelector('[name="unit_price"]');
    const amountEl = row.querySelector('.item-amount');

    const qty = parseFloat(qtyInput?.value || 0);
    const rate = parseFloat(rateInput?.value || 0);

    const total = qty * rate;
    if (amountEl) {
        amountEl.textContent = `₹${total.toFixed(2)}`;
    }
}

        // ----- Helper: calculate row amounts -----
        function calculateItemAmounts() {
            document.querySelectorAll("tr.item-row").forEach(row => {
                const qtyField = row.querySelector("td:nth-child(3)");
                const rateField = row.querySelector("td:nth-child(5)");
                const amountField = row.querySelector("td:nth-child(7)");

                const qty = parseFloat(qtyField?.textContent || 0);
                const rate = parseFloat(rateField?.textContent || 0);

                if (amountField) {
                    const amount = qty * rate;
                    amountField.textContent = `₹${amount.toFixed(2)}`;
                }
            });

            if (typeof updateInvoiceSummary === "function") updateInvoiceSummary();
        }

        // ----- Helper: close modal -----
        function closeModal() {
            const modalEl = document.getElementById("voiceCommandModal");
            if (modalEl) {
                let modal = bootstrap.Modal.getInstance(modalEl);
                if (!modal) modal = new bootstrap.Modal(modalEl);
                modal.hide();
            }
            document.querySelectorAll('.modal-backdrop').forEach(el => el.remove());
            document.body.style.overflow = "auto";
            isListening = false;
        }

        // ----- Helper: Tamil text → number -----
        function tamilTextToNumber(text) {
            const map = {
                "பூஜ்யம்": 0, "ஒன்று": 1, "இரண்டு": 2, "மூன்று": 3,
                "நான்கு": 4, "ஐந்து": 5, "ஆறு": 6, "ஏழு": 7,
                "எட்டு": 8, "ஒன்பது": 9, "பத்து": 10, "ஆயிரம்": 1000
            };

            let num = 0;
            text.split(" ").forEach(word => {
                if (!isNaN(word)) num += parseInt(word);
                else if (map[word]) num += map[word];
            });

            return num || null;
        }
    }
</script>
{% endraw %}
