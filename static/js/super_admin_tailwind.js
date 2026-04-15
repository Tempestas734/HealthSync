const superAdminTailwindConfig = {
    darkMode: "class",
    theme: {
        extend: {
            colors: {
                surface: "#f8f9fa",
                "surface-dim": "#d9dadb",
                "tertiary-fixed": "#ffdbcb",
                "primary-fixed-dim": "#a8c8ff",
                "on-secondary": "#ffffff",
                "primary-fixed": "#d6e3ff",
                "on-surface-variant": "#424752",
                "on-primary": "#ffffff",
                secondary: "#53606f",
                "surface-container-low": "#f3f4f5",
                outline: "#727783",
                "tertiary-fixed-dim": "#ffb691",
                "on-primary-fixed": "#001b3d",
                "on-error-container": "#93000a",
                "inverse-surface": "#2e3132",
                "on-tertiary-fixed": "#341100",
                "surface-container": "#edeeef",
                "on-primary-container": "#cadcff",
                "surface-variant": "#e1e3e4",
                "on-background": "#191c1d",
                "secondary-container": "#d6e4f7",
                tertiary: "#7b3200",
                "surface-container-high": "#e7e8e9",
                "surface-tint": "#005db5",
                "on-secondary-fixed-variant": "#3b4857",
                "on-tertiary-fixed-variant": "#783100",
                "inverse-primary": "#a8c8ff",
                "on-primary-fixed-variant": "#00468b",
                "secondary-fixed": "#d6e4f7",
                "on-tertiary": "#ffffff",
                "inverse-on-surface": "#f0f1f2",
                "tertiary-container": "#a04401",
                background: "#f8f9fa",
                "surface-container-highest": "#e1e3e4",
                "on-secondary-container": "#586676",
                "error-container": "#ffdad6",
                "primary-container": "#005fb8",
                "outline-variant": "#c2c6d4",
                "on-error": "#ffffff",
                primary: "#00488d",
                error: "#ba1a1a",
                "on-secondary-fixed": "#001d35",
                "surface-bright": "#f8f9fa",
                "on-surface": "#191c1d",
                "secondary-fixed-dim": "#bac8da",
                "surface-container-lowest": "#ffffff",
                "on-tertiary-container": "#ffd1bc"
            },
            fontFamily: {
                headline: ["Manrope", "sans-serif"],
                body: ["Inter", "sans-serif"],
                label: ["Inter", "sans-serif"]
            },
            borderRadius: {
                DEFAULT: "0.125rem",
                lg: "0.25rem",
                xl: "0.75rem",
                full: "9999px"
            }
        }
    }
};

if (typeof tailwind !== "undefined") {
    tailwind.config = superAdminTailwindConfig;
} else {
    window.tailwind = window.tailwind || {};
    window.tailwind.config = superAdminTailwindConfig;
}
