document.addEventListener('DOMContentLoaded', function () {
    const quiSelect = document.getElementById('musicien');
    const motifSelect = document.getElementById('motif');
    const creditRadio = document.getElementById('credit_radio');
    const debitRadio = document.getElementById('debit_radio');
    const modeRadios = document.querySelectorAll('input[name="mode"]');

    function updateFormFields() {
        const selectedBenef = quiSelect ? quiSelect.value.trim() : "";
        const selectedMotif = motifSelect ? motifSelect.value.trim() : "";

        // Gérer le champ "Motif" selon la logique métier
        if (motifSelect) {
            for (const option of motifSelect.options) {
                const val = option.value;
                let disable = false;

                if (selectedBenef === "TRESO ASSO7") {
                    disable = true;
                } else if (!["ASSO7", "CB ASSO7", "CAISSE ASSO7", "TRESO ASSO7"].includes(selectedBenef)) {
                    if (val === "Vente" || val === "Recette concert") disable = true;
                } else if (selectedBenef === "ASSO7") {
                    if (val === "Salaire" || val === "Recette concert") disable = true;
                } else if (selectedBenef === "CB ASSO7" || selectedBenef === "CAISSE ASSO7") {
                    if (val === "Salaire" || val === "Vente") disable = true;
                }

                option.disabled = disable;
                if (disable && motifSelect.value === val) motifSelect.value = "";
            }
        }

        // Forcer certains comportements pour CAISSE ASSO7
        const isCaisse = selectedBenef === "CAISSE ASSO7";
        if (debitRadio) debitRadio.disabled = isCaisse;
        if (creditRadio && isCaisse) creditRadio.checked = true;

        for (const radio of modeRadios) {
            radio.disabled = isCaisse;
            if (isCaisse && radio.value === "Espèces") {
                radio.checked = true;
            }
        }

        // Ajuster le type d'opération selon le motif sélectionné
        if (selectedMotif === "Vente") {
            creditRadio.checked = true;
            creditRadio.disabled = false;
            debitRadio.disabled = false;
        } else if (selectedMotif === "Recette concert") {
            creditRadio.checked = true;
            creditRadio.disabled = true;
            debitRadio.disabled = true;
        } else {
            creditRadio.disabled = false;
            debitRadio.disabled = false;
        }
    }

    if (quiSelect) {
        quiSelect.addEventListener('change', updateFormFields);

        // Réordonner les options avec couleurs et placement corrects
        const specialOrder = ["ASSO7", "CB ASSO7", "CAISSE ASSO7", "TRESO ASSO7"];
        const options = Array.from(quiSelect.options).filter(opt => opt.value !== "");
        const normalOptions = options.filter(opt => !specialOrder.includes(opt.textContent.trim()));
        const specialOptions = specialOrder.map(name => {
            const opt = options.find(o => o.textContent.trim() === name);
            if (opt) {
                opt.style.fontWeight = 'bold';
                if (name === "ASSO7") opt.style.color = 'black';
                if (name === "CB ASSO7") opt.style.color = 'purple';
                if (name === "CAISSE ASSO7") opt.style.color = 'green';
                if (name === "TRESO ASSO7") opt.style.color = 'blue';
            }
            return opt;
        }).filter(Boolean);

        const defaultOption = document.createElement('option');
        defaultOption.value = '';
        defaultOption.textContent = '-- Sélectionner --';
        const separator = document.createElement('option');
        separator.disabled = true;
        separator.textContent = '──────────';

        quiSelect.innerHTML = '';
        quiSelect.appendChild(defaultOption);
        normalOptions.forEach(opt => quiSelect.appendChild(opt));
        quiSelect.appendChild(separator);
        specialOptions.forEach(opt => quiSelect.appendChild(opt));

        updateFormFields();
    }

    if (motifSelect) {
        motifSelect.addEventListener('change', updateFormFields);
    }
});