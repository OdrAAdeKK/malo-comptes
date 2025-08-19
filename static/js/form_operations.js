// static/js/form_operations.js

document.addEventListener('DOMContentLoaded', function () {
    function updateTypeOperation() {
        const motif = document.getElementById('motif').value;
        const creditRadio = document.getElementById('credit_radio');
        const debitRadio = document.getElementById('debit_radio');
        const hiddenType = document.getElementById('type_hidden');

        // Réinitialiser les boutons
        creditRadio.disabled = false;
        debitRadio.disabled = false;
        creditRadio.parentNode.style.opacity = 1;
        debitRadio.parentNode.style.opacity = 1;
        creditRadio.onclick = null;
        debitRadio.onclick = null;

        if (motif === 'Salaire') {
            debitRadio.checked = true;
            creditRadio.disabled = true;
            creditRadio.parentNode.style.opacity = 0.4;
            creditRadio.onclick = (e) => e.preventDefault();
            hiddenType.value = 'debit';
        } else if (motif === 'Frais') {
            creditRadio.checked = true;
            debitRadio.disabled = true;
            debitRadio.parentNode.style.opacity = 0.4;
            debitRadio.onclick = (e) => e.preventDefault();
            hiddenType.value = 'credit';
        } else if (motif === 'Recette concert') {
            creditRadio.checked = true;
            debitRadio.disabled = true;
            debitRadio.parentNode.style.opacity = 0.4;
            debitRadio.onclick = (e) => e.preventDefault();
            hiddenType.value = 'credit';
        } else {
            if (creditRadio.checked) {
                hiddenType.value = 'credit';
            } else if (debitRadio.checked) {
                hiddenType.value = 'debit';
            } else {
                hiddenType.value = '';
            }
        }
    }

    document.getElementById('motif').addEventListener('change', updateTypeOperation);
    document.getElementById('credit_radio').addEventListener('change', updateTypeOperation);
    document.getElementById('debit_radio').addEventListener('change', updateTypeOperation);
    updateTypeOperation(); // au chargement
});
