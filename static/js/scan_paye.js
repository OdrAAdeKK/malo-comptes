function openScanModal() {
    document.getElementById('scanModal').style.display = 'block';
}

function closeScanModal() {
    document.getElementById('scanModal').style.display = 'none';
}

function handleDrop(event) {
    event.preventDefault();
    const file = event.dataTransfer.files[0];
    if (file && file.type === "application/pdf") {
        uploadPDF(file);
    } else {
        alert("Veuillez déposer un fichier PDF.");
    }
}

function handleFileSelect(files) {
    const file = files[0];
    if (file && file.type === "application/pdf") {
        uploadPDF(file);
    } else {
        alert("Veuillez choisir un fichier PDF.");
    }
}

function formatDateFR(dateStr) {
    // Convertit une date ISO (aaaa-mm-jj) en jj/mm/aaaa
    const [year, month, day] = dateStr.split("-");
    return `${day}/${month}/${year}`;
}

function uploadPDF(file) {
    const formData = new FormData();
    formData.append("file", file);

    fetch("/upload_pdf", {
        method: "POST",
        body: formData
    })
    .then(res => {
        console.log("Réponse serveur:", res);
        return res.text();
    })
    .then(text => {
        console.log("Texte brut reçu:", text);
        try {
            const data = JSON.parse(text);
            if (data.success) {
                document.querySelector("#montant").value = data.montant || '';
                document.querySelector("#brut").value = data.brut || '';
                document.querySelector("#preciser").value = data.preciser || '';

                // Gestion de la date via Flatpickr si présent
                const dateInput = document.querySelector("#date");
                if (data.date) {
                    if (dateInput._flatpickr) {
                        dateInput._flatpickr.setDate(data.date); // ISO format accepté ici
                    } else {
                        dateInput.value = formatDateFR(data.date);
                    }
                }

                closeScanModal();
            } else {
                alert(data.message || "PDF non reconnu ou format incorrect.");
            }
        } catch (e) {
            alert("Réponse serveur invalide : " + text);
            console.error("Erreur JSON parse:", e);
        }
    })
    .catch(err => {
        alert("Erreur lors de l’envoi du fichier.");
        console.error(err);
    });
}
