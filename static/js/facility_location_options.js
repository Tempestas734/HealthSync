(function () {
    const countryCities = {
        Maroc: [
            "Casablanca",
            "Rabat",
            "Marrakech",
            "Fes",
            "Tanger",
            "Agadir",
            "Meknes",
            "Oujda",
            "Kenitra",
            "Tetouan",
            "Safi",
            "El Jadida",
            "Beni Mellal",
            "Nador",
            "Taza",
            "Laayoune",
            "Dakhla",
        ],
        France: ["Paris", "Marseille", "Lyon", "Toulouse", "Nice", "Nantes", "Montpellier", "Strasbourg", "Bordeaux", "Lille"],
        Espagne: ["Madrid", "Barcelone", "Valence", "Seville", "Malaga", "Bilbao"],
        Algerie: ["Alger", "Oran", "Constantine", "Annaba", "Blida"],
        Tunisie: ["Tunis", "Sfax", "Sousse", "Kairouan", "Bizerte"],
    };

    function updateCityOptions(countrySelect, citySelect) {
        const selectedCountry = countrySelect.value;
        const currentCity = citySelect.dataset.currentValue || citySelect.value;
        const cities = countryCities[selectedCountry] || [];

        citySelect.innerHTML = "";

        const placeholder = document.createElement("option");
        placeholder.value = "";
        placeholder.textContent = "Choisir une ville";
        citySelect.appendChild(placeholder);

        cities.forEach(function (city) {
            const option = document.createElement("option");
            option.value = city;
            option.textContent = city;
            if (city === currentCity) {
                option.selected = true;
            }
            citySelect.appendChild(option);
        });
    }

    document.addEventListener("DOMContentLoaded", function () {
        const countrySelect = document.getElementById("id_pays");
        const citySelect = document.getElementById("id_ville");
        if (!countrySelect || !citySelect) {
            return;
        }

        citySelect.dataset.currentValue = citySelect.value;
        updateCityOptions(countrySelect, citySelect);

        countrySelect.addEventListener("change", function () {
            citySelect.dataset.currentValue = "";
            updateCityOptions(countrySelect, citySelect);
        });
    });
})();
