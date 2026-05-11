(function () {
    const passwordInput = document.getElementById("login-password");
    const toggleButton = document.getElementById("toggle-password-visibility");
    const toggleIcon = document.getElementById("toggle-password-icon");

    if (!passwordInput || !toggleButton || !toggleIcon) {
        return;
    }

    toggleButton.addEventListener("click", function () {
        const showPassword = passwordInput.type === "password";
        passwordInput.type = showPassword ? "text" : "password";
        toggleIcon.textContent = showPassword ? "visibility_off" : "visibility";
    });
}());
