(function () {
    const target = document.getElementById("patient-qrcode");
    if (!target || typeof QRCode === "undefined") {
        return;
    }

    const payload = JSON.stringify({
        patient_code: target.dataset.patientCode || "",
        barcode_value: target.dataset.barcodeValue || "",
        patient_name: target.dataset.patientName || "",
        date_of_birth: target.dataset.dateOfBirth || "",
        facility: target.dataset.facility || "",
    });

    new QRCode(target, {
        text: payload,
        width: 132,
        height: 132,
        colorDark: "#000000",
        colorLight: "#ffffff",
        correctLevel: QRCode.CorrectLevel.M,
    });

    window.setTimeout(function () {
        window.print();
    }, 300);
}());
