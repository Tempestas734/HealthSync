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
        const postalCodeInput = container.dataset.postalCodeInput
            ? document.getElementById(container.dataset.postalCodeInput)
            : null;
        if (!latitudeInput || !longitudeInput) {
            return;
        }

        if (typeof L === "undefined") {
            const warning = document.createElement("div");
            warning.className = "mt-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-800";
            warning.textContent = "Leaflet n'a pas charge. Verifie la connexion a unpkg.com ou charge Leaflet en local.";
            container.replaceChildren(warning);
            return;
        }

        const savedLat = parseNumber(latitudeInput.value) ?? parseNumber(container.dataset.initialLat);
        const savedLng = parseNumber(longitudeInput.value) ?? parseNumber(container.dataset.initialLng);
        const hasInitialCoordinates = savedLat !== null && savedLng !== null;
        const initialLat = savedLat ?? 33.5731;
        const initialLng = savedLng ?? -7.5898;
        const interactive = container.dataset.interactive === "true";

        const map = L.map(container, {
            scrollWheelZoom: interactive,
            dragging: true,
            tap: interactive,
        }).setView([initialLat, initialLng], hasInitialCoordinates ? 13 : 5);

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

        let marker = null;

        function ensureMarker(latlng) {
            if (!marker) {
                marker = L.marker([latlng.lat, latlng.lng], {
                    draggable: interactive,
                }).addTo(map);

                if (interactive) {
                    marker.on("dragend", function () {
                        moveMarker(marker.getLatLng());
                    });
                }
                return marker;
            }

            marker.setLatLng(latlng);
            return marker;
        }

        function syncInputs(latlng) {
            latitudeInput.value = latlng.lat.toFixed(6);
            longitudeInput.value = latlng.lng.toFixed(6);
        }

        function moveMarker(latlng) {
            ensureMarker(latlng);
            map.panTo(latlng);
            syncInputs(latlng);
        }

        function buildAddressQuery() {
            const parts = [
                addressInput ? addressInput.value.trim() : "",
                cityInput ? cityInput.value.trim() : "",
                countryInput ? countryInput.value.trim() : "",
                postalCodeInput ? postalCodeInput.value.trim() : "",
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

        if (hasInitialCoordinates) {
            ensureMarker({ lat: initialLat, lng: initialLng });
        }

        if (interactive) {
            map.on("click", function (event) {
                moveMarker(event.latlng);
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
        }

        setTimeout(function () {
            map.invalidateSize();
        }, 0);
    }

    document.addEventListener("DOMContentLoaded", function () {
        document.querySelectorAll("[data-facility-map]").forEach(bindFacilityMap);
    });
})();
