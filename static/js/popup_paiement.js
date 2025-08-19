document.querySelectorAll('.paye-checkbox').forEach(function(box) {
  box.addEventListener('change', function(e) {
    const concertId = this.dataset.id;

    if (this.checked) {
      // Si le pop-up de paiement est présent, l’utiliser
      if (document.getElementById('popupPaiement')) {
        ouvrirPopupPaiement(concertId);
        setTimeout(() => { this.checked = false; }, 10); // on décoche provisoirement
      } else {
        // Sinon, on valide automatiquement avec CB ASSO7
        fetch("/valider_paiement_concert", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ concert_id: concertId, compte: "CB ASSO7" })
        })
        .then(r => r.json())
        .then(data => {
          if (data.success) location.reload();
          else {
            alert("Erreur : " + data.message);
            this.checked = false;
          }
        });
      }
    } else {
      // Annulation du paiement (avec confirmation)
      annulerPaiementConcert(concertId);
    }
  });
});

let popupConcertId = null;

function ouvrirPopupPaiement(concertId) {
    popupConcertId = concertId;
    document.getElementById('concertIdPopup').value = concertId;

    // Récupère la recette_attendue depuis la checkbox cochée
    const checkbox = document.querySelector(`.paye-checkbox[data-id="${concertId}"]`);
    const recetteAttendue = checkbox ? checkbox.dataset.recetteAttendue : '';
    document.getElementById('recettePopup').value = recetteAttendue;

    document.getElementById('popupPaiement').showModal();
}

function fermerPopupPaiement() {
  document.getElementById('popupPaiement').close();
  popupConcertId = null;
}

// Bouton de validation du pop-up
document.getElementById('validerPaiement').onclick = function() {
    const compte = document.querySelector('input[name="compte"]:checked').value;
    const concertId = document.getElementById('concertIdPopup').value;
    const recette = document.getElementById('recettePopup').value;

    fetch("/valider_paiement_concert", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ concert_id: concertId, compte: compte, recette: recette })
    })
    .then(r => r.json())
    .then(data => {
        fermerPopupPaiement();
        if (data.success) location.reload();
        else alert("Erreur : " + data.message);
    });
};


function annulerPaiementConcert(concertId) {
  if (!confirm("Annuler la validation du paiement pour ce concert ?")) return;
  fetch("/annuler_paiement_concert", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ concert_id: concertId })
  })
    .then(r => r.json())
    .then(data => {
      if (data.success) location.reload();
      else alert("Erreur : " + data.message);
    });
}
