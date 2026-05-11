(function () {
    const defaultIntervals = [
        { start: "08:00", end: "12:00" },
        { start: "14:00", end: "18:00" },
    ];

    function applyDefaults(dayCode) {
        defaultIntervals.forEach((interval, index) => {
            const slot = index + 1;
            const startInput = document.querySelector('input[name="' + dayCode + '_start_' + slot + '"]');
            const endInput = document.querySelector('input[name="' + dayCode + '_end_' + slot + '"]');
            if (startInput && !startInput.value) {
                startInput.value = interval.start;
            }
            if (endInput && !endInput.value) {
                endInput.value = interval.end;
            }
        });
    }

    document.querySelectorAll(".schedule-day-toggle").forEach((checkbox) => {
        const dayCode = checkbox.dataset.dayCode;
        if (checkbox.checked) {
            applyDefaults(dayCode);
        }
        checkbox.addEventListener("change", function () {
            if (checkbox.checked) {
                applyDefaults(dayCode);
            }
        });
    });
}());
