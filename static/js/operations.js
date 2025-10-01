// ===========================
// operations_bundle.js
// ===========================
// Regroupe toute la logique JS pour operations.html (et form_operations.html).
// Fichier commenté et clair, adapté aux débutants et à l'usage moderne.

// Utilisation du strict mode (plus sûr)
"use strict";

/* =========================
   1. Initialisation générale
   ========================= */
document.addEventListener("DOMContentLoaded", function () {
    // On prépare tous les composants JS au chargement de la page
    initMusicienMotifLogic();
    initConcertAutocomplete();
    initFormValidation();
    initScanPaye();
    initSuppressionOperation();
});

function initFlatpickr() {
    // Champ Date (toujours dispo)
    if (document.getElementById("date")) {
        flatpickr("#date", {
            dateFormat: "d/m/Y",
            locale: "fr",
            allowInput: true,
        });
    }
}
/* =======================================
   2. Logique Musicien / Motif / Mode
   ======================================= */
function initMusicienMotifLogic() {
  const quiSelect   = document.getElementById('musicien');
  const motifSelect = document.getElementById('motif');
  const brutField   = document.getElementById('brut');

  // Radios + hidden
  const creditRadio = document.getElementById('credit_radio');
  const debitRadio  = document.getElementById('debit_radio');
  const typeHidden  = document.getElementById('type_hidden');

  // Mode de paiement
  const modeRadios  = document.querySelectorAll('input[name="mode"]');

  if (!quiSelect || !motifSelect || !creditRadio || !debitRadio || !typeHidden) return;

  // ============= Règles de motifs autorisés
  const motifRules = {
    musicien: ["Salaire", "Frais", "Remboursement frais divers"],
    "ASSO7": ["Achat","Vente","Divers"],   // <-- ajouté "Divers"
    "CB ASSO7": ["Frais", "Recette concert"],
    "CAISSE ASSO7": ["Frais", "Recette concert"]
  };
  const isStructure = (val) => ["ASSO7", "CB ASSO7", "CAISSE ASSO7", "TRESO ASSO7"].includes(val);

  function allowedMotifsFor(benef) {
    return motifRules[benef] || motifRules.musicien;
  }

  // ============= Helpers
  function setType(value, lock) {
    if (value === 'credit') {
      creditRadio.checked = true;
      debitRadio.checked  = false;
    } else {
      debitRadio.checked  = true;
      creditRadio.checked = false;
    }
    creditRadio.disabled = !!lock;
    debitRadio.disabled  = !!lock;
    typeHidden.value     = value;
  }

  function unlockType() {
    creditRadio.disabled = false;
    debitRadio.disabled  = false;
  }

  function syncHiddenFromRadios() {
    typeHidden.value = creditRadio.checked ? 'credit' : (debitRadio.checked ? 'debit' : '');
  }

function filterMotifs(benef) {
  // benef = 'musicien' ou le nom exact: "ASSO7", "CB ASSO7", "CAISSE ASSO7"
  const allowed = motifRules[benef] || motifRules["musicien"];
  const current = (motifSelect.value || "").trim();

  // Reconstruit la liste (au lieu de cacher des options existantes)
  motifSelect.innerHTML = "";
  for (const label of allowed) {
    const opt = document.createElement("option");
    opt.value = label;
    opt.textContent = label;
    motifSelect.appendChild(opt);
  }

  // Conserve l’ancienne valeur si encore autorisée, sinon 1ère (ASSO7 -> "Achat")
  motifSelect.value = allowed.includes(current) ? current : allowed[0];
}


  function lockEspecesIfCaisse(benef) {
    const isCaisse = benef === "CAISSE ASSO7";
    modeRadios.forEach(r => {
      r.disabled = isCaisse;
      if (isCaisse) r.checked = (r.value === "Espèces");
    });
    if (!isCaisse) {
      // par défaut on remet "Compte" si dispo
      const compte = Array.from(modeRadios).find(r => r.value === "Compte");
      if (compte && !Array.from(modeRadios).some(r => r.checked)) compte.checked = true;
    }
  }

  function syncBrut(motif) {
    if (motif === "Salaire") {
      brutField.disabled = false;
      brutField.style.background = '';
    } else {
      brutField.disabled = true;
      brutField.value = '';
      brutField.style.background = '#f3f3f3';
    }
  }

// ============= UI principale
function updateFormFields() {
  const benef = (quiSelect.value || '').trim();

  // 1) Motifs autorisés selon benef (peut CHANGER la valeur sélectionnée)
  filterMotifs(isStructure(benef) ? benef : 'musicien');

  // ASSO7 : si, après filtrage, la valeur n'est pas dans la liste structure,
  // on force "Achat" par défaut.
  if (benef === 'ASSO7') {
    const allowedASSO7 = ['Achat', 'Vente', 'Divers'];
    const cur = (motifSelect.value || '').trim();
    if (!allowedASSO7.includes(cur)) motifSelect.value = 'Achat';
  }

  // 🔁 Relire la valeur APRES filtrage / éventuel forçage
  const motif = (motifSelect.value || '').trim();

  // 2) Spé CAISSE ASSO7
  lockEspecesIfCaisse(benef);

  // 3) Brut
  syncBrut(motif);

  // 4) Crédit/Débit selon motif + verrouillage

  // --- Règles STRUCTURES ---
  if (benef === "ASSO7") {
    if (motif === "Achat")  { setType('debit',  true);  return; }   // verrouillé
    if (motif === "Vente")  { setType('credit', true);  return; }   // verrouillé
    if (motif === "Divers") { unlockType(); syncHiddenFromRadios(); return; } // libre
  }
  if (benef === "CB ASSO7" || benef === "CAISSE ASSO7") {
    if (motif === "Frais")           { setType('debit',  true); return; }
    if (motif === "Recette concert") { setType('credit', true); return; }
  }

  // --- Règles MUSICIENS (inchangées) ---
  if (motif === "Recette concert")            { setType('credit', true); return; }
  if (motif === "Salaire")                    { setType('debit',  true); return; }
  if (motif === "Frais")                      { setType('credit', true); return; }
  if (motif === "Remboursement frais divers") { setType('debit',  true); return; }

  // Par défaut : libre
  unlockType();
  syncHiddenFromRadios();
}

// -- BIND & INIT (AJOUTER CE BLOC) --
quiSelect  .addEventListener('change', updateFormFields);
motifSelect.addEventListener('change', updateFormFields);
creditRadio.addEventListener('change', syncHiddenFromRadios);
debitRadio .addEventListener('change', syncHiddenFromRadios);

// Lancer une première fois pour filtrer selon le bénéficiaire courant
updateFormFields();

}

/* ===============================
   3. Autocomplete + Calendrier Flatpickr
   =============================== */
function initConcertAutocomplete() {
  const concertField       = document.getElementById("concert_field");       // champ visible "jj/mm/aaaa — lieu"
  const concertIdField     = document.getElementById("concert_id");          // hidden: id du concert
  const concertAutocomplete= document.getElementById("concert_autocomplete");// liste
  const calendarIcon       = document.getElementById("calendar_icon");
  const concertDatePicker  = document.getElementById("concert_date_picker"); // input pour flatpickr (caché)
  const motifSelect        = document.getElementById("motif");
  const dateField          = document.getElementById("date");

  // ⚠️ musicien: select en création OU hidden en édition
  const musicienInput = document.getElementById("musicien") || document.querySelector('input[name="musicien"]');

  if (!concertField || !concertIdField || !concertDatePicker || !motifSelect) return;

  // Motifs qui exigent un concert lié
  const motifsQuiActivent = ["Frais", "Recette concert", "Remboursement frais divers"];

  // ---- Données passées par le serveur ----
  const allConcerts = (window.concerts || []).map(c => {
    const [y, m, d] = c.date.split("-");
    return { ...c, dateFr: `${d}/${m}/${y}` }; // c.date = "YYYY-MM-DD"
  });
  const concertsById = new Map(allConcerts.map(c => [String(c.id), c]));

  // concertsParMusicien peut être: { "Prénom Nom": [id, id...] } ou { "Prénom Nom": [{id,date,lieu}...] }
  const CPM = window.concertsParMusicien || {};

  // ---- Helpers ----
  function currentMusicienName() {
    return (musicienInput?.value || "").trim();
  }
  function formatDate(iso) {
    const [y,m,d] = iso.split("-");
    return `${d}/${m}/${y}`;
  }
  function allowedConcertsFor(name) {
    const raw = CPM[name] || [];
    if (!Array.isArray(raw)) return [];
    // objets -> normalise; ids -> map vers allConcerts
    if (raw.length && typeof raw[0] === "object") {
      return raw.map(c => ({ ...c, dateFr: c.dateFr || formatDate(c.date) }));
    }
    return raw.map(id => concertsById.get(String(id))).filter(Boolean);
  }

  // --- Flatpickr sur la date générale (champ "Date") ---
  if (dateField && typeof flatpickr === "function") {
    if (!dateField._flatpickr) {
      flatpickr(dateField, { dateFormat: "d/m/Y", locale: "fr", allowInput: true });
    }
  }

  // --- Flatpickr sur l’input caché "concert_date_picker" (pour n’ouvrir que les dates permises) ---
  if (typeof flatpickr !== "function") {
    console.error("flatpickr non chargé");
    return;
  }
  if (!concertDatePicker._flatpickr) {
    flatpickr(concertDatePicker, {
      dateFormat: "Y-m-d",
      locale: flatpickr.l10ns.fr,
      enable: [],              // ⚠️ on activera dynamiquement
      clickOpens: true,
      allowInput: false,
      onChange(selectedDates, dateStr) {
        const list = currentAllowed();
        const hit = list.find(c => c.date === dateStr);
        if (hit) fillConcert(hit);
      }
    });
  }

  // Ouvre le calendrier via l’icône
  if (calendarIcon) {
    calendarIcon.addEventListener("click", () => concertDatePicker._flatpickr.open());
  }

  // État courant filtré (reconstruit via refresh)
  let concerts = [];

  // --- remplace cette fonction dans initConcertAutocomplete ---
  function currentAllowed() {
    const motif = (motifSelect.value || "").trim();
    if (!motifsQuiActivent.includes(motif)) return [];

    const nameRaw = currentMusicienName();
    const nameNorm = (nameRaw || "").trim().toLowerCase();

    // ✅ Exception : si "CB ASSO7" + motif "Frais" -> autoriser TOUS les concerts
    if (nameNorm === "cb asso7" && motif === "Frais") {
      return allConcerts.slice().sort((a, b) => a.date.localeCompare(b.date));
    }

    // Cas normal : ne proposer QUE les concerts du musicien
    return allowedConcertsFor(nameRaw).slice().sort((a, b) => a.date.localeCompare(b.date));
  }


  function setDateFieldFromConcert(c) {
    if (!dateField) return;
    if (dateField._flatpickr) {
      dateField._flatpickr.setDate(c.date, true, "Y-m-d"); // met JJ/MM/AAAA
    } else {
      dateField.value = formatDate(c.date);
    }
  }

  function fillConcert(c) {
    concertField.value = `${c.dateFr || formatDate(c.date)} — ${c.lieu || ""}`.trim();
    concertIdField.value = c.id;
    concertField.dataset.locked = "true";
    concertAutocomplete.style.display = "none";
    setDateFieldFromConcert(c);
  }

  function refreshConcertField() {
    concerts = currentAllowed();

    // (1) restreindre le calendrier
    concertDatePicker._flatpickr.set("enable", concerts.map(c => c.date));

    // (2) activer/désactiver le champ en fonction du motif
    const motif = (motifSelect.value || "").trim();
    if (motifsQuiActivent.includes(motif)) {
      concertField.disabled = false;
      concertField.style.backgroundColor = "";
      calendarIcon && (calendarIcon.style.pointerEvents = "", calendarIcon.style.opacity = "");
    } else {
      // reset si motif ne requiert pas un concert
      concertField.disabled = true;
      concertField.value = "";
      concertIdField.value = "";
      concertField.style.backgroundColor = "#e9e9e9";
      concertAutocomplete.style.display = "none";
      if (calendarIcon) { calendarIcon.style.pointerEvents = "none"; calendarIcon.style.opacity = "0.4"; }
    }

    // (3) si la valeur actuelle n’est plus autorisée, on vide
    if (concertIdField.value && !concerts.some(c => String(c.id) === String(concertIdField.value))) {
      concertIdField.value = "";
      if (motifsQuiActivent.includes(motif)) concertField.value = ""; // on laisse l’utilisateur re-choisir
    }
  }

  // Autocomplete “maison”
  let currentMatches = [];
  let currentIndex = -1;
  let selectByMouse = false;

  concertField.addEventListener("input", function () {
    if (concertField.disabled) return;
    if (concertField.dataset.locked === "true") return;

    const value = concertField.value.trim().toLowerCase();
    concertAutocomplete.innerHTML = "";
    concertIdField.value = "";
    concertField.dataset.locked = "";

    if (value.length < 1) {
      concertAutocomplete.style.display = "none";
      return;
    }

    // on filtre UNIQUEMENT dans les concerts autorisés
    currentMatches = concerts.filter(c => {
      const label = `${c.dateFr || formatDate(c.date)} — ${c.lieu || ""}`.toLowerCase();
      const words = label.split(/[\s—]+/);
      return words.some(w => w.startsWith(value));
    });
    currentIndex = -1;
    if (!currentMatches.length) {
      concertAutocomplete.style.display = "none";
      return;
    }
    currentMatches.forEach((c, i) => {
      const item = document.createElement("div");
      item.textContent = `${c.dateFr || formatDate(c.date)} — ${c.lieu || ""}`.trim();
      item.className = "autocomplete-item";
      item.tabIndex = -1;
      item.addEventListener("mousedown", () => { selectByMouse = true; fillConcert(c); });
      item.addEventListener("mouseenter", () => { currentIndex = i; updateHighlight(); });
      concertAutocomplete.appendChild(item);
    });
    concertAutocomplete.style.display = "block";
  });

  function updateHighlight() {
    const items = concertAutocomplete.querySelectorAll(".autocomplete-item");
    items.forEach((el, i) => { el.style.background = (i === currentIndex) ? "#eef" : "white"; });
  }

  concertField.addEventListener("keydown", function (e) {
    const items = concertAutocomplete.querySelectorAll(".autocomplete-item");
    if (!items.length) return;

    if (concertField.dataset.locked === "true" && !["Tab","ArrowUp","ArrowDown"].includes(e.key)) {
      e.preventDefault();
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault(); currentIndex = (currentIndex + 1) % items.length; updateHighlight();
    } else if (e.key === "ArrowUp") {
      e.preventDefault(); currentIndex = (currentIndex - 1 + items.length) % items.length; updateHighlight();
    } else if (e.key === "Tab" || e.key === "Enter") {
      if (currentIndex >= 0) { e.preventDefault(); fillConcert(currentMatches[currentIndex]); }
    } else if (e.key === "Escape") {
      concertAutocomplete.style.display = "none";
    }
  });

  concertField.addEventListener("blur", function () {
    setTimeout(() => {
      if (concertIdField.value || selectByMouse) {
        concertAutocomplete.style.display = "none";
        selectByMouse = false;
        return;
      }
      concertAutocomplete.style.display = "none";
      concertField.value = "";
      concertIdField.value = "";
    }, 120);
  });

  concertField.addEventListener("focus", function () {
    if (concertField.disabled) return;
    if (concertField.dataset.locked !== "true" && concertField.value.trim()) {
      concertField.dispatchEvent(new Event("input"));
    }
  });

  // Refiltrage quand le bénéficiaire OU le motif change
  if (musicienInput && musicienInput.tagName === "SELECT") {
    musicienInput.addEventListener("change", refreshConcertField);
  }
  // (mode édition = input hidden) : pas d’event nécessaire, la valeur ne change pas.
  motifSelect.addEventListener("change", refreshConcertField);

  // Init
  refreshConcertField();

  // Si un label est déjà présent (pré-remplissage) mais l’ID est vide, tente de le retrouver
  if (concertField.value.trim() && !concertIdField.value) {
    const match = allConcerts.find(c => `${c.dateFr} — ${c.lieu}`.trim() === concertField.value.trim());
    if (match) concertIdField.value = match.id;
  }
}




/* ===============================
   4. Validation du formulaire
   =============================== */
function initFormValidation() {
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

	  // NEW — synchroniser le champ caché avec les radios
	  const typeHidden  = document.getElementById("type_hidden");
	  const creditRadio = document.getElementById("credit_radio");
	  const debitRadio  = document.getElementById("debit_radio");
	  if (typeHidden && creditRadio && debitRadio) {
		if (debitRadio.checked)      typeHidden.value = "debit";
		else if (creditRadio.checked) typeHidden.value = "credit";
	  }

	  const montant   = montantField.value.trim();
	  const brut      = brutField.value.trim();
	  const motif     = motifField.value;
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

	  if ((motif === "Frais" || motif === "Remboursement frais divers") && !concertId) {
		e.preventDefault();
		alert("Veuillez sélectionner un concert lié pour ce type d’opération.");
		markInvalid(concertField);
		concertField.focus();
		valid = false;
		return;
	  }

	  return valid;
	});
}

/* ===============================
   5. Gestion du Scan PAYE (PDF)
   =============================== */
function initScanPaye() {
    // Bouton d'ouverture du modal
    window.openScanModal = function () {
        document.getElementById('scanModal').style.display = 'block';
    };

    window.closeScanModal = function () {
        document.getElementById('scanModal').style.display = 'none';
    };

    window.handleDrop = function (event) {
        event.preventDefault();
        const file = event.dataTransfer.files[0];
        if (file && file.type === "application/pdf") {
            uploadPDF(file);
        } else {
            alert("Veuillez déposer un fichier PDF.");
        }
    };

    window.handleFileSelect = function (files) {
        const file = files[0];
        if (file && file.type === "application/pdf") {
            uploadPDF(file);
        } else {
            alert("Veuillez choisir un fichier PDF.");
        }
    };

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
        .then(res => res.text())
        .then(text => {
            try {
                const data = JSON.parse(text);
                if (data.success) {
                    document.querySelector("#montant").value = data.montant || '';
                    document.querySelector("#brut").value = data.brut || '';
                    document.querySelector("#preciser").value = data.preciser || '';

                    // Gestion de la date via Flatpickr si présent
                    const dateInput = document.querySelector("#date");
				if (data.date) {
					const isoDate = data.date;
					const dateObj = new Date(isoDate);

					if (dateInput._flatpickr) {
						dateInput._flatpickr.setDate(dateObj, true); // true = triggerChange
					} else {
						const day = String(dateObj.getDate()).padStart(2, '0');
						const month = String(dateObj.getMonth() + 1).padStart(2, '0');
						const year = dateObj.getFullYear();
						dateInput.value = `${day}/${month}/${year}`;
					}
				}
                    window.closeScanModal();
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
}

/* ===============================
   6. Suppression d'opération
   =============================== */
function initSuppressionOperation() {
    // Pour les boutons de suppression (utilisé surtout dans les archives/à venir)
    const deleteButtons = document.querySelectorAll('.delete-operation-button');
    deleteButtons.forEach(button => {
        button.addEventListener('click', function(event) {
            event.preventDefault();
            const form = this.closest('form');
            const confirmation = confirm('Es-tu sûr de vouloir supprimer cette opération ?');
            if (confirmation) {
                fetch(form.action, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ id: form.dataset.id }) // Envoie l'ID de l'opération
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        location.reload(); // Recharge la page pour voir la suppression
                    } else {
                        alert('Erreur lors de la suppression de l\'opération');
                    }
                })
                .catch(() => {
                    alert('Erreur réseau, l\'opération n\'a pas pu être supprimée');
                });
            }
        });
    });
}

/* ===============================
   7. (Facultatif) Exports si tu veux en faire un module plus tard
   =============================== */
// export { initMusicienMotifLogic, initConcertAutocomplete, initFormValidation, initScanPaye, initSuppressionOperation };
