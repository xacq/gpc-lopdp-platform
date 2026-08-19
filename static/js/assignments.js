(() => {
    "use strict";

    const form = document.querySelector("[data-bulk-assignment]");
    if (!form) return;

    const container = form.closest(".admin-data-card");
    const selections = Array.from(container.querySelectorAll("[data-request-selection]"));
    const selectAll = container.querySelector("[data-select-all]");
    const assignee = form.querySelector("[name='assignee_id']");
    const submit = form.querySelector("button[type='submit']");
    const count = form.querySelector("[data-selection-count]");
    const feedback = form.querySelector("[data-assignment-feedback]");

    const selected = () => selections.filter((checkbox) => checkbox.checked);
    const update = () => {
        const selectedCount = selected().length;
        count.textContent = String(selectedCount);
        submit.disabled = selectedCount === 0 || !assignee.value;
        if (selectAll) {
            selectAll.checked = selections.length > 0 && selectedCount === selections.length;
            selectAll.indeterminate = selectedCount > 0 && selectedCount < selections.length;
        }
    };

    selections.forEach((checkbox) => checkbox.addEventListener("change", update));
    assignee.addEventListener("change", update);
    if (selectAll) {
        selectAll.addEventListener("change", () => {
            selections.forEach((checkbox) => { checkbox.checked = selectAll.checked; });
            update();
        });
    }

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const requestIds = selected().map((checkbox) => checkbox.value);
        if (!requestIds.length || !assignee.value) return;

        submit.disabled = true;
        feedback.className = "bulk-assignment__feedback";
        feedback.textContent = "Procesando asignación…";

        try {
            const response = await fetch(form.dataset.applyUrl, {
                method: "POST",
                credentials: "same-origin",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": form.querySelector("[name='csrfmiddlewaretoken']").value,
                },
                body: JSON.stringify({ request_ids: requestIds, assignee_id: assignee.value }),
            });
            const payload = await response.json();
            if (!response.ok) throw new Error(payload.error || "No fue posible completar la asignación.");
            feedback.classList.add("bulk-assignment__feedback--success");
            feedback.textContent = `${payload.assigned} expediente(s) asignado(s); ${payload.unchanged} sin cambios.`;
            window.setTimeout(() => window.location.reload(), 700);
        } catch (error) {
            feedback.classList.add("bulk-assignment__feedback--error");
            feedback.textContent = error.message || "No fue posible completar la asignación.";
            update();
        }
    });

    update();
})();
