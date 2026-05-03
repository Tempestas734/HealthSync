(function () {
    function appendBanner(message) {
        if (document.querySelector("[data-asset-diagnostic-banner]")) {
            return;
        }

        const banner = document.createElement("div");
        banner.setAttribute("data-asset-diagnostic-banner", "true");
        banner.style.position = "fixed";
        banner.style.top = "0";
        banner.style.left = "0";
        banner.style.right = "0";
        banner.style.zIndex = "9999";
        banner.style.padding = "10px 16px";
        banner.style.background = "#fff4e5";
        banner.style.borderBottom = "1px solid #f5c27a";
        banner.style.color = "#7a3e00";
        banner.style.fontFamily = "Inter, Arial, sans-serif";
        banner.style.fontSize = "14px";
        banner.style.fontWeight = "600";
        banner.style.textAlign = "center";
        banner.textContent = message;
        document.body.prepend(banner);
    }

    function checkTailwind() {
        if (typeof window.tailwind !== "undefined") {
            return;
        }

        appendBanner("Tailwind CDN n'a pas charge. Les couleurs et le layout peuvent etre incomplets.");
        console.error("Tailwind CDN failed to load. Check access to https://cdn.tailwindcss.com");
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", checkTailwind);
    } else {
        checkTailwind();
    }
})();
