function ouvrirPopupRecherche() {
    document.getElementById('popup-recherche').style.display = 'block';
}

function fermerPopupRecherche() {
    document.getElementById('popup-recherche').style.display = 'none';
}

function filtrerOperationsParMontant() {
    const montantStr = document.getElementById('montant').value.trim();
    const montant = parseFloat(montantStr.replace(',', '.'));

    const lignes = document.querySelectorAll(".archived-table tbody tr");
    let auMoinsUneVisible = false;

    lignes.forEach(ligne => {
        const montantCellText = ligne.children[5]?.innerText || "";
        const montantCell = parseFloat(montantCellText.replace(/\s/g, '').replace('€', '').replace(',', '.'));

        const afficher = !isNaN(montant) ? montant === montantCell : true;
        ligne.style.display = afficher ? "" : "none";
        if (afficher) auMoinsUneVisible = true;
    });

    // Affiche le bouton "Retour à la liste" si un filtre a été appliqué
    if (!isNaN(montant)) {
        document.getElementById('btn-retour-liste').style.display = 'inline-block';
    }

    fermerPopupRecherche();
    return false;
}

function retourListe() {
    const lignes = document.querySelectorAll(".archived-table tbody tr");
    lignes.forEach(ligne => ligne.style.display = "");

    document.getElementById('montant').value = "";
    document.getElementById('btn-retour-liste').style.display = 'none';
}

