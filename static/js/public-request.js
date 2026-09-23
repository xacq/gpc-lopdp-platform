(() => {
    "use strict";

    const form = document.querySelector("[data-request-wizard]");
    if (!form) return;

    const panels = Array.from(form.querySelectorAll("[data-wizard-panel]"));
    const steps = Array.from(document.querySelectorAll("[data-wizard-steps] .request-stepper__item"));
    const representativeToggle = form.elements.namedItem("has_representative");
    const representativeFields = form.querySelector(".representative-fields");
    const representativeRequiredNames = [
        "representative_name",
        "representative_document_type",
        "representative_document_number",
    ];
    let currentStep = 1;

    form.noValidate = true;

    const control = (name) => form.elements.namedItem(name);

    function setRepresentativeState() {
        if (!representativeToggle || !representativeFields) return;
        const hasErrors = Boolean(representativeFields.querySelector(".is-invalid, .public-field__error"));
        const hasValues = representativeRequiredNames.some((name) => Boolean(control(name)?.value));
        const hasAuthorityDocument = Boolean(control("authority_document")?.files?.length);
        const representativeIntent = representativeToggle.checked || hasValues || hasAuthorityDocument;
        const visible = representativeIntent || hasErrors;
        representativeFields.hidden = !visible;
        representativeRequiredNames.forEach((name) => {
            const field = control(name);
            if (field) field.required = representativeIntent;
        });
    }

    function updateSummary() {
        const documentType = control("document_type");
        const right = control("right");
        const documentLabel = documentType?.selectedOptions?.[0]?.text || "";
        const documentNumber = control("document_number")?.value || "";
        const files = ["identity_document", "authority_document", "supporting_document"]
            .reduce((total, name) => total + (control(name)?.files?.length || 0), 0);
        const values = {
            full_name: control("full_name")?.value || "—",
            document: [documentLabel, documentNumber].filter(Boolean).join(" · ") || "—",
            email: control("email")?.value || "—",
            right: right?.selectedOptions?.[0]?.text || "—",
            representative: (
                representativeToggle?.checked || Boolean(control("representative_name")?.value)
            ) ? "Sí" : "No",
            attachments: String(files),
        };
        Object.entries(values).forEach(([key, value]) => {
            const target = form.querySelector(`[data-summary="${key}"]`);
            if (target) target.textContent = value;
        });
    }

    function showStep(step, focusHeading = true) {
        currentStep = Math.min(Math.max(step, 1), panels.length);
        panels.forEach((panel) => {
            panel.hidden = Number(panel.dataset.wizardPanel) !== currentStep;
        });
        steps.forEach((item, index) => {
            const number = index + 1;
            item.classList.toggle("request-stepper__item--active", number === currentStep);
            item.classList.toggle("request-stepper__item--complete", number < currentStep);
            if (number === currentStep) item.setAttribute("aria-current", "step");
            else item.removeAttribute("aria-current");
        });
        if (currentStep === panels.length) updateSummary();
        if (focusHeading) {
            const heading = panels[currentStep - 1]?.querySelector("h2");
            heading?.setAttribute("tabindex", "-1");
            heading?.focus({preventScroll: true});
            document.querySelector("[data-wizard-steps]")?.scrollIntoView({behavior: "smooth", block: "start"});
        }
    }

    function validatePanel(panel) {
        const fields = Array.from(panel.querySelectorAll("input, select, textarea"));
        for (const field of fields) {
            if (field.disabled || field.type === "hidden") continue;
            if (!field.checkValidity()) {
                field.reportValidity();
                field.focus();
                return false;
            }
        }
        return true;
    }

    form.addEventListener("click", (event) => {
        const next = event.target.closest("[data-wizard-next]");
        const back = event.target.closest("[data-wizard-back]");
        if (next) {
            const panel = panels[currentStep - 1];
            if (validatePanel(panel)) showStep(currentStep + 1);
        } else if (back) {
            showStep(currentStep - 1);
        }
    });

    form.addEventListener("submit", (event) => {
        for (let index = 0; index < panels.length; index += 1) {
            const invalidField = panels[index].querySelector(":invalid");
            if (invalidField) {
                event.preventDefault();
                showStep(index + 1, false);
                validatePanel(panels[index]);
                return;
            }
        }
    });

    representativeToggle?.addEventListener("change", setRepresentativeState);
    representativeFields?.addEventListener("input", setRepresentativeState);
    control("authority_document")?.addEventListener("change", setRepresentativeState);
    form.querySelectorAll("[data-file-picker] input[type=file]").forEach((input) => {
        input.addEventListener("change", () => {
            const name = input.closest("[data-file-picker]")?.querySelector("[data-file-picker-name]");
            if (name) name.textContent = input.files?.[0]?.name || "Ningún archivo seleccionado";
        });
    });
    setRepresentativeState();

    const firstError = form.querySelector(".is-invalid, .public-field__error");
    const errorPanel = firstError?.closest("[data-wizard-panel]");
    showStep(errorPanel ? Number(errorPanel.dataset.wizardPanel) : 1, false);
})();
