document.addEventListener("DOMContentLoaded", function () {
    flatpickr("#flatpickr_trigger", {
        mode: "multiple",
        dateFormat: "d/m/Y",
        locale: "fr",
        onChange: function (selectedDates, dateStr) {
            // Tri des dates
            selectedDates.sort((a, b) => a - b);

            // Nombre de cachets
            const nb = selectedDates.length;
            document.getElementById("nombre_cachets").value = nb;

            // Mise à jour du montant total
            updateMontantTotal();

            // Affichage des dates avec retour à la ligne
            const display = selectedDates.map(d => d.toLocaleDateString("fr-FR")).join(",\n");
            document.getElementById("dates_display").value = display;

            // Valeur brute (envoyée au serveur)
            const hidden = selectedDates.map(d => {
			  const local = new Date(d.getTime() - d.getTimezoneOffset() * 60000);
			  return local.toISOString().split('T')[0];
			}).join(",");
            document.getElementById("dates_hidden").value = hidden;
        }
    });

    function updateMontantTotal() {
        const montant = parseFloat(document.getElementById("montant").value.replace(",", ".")) || 0;
        const nb = parseInt(document.getElementById("nombre_cachets").value) || 0;
        const total = (montant * nb).toFixed(2).replace(".", ",");
        document.getElementById("montant_total").value = total + " €";
    }

    document.getElementById("montant").addEventListener("input", updateMontantTotal);

    document.getElementById("dates_display").addEventListener("click", function () {
        document.getElementById("flatpickr_trigger")._flatpickr.open();
    });
});
