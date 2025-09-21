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
    "ASSO7": ["Achat", "Vente"],
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
    const allowed = allowedMotifsFor(benef);
    Array.from(motifSelect.options).forEach(opt => {
      const ok = allowed.includes(opt.value);
      opt.disabled = !ok;
      opt.hidden   = !ok;
    });
    if (!allowed.includes(motifSelect.value)) {
      motifSelect.value = allowed[0];
    }
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
    const motif = (motifSelect.value || '').trim();

    // 1) Motifs autorisés selon benef
    filterMotifs(isStructure(benef) ? benef : 'musicien');

    // 2) Spé CAISSE ASSO7
    lockEspecesIfCaisse(benef);

    // 3) Brut
    syncBrut(motif);

    // 4) Crédit/Débit selon motif + verrouillage
    if (motif === "Vente") {
      setType('credit', false);            // libre, mais on oriente
    } else if (motif === "Recette concert") {
      setType('credit', true);             // imposé
    } else if (motif === "Salaire") {
      setType('debit', true);              // imposé
    } else if (motif === "Frais") {
      if (benef === "CB ASSO7" || benef === "CAISSE ASSO7") {
        setType('debit', true);            // frais d'une structure = débit
      } else {
        setType('credit', true);           // frais d'un musicien = crédit
      }
    } else if (motif === "Remboursement frais divers") {
      setType('debit', true);              // toujours débit
    } else {
      unlockType();
      syncHiddenFromRadios();
    }
  }

  // Listeners
  quiSelect  .addEventListener('change', updateFormFields);
  motifSelect.addEventListener('change', updateFormFields);
  creditRadio.addEventListener('change', syncHiddenFromRadios);
  debitRadio .addEventListener('change', syncHiddenFromRadios);

  // Init
  updateFormFields();
}



/* ===============================
   3. Autocomplete + Calendrier Flatpickr
   =============================== */

function initConcertAutocomplete() {
  const concertField = document.getElementById("concert_field");
  const concertIdField = document.getElementById("concert_id");
  const concertAutocomplete = document.getElementById("concert_autocomplete");
  const calendarIcon = document.getElementById("calendar_icon");
  const concertDatePicker = document.getElementById("concert_date_picker");
  const musicienSelect = document.getElementById("musicien");
  const motifSelect = document.getElementById("motif");
  const dateField = document.getElementById("date");



  // ✅ une seule déclaration ici
  const motifsQuiActivent = ["Frais", "Recette concert", "Remboursement frais divers"];


    // --- (Nouveau) Flatpickr sur champ date principal, en français ---
    if (dateField) {
        flatpickr(dateField, {
            dateFormat: "d/m/Y",
            locale: "fr",
            allowInput: true
        });
    }

    // Formatage initial des concerts
    const allConcerts = (window.concerts || []).map(c => {
        const [y, m, d] = c.date.split("-");
        return { ...c, dateFr: `${d}/${m}/${y}` };
    });

    let concerts = allConcerts.slice();
    let currentMatches = [];
    let currentIndex = -1;
    let selectByMouse = false;

    function formatDate(isoDate) {
        const [year, month, day] = isoDate.split("-");
        return `${day}/${month}/${year}`;
    }

    // --- Filtres dynamiques (motif/musicien) ---
	  function refreshConcertField() {
		const motif = motifSelect.value;
		const musicien = musicienSelect.value;

		if (
		  motifsQuiActivent.includes(motif) &&
		  window.concertsParMusicien &&
		  window.concertsParMusicien[musicien]
		) {
		  concerts = window.concertsParMusicien[musicien].map(c => ({
			...c,
			dateFr: formatDate(c.date)
		  }));
		} else {
		  concerts = allConcerts.slice();
		}

		// ✅ guard flatpickr
		if (concertDatePicker && concertDatePicker._flatpickr) {
		  concertDatePicker._flatpickr.set('enable', concerts.map(c => c.date));
		}

		if (motifsQuiActivent.includes(motif)) {
		  concertField.disabled = false;
		  concertField.style.backgroundColor = "";
		  calendarIcon.style.pointerEvents = "";
		  calendarIcon.style.opacity = "";
		} else {
		  concertField.disabled = true;
		  concertField.value = "";
		  concertIdField.value = "";
		  concertField.style.backgroundColor = "#e9e9e9";
		  calendarIcon.style.pointerEvents = "none";
		  calendarIcon.style.opacity = "0.4";
		  concertAutocomplete.style.display = "none";
		}
	  }

    // --- (Nouveau) Remplit la date générale dès sélection concert ---
    function setDateFieldFromConcert(concert) {
        if (!dateField) return;
        // Format "JJ/MM/AAAA"
        if (dateField._flatpickr) {
            // Flatpickr attend ISO ou objet Date
            dateField._flatpickr.setDate(concert.date, true, "Y-m-d");
        } else {
            dateField.value = formatDate(concert.date);
        }
    }

    function fillConcert(concert) {
        concertField.value = `${concert.dateFr} — ${concert.lieu}`;
        concertIdField.value = concert.id;
        concertField.dataset.locked = "true";
        concertAutocomplete.style.display = "none";
        // (Nouveau) Remplit la date générale
        setDateFieldFromConcert(concert);
    }

    // --- Flatpickr sur input caché (concert lié) ---
    flatpickr(concertDatePicker, {
        dateFormat: "Y-m-d",
        locale: flatpickr.l10ns.fr,
        enable: concerts.map(c => c.date),
        clickOpens: true,
        allowInput: false,
        onChange: function (selectedDates, dateStr) {
            const concert = concerts.find(c => c.date === dateStr);
            if (concert) fillConcert(concert);
        }
    });

    // Icône calendrier ouvre le Flatpickr (concert lié)
    calendarIcon.addEventListener("click", function () {
        concertDatePicker._flatpickr.open();
    });

    // --- Autocomplete maison ---
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
        currentMatches = concerts.filter(c => {
            const label = `${c.dateFr} — ${c.lieu}`.toLowerCase();
            const words = label.split(/[\s—]+/);
            return words.some(word => word.startsWith(value));
        });
        currentIndex = -1;
        if (currentMatches.length === 0) {
            concertAutocomplete.style.display = "none";
            return;
        }
        currentMatches.forEach((c, i) => {
            const item = document.createElement("div");
            item.textContent = `${c.dateFr} — ${c.lieu}`;
            item.className = "autocomplete-item";
            item.tabIndex = -1;
            item.addEventListener("mousedown", function (e) {
                selectByMouse = true;
                fillConcert(c); // Remplit aussi la date
            });
            item.addEventListener("mouseenter", function () {
                currentIndex = i;
                updateHighlight();
            });
            concertAutocomplete.appendChild(item);
        });
        concertAutocomplete.style.display = "block";
    });

    function updateHighlight() {
        const items = concertAutocomplete.querySelectorAll(".autocomplete-item");
        items.forEach((item, i) => {
            item.style.background = (i === currentIndex) ? "#eef" : "white";
        });
    }

    concertField.addEventListener("keydown", function (e) {
        const items = concertAutocomplete.querySelectorAll(".autocomplete-item");
        if (items.length === 0) return;
        if (concertField.dataset.locked === "true" && !["Tab", "ArrowUp", "ArrowDown"].includes(e.key)) {
            e.preventDefault();
            return;
        }
        if (e.key === "ArrowDown") {
            e.preventDefault();
            currentIndex = (currentIndex + 1) % items.length;
            updateHighlight();
        } else if (e.key === "ArrowUp") {
            e.preventDefault();
            currentIndex = (currentIndex - 1 + items.length) % items.length;
            updateHighlight();
        } else if (e.key === "Tab" || e.key === "Enter") {
            if (currentIndex >= 0) {
                e.preventDefault();
                fillConcert(currentMatches[currentIndex]);
            }
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

    if (musicienSelect) musicienSelect.addEventListener("change", refreshConcertField);
    if (motifSelect) motifSelect.addEventListener("change", refreshConcertField);

    refreshConcertField();

    if (concertField.value.trim() && !concertIdField.value) {
        const match = concerts.find(c => `${c.dateFr} — ${c.lieu}` === concertField.value.trim());
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
