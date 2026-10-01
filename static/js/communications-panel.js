(function () {
    const outboundForm = document.querySelector('[data-composer-form="outbound"]');
    if (!outboundForm) return;

    const requestSelect = outboundForm.querySelector("[data-recipient-source]");
    const recipientInput = outboundForm.querySelector("[data-recipient-target]");
    if (!requestSelect || !recipientInput) return;

    function applyRecipientFromSelectedCase() {
        const selectedOption = requestSelect.selectedOptions[0];
        const recipientEmail = selectedOption
            ? selectedOption.dataset.recipientEmail || ""
            : "";

        recipientInput.value = recipientEmail;
        recipientInput.dataset.autofilledRecipient = recipientEmail;
    }

    requestSelect.addEventListener("change", applyRecipientFromSelectedCase);
    applyRecipientFromSelectedCase();
})();
