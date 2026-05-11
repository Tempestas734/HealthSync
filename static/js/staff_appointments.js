(function () {
    const doctorFilters = Array.from(document.querySelectorAll(".doctor-filter"));
    const appointmentCards = Array.from(document.querySelectorAll(".appointment-card"));
    const timeIndicator = document.getElementById("current-time-indicator");
    const calendarGrid = document.getElementById("appointments-calendar-grid");

    function applyDoctorFilters() {
        const activeDoctorIds = new Set(
            doctorFilters.filter((input) => input.checked).map((input) => input.dataset.doctorId)
        );

        appointmentCards.forEach((card) => {
            const isVisible = activeDoctorIds.has(card.dataset.doctorId);
            card.classList.toggle("hidden", !isVisible);
        });
    }

    function updateCurrentTimeIndicator() {
        if (!timeIndicator || !calendarGrid) {
            return;
        }

        const today = new Date();
        const weekStartRaw = calendarGrid.dataset.weekStart;
        if (weekStartRaw) {
            const [year, month, day] = weekStartRaw.split("-").map(Number);
            const renderedWeekStart = new Date(year, month - 1, day);
            const renderedWeekEnd = new Date(year, month - 1, day + 6);
            const todayDateOnly = new Date(today.getFullYear(), today.getMonth(), today.getDate());
            if (todayDateOnly < renderedWeekStart || todayDateOnly > renderedWeekEnd) {
                timeIndicator.classList.add("hidden");
                return;
            }
        }

        const currentMinutes = (today.getHours() * 60) + today.getMinutes();
        const startMinutes = 8 * 60;
        const endMinutes = 18 * 60;

        if (currentMinutes < startMinutes || currentMinutes > endMinutes) {
            timeIndicator.classList.add("hidden");
            return;
        }

        const topPercent = ((currentMinutes - startMinutes) / (endMinutes - startMinutes)) * 100;
        timeIndicator.style.top = topPercent + "%";
        timeIndicator.classList.remove("hidden");
    }

    doctorFilters.forEach((input) => {
        input.addEventListener("change", applyDoctorFilters);
    });

    applyDoctorFilters();
    updateCurrentTimeIndicator();
}());
