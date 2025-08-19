document.addEventListener("DOMContentLoaded", function () {
    const form = document.querySelector("form");
    if (!form) return;

    const montantField = document.getElementById("montant");
    const brutField = document.getElementById("brut");
    const motifField = document.getElementById("motif");
    const concertIdField = document.getElementById("concert_id");
    const concertField = document.getElementById("concert_field");

    function markInvalid(field) {
        field.style.border = "2px solid #cc0000";
        field.style.backgroundColor = "#ffecec";
    }

    function resetFieldStyle(field) {
        field.style.border = "";
        field.style.backgroundColor = "";
    }

    form.addEventListener("submit", function (e) {
        let valid = true;

        resetFieldStyle(montantField);
        resetFieldStyle(brutField);
        resetFieldStyle(concertField);

        const montant = montantField.value.trim();
        const brut = brutField.value.trim();
        const motif = motifField.value;
        const concertId = concertIdField.value;

        if (!montant) {
            e.preventDefault();
            alert("Veuillez indiquer un montant.");
            markInvalid(montantField);
            montantField.focus();
            valid = false;
            return;
        }

        if (motif === "Salaire" && !brut) {
            e.preventDefault();
            alert("Veuillez indiquer le montant brut pour une opération de type 'Salaire'.");
            markInvalid(brutField);
            brutField.focus();
            valid = false;
            return;
        }

        if (motif === "Frais" && !concertId) {
            e.preventDefault();
            alert("Veuillez sélectionner un concert lié pour une opération de type 'Frais'.");
            markInvalid(concertField);
            concertField.focus();
            valid = false;
            return;
        }

        return valid;
    });
});
