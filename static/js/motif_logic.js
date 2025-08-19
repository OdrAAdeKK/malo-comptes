document.addEventListener("DOMContentLoaded", function () {
    const selectMusicien = document.getElementById("musicien");
    const selectMotif = document.getElementById("motif");
    const concertFieldWrapper = document.querySelector(".field-col.large");

    function updateMotifOptions() {
        const selectedOption = selectMusicien.options[selectMusicien.selectedIndex];
        const isStructure = selectedOption && selectedOption.classList.contains("structure-option");

        const optionSalaire = Array.from(selectMotif.options).find(opt => opt.value === "Salaire");
        const optionVente = Array.from(selectMotif.options).find(opt => opt.value === "Vente");

        if (optionSalaire) {
            optionSalaire.disabled = isStructure;
            if (isStructure && selectMotif.value === "Salaire") {
                selectMotif.value = "";
            }
        }

        if (optionVente) {
            optionVente.disabled = !isStructure;
            if (!isStructure && selectMotif.value === "Vente") {
                selectMotif.value = "";
            }
        }

        updateConcertFieldVisibility();
    }

    function updateConcertFieldVisibility() {
        const selectedMotif = selectMotif.value;
        const shouldShowConcert = selectedMotif === "Frais concert" || selectedMotif === "Recette concert";

        if (concertFieldWrapper) {
            concertFieldWrapper.style.display = shouldShowConcert ? "block" : "none";
        }
    }

    selectMusicien.addEventListener("change", updateMotifOptions);
    selectMotif.addEventListener("change", updateConcertFieldVisibility);

    updateMotifOptions(); // Appel initial
    updateConcertFieldVisibility(); // Appel initial
});
