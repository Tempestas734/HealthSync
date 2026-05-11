(function () {
    const modal = document.getElementById("doctor-calendar-modal");
    const closeButton = document.getElementById("calendar-modal-close");
    const titleNode = document.getElementById("calendar-modal-title");
    const subtitleNode = document.getElementById("calendar-modal-subtitle");
    const avatarNode = document.getElementById("calendar-modal-avatar");
    const mainNode = document.getElementById("calendar-modal-main");
    const sideNode = document.getElementById("calendar-modal-side");
    const footerCloseButton = document.getElementById("calendar-modal-footer-close");
    const tabs = Array.from(document.querySelectorAll(".calendar-tab"));
    let activePayload = null;
    let activeTab = "week";
    let selectedMonthKey = null;
    let selectedDateIso = null;

    function parseIsoDate(isoValue) {
        const [year, month, day] = isoValue.split("-").map(Number);
        return new Date(year, month - 1, day);
    }

    function formatDate(dateValue) {
        return String(dateValue.getDate()).padStart(2, "0") + "/" +
            String(dateValue.getMonth() + 1).padStart(2, "0") + "/" +
            dateValue.getFullYear();
    }

    function toMinutes(timeValue) {
        const [hours, minutes] = timeValue.split(":").map(Number);
        return (hours * 60) + minutes;
    }

    function renderMonthView(payload) {
        const month = payload.months[selectedMonthKey];
        const weekdayHeaders = month.weekday_labels.map((label, index) =>
            '<div class="py-2 text-center text-[9px] font-bold uppercase tracking-[0.2em] ' +
            (index >= 5 ? "bg-slate-50 text-slate-400" : "text-slate-400") + " " +
            (index < 6 ? "border-r border-slate-100" : "") + '">' +
            label.slice(0, 3) + "</div>"
        ).join("");

        const dayCells = month.weeks.flat().map((day, index) => {
            const hasContent = day.is_blocked || day.is_available;
            const selectedOutline = day.iso === selectedDateIso ? "ring-2 ring-primary ring-offset-1" : "";
            const baseBackground = day.is_current_month
                ? (day.is_blocked
                    ? "bg-red-50/70"
                    : day.is_available
                        ? "bg-emerald-50/80"
                        : "bg-white")
                : "bg-slate-50/40";
            const textTone = day.is_current_month
                ? (day.is_blocked
                    ? "text-red-600"
                    : day.is_available
                        ? "text-emerald-700"
                        : "text-slate-700")
                : "text-slate-300";
            const marker = day.is_blocked
                ? '<div class="mt-2 h-1.5 w-full rounded-full ' +
                    (day.tone === "amber" ? "bg-amber-400" : day.tone === "blue" ? "bg-blue-400" : day.tone === "slate" ? "bg-slate-400" : "bg-red-400") +
                    '"></div>'
                : day.is_available
                    ? '<div class="mt-2 h-1.5 w-full rounded-full bg-emerald-500"></div>'
                    : "";

            return (
                '<button class="calendar-day-trigger flex h-14 flex-col items-start justify-start border-b border-slate-100 px-2 py-1.5 text-left transition-colors hover:bg-slate-50 sm:h-16 ' +
                selectedOutline + " " + baseBackground + " " + (day.is_current_month ? "" : "pointer-events-none") + " " +
                (index % 7 < 6 ? "border-r" : "") + '" data-day-iso="' + day.iso + '" ' + (day.is_current_month ? "" : "disabled") + ">" +
                '<span class="text-xs font-bold sm:text-sm ' + textTone + '">' + day.day_number + "</span>" +
                marker +
                "</button>"
            );
        }).join("");

        mainNode.innerHTML =
            '<div class="rounded-[2rem] border border-slate-100 bg-white shadow-sm">' +
                '<div class="flex items-center justify-between border-b border-slate-100 bg-surface-container-low/10 px-5 py-4">' +
                    '<h3 class="font-bold text-on-surface">' + month.label + "</h3>" +
                    '<div class="flex gap-2">' +
                        '<button class="calendar-month-nav rounded-full p-1 transition-colors hover:bg-white" data-direction="-1" type="button"><span class="material-symbols-outlined text-sm">chevron_left</span></button>' +
                        '<button class="calendar-month-nav rounded-full p-1 transition-colors hover:bg-white" data-direction="1" type="button"><span class="material-symbols-outlined text-sm">chevron_right</span></button>' +
                    "</div>" +
                "</div>" +
                '<div class="px-3 py-3 sm:px-4 sm:py-4">' +
                    '<div class="mb-2 text-[11px] font-semibold text-slate-500">Vert = disponible, rouge/orange = indisponible</div>' +
                    '<div class="grid grid-cols-7 overflow-hidden rounded-2xl border border-slate-100">' +
                        weekdayHeaders +
                        dayCells +
                    "</div>" +
                "</div>" +
            "</div>";
        sideNode.classList.add("hidden");

        mainNode.querySelectorAll(".calendar-day-trigger").forEach((button) => {
            button.addEventListener("click", function () {
                selectedDateIso = button.dataset.dayIso;
                activeTab = "week";
                renderActiveTab();
            });
        });

        mainNode.querySelectorAll(".calendar-month-nav").forEach((button) => {
            button.addEventListener("click", function () {
                const keys = Object.keys(payload.months);
                const currentIndex = keys.indexOf(selectedMonthKey);
                const nextIndex = currentIndex + Number(button.dataset.direction);
                if (keys[nextIndex]) {
                    selectedMonthKey = keys[nextIndex];
                    const nextMonth = payload.months[selectedMonthKey];
                    const firstCurrentMonthDay = nextMonth.weeks.flat().find((day) => day.is_current_month);
                    if (firstCurrentMonthDay) {
                        selectedDateIso = firstCurrentMonthDay.iso;
                    }
                    renderActiveTab();
                }
            });
        });
    }

    function renderWeekView(payload) {
        const selectedDate = parseIsoDate(selectedDateIso);
        const monday = new Date(selectedDate);
        monday.setDate(selectedDate.getDate() - ((selectedDate.getDay() + 6) % 7));
        const weekDays = [];
        const timeLabels = ["08:00", "10:00", "12:00", "14:00", "16:00", "18:00"];
        const plannerStart = 8 * 60;
        const plannerEnd = 18 * 60;
        const plannerMinutes = plannerEnd - plannerStart;

        for (let offset = 0; offset < 7; offset += 1) {
            const currentDate = new Date(monday);
            currentDate.setDate(monday.getDate() + offset);
            const iso = currentDate.getFullYear() + "-" +
                String(currentDate.getMonth() + 1).padStart(2, "0") + "-" +
                String(currentDate.getDate()).padStart(2, "0");
            const details = payload.day_details[iso] || { intervals: [], entries: [], is_available: false, is_blocked: false };
            weekDays.push({ iso, date: currentDate, details });
        }

        const weekHeader = weekDays.map((item, index) =>
            '<div class="flex h-14 flex-col items-center justify-center border-b border-slate-100 px-2 text-center ' +
            (index < 6 ? "border-r" : "") + " " + (index >= 5 ? "bg-slate-50" : "bg-surface-container-low/10") + '">' +
                '<span class="text-[10px] font-bold uppercase tracking-[0.24em] ' + (index >= 5 ? "text-slate-300" : "text-slate-400") + '">' + ((item.details.weekday_label || "").slice(0, 3)) + "</span>" +
                '<span class="mt-1 text-sm font-bold ' + (item.iso === selectedDateIso ? "text-primary" : "text-on-surface") + '">' + item.date.getDate() + "</span>" +
            "</div>"
        ).join("");

        const weekColumns = weekDays.map((item, index) => {
            const isWeekend = index >= 5;
            const intervalBlocks = (item.details.intervals || []).map((interval) => {
                const startMinutes = Math.max(toMinutes(interval.start), plannerStart);
                const endMinutes = Math.min(toMinutes(interval.end), plannerEnd);
                const top = ((startMinutes - plannerStart) / plannerMinutes) * 100;
                const height = Math.max(((endMinutes - startMinutes) / plannerMinutes) * 100, 8);
                return (
                    '<div class="absolute inset-x-1 rounded-lg border-l-4 border-primary bg-primary/10 px-2 py-1.5 text-[10px] font-bold leading-tight text-primary shadow-sm" style="top:' + top + "%; height:" + height + '%;">' +
                        "<div>Disponible</div>" +
                        '<div class="mt-1 text-[9px] font-semibold text-primary/70">' + interval.start + " - " + interval.end + "</div>" +
                    "</div>"
                );
            }).join("");

            const blockedBlocks = (item.details.entries || []).map((entry) => {
                const toneClass = entry.type === "Conge"
                    ? "border-orange-400 bg-orange-50/90 text-orange-700"
                    : entry.type === "Absence"
                        ? "border-red-400 bg-red-50/90 text-red-700"
                        : "border-slate-400 bg-slate-100/95 text-slate-700";
                return (
                    '<div class="absolute inset-0 flex items-center justify-center px-2">' +
                        '<div class="w-full rounded-lg border-l-4 ' + toneClass + ' px-2 py-2 text-center text-[10px] font-bold leading-tight shadow-sm">' +
                            "<div>" + entry.type + "</div>" +
                            '<div class="mt-1 text-[9px] font-semibold">' + entry.motif + "</div>" +
                        "</div>" +
                    "</div>"
                );
            }).join("");

            const hourLines = timeLabels.map((label, lineIndex) =>
                '<div class="absolute inset-x-0 border-t border-slate-200" style="top:' + ((lineIndex / (timeLabels.length - 1)) * 100) + '%"></div>'
            ).join("");

            return (
                '<div class="relative ' + (index < 6 ? "border-r border-slate-100" : "") + " " + (isWeekend ? "bg-slate-50/80" : "bg-white") + '">' +
                    '<div class="relative h-64">' +
                        hourLines +
                        intervalBlocks +
                        blockedBlocks +
                    "</div>" +
                "</div>"
            );
        }).join("");

        mainNode.innerHTML =
            '<div class="rounded-[2rem] border border-slate-100 bg-white shadow-sm">' +
                '<div class="flex items-center justify-between border-b border-slate-100 bg-surface-container-low/10 px-5 py-4">' +
                    '<h3 class="font-bold text-on-surface">Weekly Schedule</h3>' +
                    '<div class="flex gap-2">' +
                        '<button class="calendar-week-nav rounded-full p-1 transition-colors hover:bg-white" data-direction="-7" type="button"><span class="material-symbols-outlined text-sm">chevron_left</span></button>' +
                        '<button class="calendar-week-nav rounded-full p-1 transition-colors hover:bg-white" data-direction="7" type="button"><span class="material-symbols-outlined text-sm">chevron_right</span></button>' +
                    "</div>" +
                "</div>" +
                '<div class="p-3 sm:p-4">' +
                    '<h3 class="headline-font text-xl font-bold tracking-tight text-on-surface sm:text-2xl">Semaine du ' + formatDate(monday) + " au " + formatDate(weekDays[6].date) + "</h3>" +
                    '<p class="mt-1 text-xs text-on-surface-variant">Toutes les colonnes restent visibles sans scroll.</p>' +
                    '<div class="mt-4 overflow-hidden rounded-[28px] border border-slate-100 bg-white shadow-sm">' +
                        '<div class="grid grid-cols-8">' +
                            '<div class="bg-surface-container-low/30">' +
                                '<div class="h-14 border-b border-r border-slate-100"></div>' +
                                timeLabels.slice(0, -1).map((label) =>
                                    '<div class="flex h-[51.2px] items-center justify-center border-b border-r border-slate-100 text-[10px] font-bold text-slate-400">' + label + "</div>"
                                ).join("") +
                            "</div>" +
                            '<div class="col-span-7 grid grid-cols-7">' +
                                weekHeader +
                                weekColumns +
                            "</div>" +
                        "</div>" +
                    "</div>" +
                "</div>" +
            "</div>";
        sideNode.classList.add("hidden");

        mainNode.querySelectorAll(".calendar-week-nav").forEach((button) => {
            button.addEventListener("click", function () {
                const nextDate = new Date(selectedDate);
                nextDate.setDate(selectedDate.getDate() + Number(button.dataset.direction));
                selectedDateIso = nextDate.getFullYear() + "-" +
                    String(nextDate.getMonth() + 1).padStart(2, "0") + "-" +
                    String(nextDate.getDate()).padStart(2, "0");
                selectedMonthKey = nextDate.getFullYear() + "-" + String(nextDate.getMonth() + 1).padStart(2, "0");
                renderActiveTab();
            });
        });
    }

    function renderActiveTab() {
        if (!activePayload) {
            return;
        }

        tabs.forEach((tab) => {
            const isActive = tab.dataset.tab === activeTab;
            tab.className = isActive
                ? "calendar-tab rounded-full bg-white px-5 py-2 text-xs font-bold uppercase tracking-widest text-primary shadow-sm"
                : "calendar-tab rounded-full px-5 py-2 text-xs font-bold uppercase tracking-widest text-secondary transition-colors hover:bg-white/50";
        });

        if (activeTab === "month") {
            renderMonthView(activePayload);
        }
        if (activeTab === "week") {
            renderWeekView(activePayload);
        }
    }

    document.querySelectorAll(".calendar-modal-trigger").forEach((button) => {
        button.addEventListener("click", function () {
            const rawPayload = button.dataset.calendarPayload;
            if (!rawPayload) {
                return;
            }

            activePayload = JSON.parse(rawPayload);
            selectedMonthKey = activePayload.selected_month;
            selectedDateIso = activePayload.selected_date;
            activeTab = "week";
            titleNode.textContent = activePayload.doctor_name;
            subtitleNode.textContent = activePayload.specialite;
            if (avatarNode) {
                avatarNode.textContent = activePayload.avatar_initials || "DR";
            }
            renderActiveTab();
            modal.classList.remove("hidden");
            modal.classList.add("flex");
        });
    });

    tabs.forEach((tab) => {
        tab.addEventListener("click", function () {
            activeTab = tab.dataset.tab;
            renderActiveTab();
        });
    });

    function closeModal() {
        modal.classList.add("hidden");
        modal.classList.remove("flex");
    }

    if (closeButton) {
        closeButton.addEventListener("click", closeModal);
    }
    if (footerCloseButton) {
        footerCloseButton.addEventListener("click", closeModal);
    }
    if (modal) {
        modal.addEventListener("click", function (event) {
            if (event.target === modal) {
                closeModal();
            }
        });
    }
}());
