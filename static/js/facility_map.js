(function () {
    function parseNumber(value) {
        if (value === undefined || value === null || value === "") {
            return null;
        }
        const parsed = Number(value);
        return Number.isFinite(parsed) ? parsed : null;
    }

    function debounce(fn, delay) {
        let timeoutId = null;
        return function () {
            const args = arguments;
            clearTimeout(timeoutId);
            timeoutId = setTimeout(function () {
                fn.apply(null, args);
            }, delay);
        };
    }

    function bindFacilityMap(container) {
        const latitudeInput = document.getElementById(container.dataset.latitudeInput);
        const longitudeInput = document.getElementById(container.dataset.longitudeInput);
        const addressInput = document.getElementById(container.dataset.addressInput);
        const cityInput = document.getElementById(container.dataset.cityInput);
        const countryInput = document.getElementById(container.dataset.countryInput);
        const postalCodeInput = document.getElementById(container.dataset.postalCodeInput);
        if (!latitudeInput || !longitudeInput || typeof L === "undefined") {
            return;
        }

        const initialLat = parseNumber(latitudeInput.value) ?? parseNumber(container.dataset.initialLat) ?? 33.5731;
        const initialLng = parseNumber(longitudeInput.value) ?? parseNumber(container.dataset.initialLng) ?? -7.5898;
        const interactive = container.dataset.interactive === "true";

        const map = L.map(container, {
            scrollWheelZoom: interactive,
            dragging: true,
            tap: interactive,
        }).setView([initialLat, initialLng], parseNumber(latitudeInput.value) !== null && parseNumber(longitudeInput.value) !== null ? 13 : 5);

        const tileLayer = L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
            attribution: "&copy; OpenStreetMap contributors &copy; CARTO",
            maxZoom: 19,
            subdomains: "abcd",
        }).addTo(map);

        let tileErrorShown = false;
        tileLayer.on("tileerror", function () {
            if (tileErrorShown) {
                return;
            }
            tileErrorShown = true;

            const warning = document.createElement("div");
            warning.className = "mt-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-800";
            warning.textContent = "Le fond de carte est bloqué par le fournisseur. Tu peux quand même saisir latitude et longitude manuellement.";
            container.insertAdjacentElement("afterend", warning);
        });

        const marker = L.marker([initialLat, initialLng], {
            draggable: interactive,
        }).addTo(map);

        function syncInputs(latlng) {
            latitudeInput.value = latlng.lat.toFixed(6);
            longitudeInput.value = latlng.lng.toFixed(6);
        }

        function moveMarker(latlng) {
            marker.setLatLng(latlng);
            map.panTo(latlng);
            syncInputs(latlng);
        }

        function buildAddressQuery() {
            const parts = [
                addressInput ? addressInput.value.trim() : "",
                postalCodeInput ? postalCodeInput.value.trim() : "",
                cityInput ? cityInput.value.trim() : "",
                countryInput ? countryInput.value.trim() : "",
            ].filter(Boolean);

            if (parts.length < 2) {
                return null;
            }
            return parts.join(", ");
        }

        async function geocodeAddress() {
            const query = buildAddressQuery();
            if (!query) {
                return;
            }

            try {
                const response = await fetch(
                    "https://nominatim.openstreetmap.org/search?" +
                        new URLSearchParams({
                            q: query,
                            format: "jsonv2",
                            limit: "1",
                        }),
                    {
                        headers: {
                            Accept: "application/json",
                        },
                    }
                );

                if (!response.ok) {
                    return;
                }

                const results = await response.json();
                if (!Array.isArray(results) || results.length === 0) {
                    return;
                }

                const best = results[0];
                const lat = parseNumber(best.lat);
                const lng = parseNumber(best.lon);
                if (lat === null || lng === null) {
                    return;
                }

                moveMarker({ lat: lat, lng: lng });
                map.setZoom(14);
            } catch (error) {
                // Keep the form usable even if geocoding fails.
            }
        }

        const debouncedGeocode = debounce(geocodeAddress, 700);

        if (interactive) {
            map.on("click", function (event) {
                moveMarker(event.latlng);
            });

            marker.on("dragend", function () {
                moveMarker(marker.getLatLng());
            });

            [latitudeInput, longitudeInput].forEach(function (input) {
                input.addEventListener("change", function () {
                    const lat = parseNumber(latitudeInput.value);
                    const lng = parseNumber(longitudeInput.value);
                    if (lat === null || lng === null) {
                        return;
                    }
                    moveMarker({ lat: lat, lng: lng });
                });
            });

            [addressInput, cityInput, countryInput, postalCodeInput].forEach(function (input) {
                if (!input) {
                    return;
                }
                input.addEventListener("input", debouncedGeocode);
                input.addEventListener("change", geocodeAddress);
            });

            syncInputs(marker.getLatLng());
        }
    }

    document.addEventListener("DOMContentLoaded", function () {
        document.querySelectorAll("[data-facility-map]").forEach(bindFacilityMap);
    });
})();
