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

			// Valeur brute (envoyée au serveur) — format YYYY-MM-DD sans UTC
			const hidden = selectedDates.map(d => {
			  const y = d.getFullYear();
			  const m = String(d.getMonth() + 1).padStart(2, "0");
			  const day = String(d.getDate()).padStart(2, "0");
			  return `${y}-${m}-${day}`;
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
