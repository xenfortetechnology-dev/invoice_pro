function calculate() {

    let sub = parseFloat(ui_subtotal.value) || 0;
    let disPercent = parseFloat(ui_discount.value) || 0;   // Discount %
    let taxPercent = parseFloat(ui_tax.value) || 0;        // Tax %
    let ship = parseFloat(ui_shipping.value) || 0;
    let round = parseFloat(ui_rounding.value) || 0;

    // 🔹 Convert Discount % to Amount
    let discountAmount = (sub * disPercent) / 100;

    // 🔹 Taxable value after discount
    let taxableVal = sub - discountAmount;

    // 🔹 Convert Tax % to Amount
    let taxAmt = (taxableVal * taxPercent) / 100;

    // 🔹 Final total
    let total = taxableVal + taxAmt + ship + round;

    ui_total.value = total.toFixed(2);

    // ✅ COPY VALUES INTO HIDDEN FIELDS
    document.getElementById('subtotal').value      = sub.toFixed(2);
    document.getElementById('discount').value      = discountAmount.toFixed(2);  // store actual amount
    document.getElementById('taxable_value').value = taxableVal.toFixed(2);
    document.getElementById('cgst').value          = (taxAmt / 2).toFixed(2);
    document.getElementById('sgst').value          = (taxAmt / 2).toFixed(2);
    document.getElementById('igst').value          = 0;
    document.getElementById('shipping').value      = ship.toFixed(2);
    document.getElementById('rounding').value      = round.toFixed(2);
    document.getElementById('grand_total').value   = total.toFixed(2);
}

// function loadTerms(type) {
//     let terms = "";
// 
//     if (type === "standard") {
//         terms = `1. Quotation Validity: This quotation is valid for the selected validity period.
// 2. Payment Policy: 50% advance, balance payable upon delivery.
// 3. Tax Applicability: GST applicable as per government rules.
// 4. Cancellation Policy: Cancellation after confirmation may attract charges.
// 5. Refund Policy: No refund once project execution starts.
// 6. Intellectual Property Rights: All source code remains company property until full payment.
// 7. Confidentiality Clause: Client and company agree to maintain confidentiality.
// 8. Delay Responsibility: Client delay in approvals/content may affect delivery timelines.
// 9. Jurisdiction: Subject to Madurai jurisdiction.`;
//     }

//     else if (type === "corporate") {
//         terms = `1. Quotation Validity: Valid for approved corporate agreement period.
// 2. Payment Policy: Net 30 days billing cycle.
// 3. Tax Applicability: All applicable taxes will be charged.
// 4. Cancellation Policy: Written notice required for cancellation.
// 5. Refund Policy: Refund subject to management approval.
// 6. Intellectual Property Rights: Ownership transferred after full settlement.
// 7. Confidentiality Clause: NDA applicable.
// 8. Delay Responsibility: Timelines dependent on client approvals.
// 9. Jurisdiction: Chennai jurisdiction.`;
//     }

//     else if (type === "strict") {
//         terms = `1. Quotation Validity: Valid only for limited period.
// 2. Payment Policy: 100% advance payment required.
// 3. Tax Applicability: Tax mandatory.
// 4. Cancellation Policy: No cancellation allowed.
// 5. Refund Policy: No refunds under any circumstances.
// 6. Intellectual Property Rights: Ownership remains with company.
// 7. Confidentiality Clause: Strict confidentiality enforcement.
// 8. Delay Responsibility: Any delay voids warranty.
// 9. Jurisdiction: Bangalore jurisdiction.`;
//     }

//     document.getElementById("termsBox").value = terms.trim();
// }

// Event listeners
document.querySelectorAll(".calc").forEach(i => i.addEventListener("input", calculate));
quotation_date.addEventListener("change", calculateExpiry);
validity_days.addEventListener("change", calculateExpiry);

// ✅ IMPORTANT: recalc before submit so hidden fields are always up-to-date
document.querySelector("form").addEventListener("submit", function () {
    calculate();
});

// On load: only run calculateExpiry (to show expiry date from existing date+validity).
// Do NOT auto-run calculate() on load — it would overwrite the grand_total with 0
// for existing quotations whose subtotal/discount haven't been entered yet.
calculateExpiry();
