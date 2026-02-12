/* Main JavaScript for Invoice App */

function checkInvoiceFilter(btn) {
    const form = btn.closest('form');
    if (form) {
        form.submit();
    }
}

function handleInvoiceClear(event) {
    event.preventDefault();
    const form = event.target.closest('form');
    if (form) {
        // Reset all inputs
        const inputs = form.querySelectorAll('input, select');
        inputs.forEach(input => {
            if (input.type === 'text' || input.type === 'date') {
                input.value = '';
            } else if (input.tagName === 'SELECT') {
                input.selectedIndex = 0;
            }
        });
        // Submit the cleared form to reset the view
        form.submit();
    }
}

document.addEventListener('DOMContentLoaded', function() {
    // Feather icons initialization if needed
    if (typeof feather !== 'undefined') {
        feather.replace();
    }
});