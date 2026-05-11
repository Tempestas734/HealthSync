(function () {
    const printLink = document.getElementById("print-receipt-link");
    const printStatus = document.getElementById("print-status");
    const printPanel = document.getElementById("print-panel");

    if (!printLink) {
        return;
    }

    const csrfToken = document.querySelector("input[name='csrfmiddlewaretoken']");

    function setStatus(message, isError) {
        if (!printStatus) {
            return;
        }
        printStatus.textContent = message || "";
        printStatus.className = isError
            ? "mt-3 text-sm font-medium text-red-700"
            : "mt-3 text-sm font-medium text-emerald-700";
    }

    printLink.addEventListener("click", async function () {
        printLink.disabled = true;
        setStatus("Envoi du ticket a l'imprimante...", false);

        const payload = new URLSearchParams();
        payload.set("printer", "printer");

        try {
            const response = await fetch(printLink.dataset.url, {
                method: "POST",
                headers: {
                    "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                    "X-CSRFToken": csrfToken ? csrfToken.value : "",
                },
                body: payload.toString(),
                credentials: "same-origin",
            });
            const data = await response.json();
            if (!response.ok || !data.ok) {
                throw new Error(data.error || "Impression impossible.");
            }
            setStatus("Ticket imprime sur " + data.printer + ".", false);
        } catch (error) {
            setStatus(error.message || "Erreur d'impression.", true);
        } finally {
            printLink.disabled = false;
        }
    });

    if (printPanel) {
        window.setTimeout(function () {
            printPanel.classList.add("opacity-0");
            window.setTimeout(function () {
                printPanel.remove();
            }, 500);
        }, 60000);
    }
}());
