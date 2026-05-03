(function () {
    function normalizeCodePart(value, fallback) {
        const normalized = (value || "")
            .normalize("NFKD")
            .replace(/[\u0300-\u036f]/g, "")
            .toUpperCase()
            .replace(/[^A-Z]/g, "");

        const base = normalized || fallback;
        return base.slice(0, 3).padEnd(3, "X");
    }

    function updateFacilityCode() {
        const typeSelect = document.getElementById("id_type_etablissement");
        const citySelect = document.getElementById("id_ville");
        const codeInput = document.getElementById("id_code");
        if (!typeSelect || !citySelect || !codeInput) {
            return;
        }

        const selectedTypeLabel = typeSelect.options[typeSelect.selectedIndex]?.text || "";
        const selectedTypeValue = typeSelect.value || "";
        const selectedCity = citySelect.value || "";
        if (!selectedTypeValue || !selectedCity) {
            codeInput.value = "";
            return;
        }

        const typePart = normalizeCodePart(selectedTypeLabel, "TYP");
        const cityPart = normalizeCodePart(selectedCity, "VIL");
        const existingSuffixMatch = (codeInput.value || "").match(/-(\d{3})$/);
        const suffix = existingSuffixMatch ? existingSuffixMatch[1] : "001";

        codeInput.value = `${typePart}-${cityPart}-${suffix}`;
    }

    document.addEventListener("DOMContentLoaded", function () {
        const typeSelect = document.getElementById("id_type_etablissement");
        const citySelect = document.getElementById("id_ville");
        if (!typeSelect || !citySelect) {
            return;
        }

        typeSelect.addEventListener("change", updateFacilityCode);
        citySelect.addEventListener("change", updateFacilityCode);
        updateFacilityCode();
    });
})();
