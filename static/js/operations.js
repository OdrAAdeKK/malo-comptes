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
    // Déclaration des éléments...
    const quiSelect = document.getElementById('musicien');
    const motifSelect = document.getElementById('motif');
	const brutField = document.getElementById('brut');
    const creditRadio = document.getElementById('credit_radio');
    const debitRadio = document.getElementById('debit_radio');
    const modeRadios = document.querySelectorAll('input[name="mode"]');
    const structures = ["ASSO7", "CB ASSO7", "CAISSE ASSO7", "TRESO ASSO7"];

    function updateFormFields() {
        const selectedBenef = quiSelect ? quiSelect.value.trim() : "";
        const selectedMotif = motifSelect ? motifSelect.value.trim() : "";

// ===== LOGIQUE POUR LES MOTIFS =====
const motifRules = {
    "musicien": ["Salaire", "Frais"],
    "ASSO7": ["Achat", "Vente"],
    "CB ASSO7": ["Frais", "Recette concert"],
    "CAISSE ASSO7": ["Frais", "Recette concert"]
};

function getMotifAllowedList(benef) {
    // Par défaut, si pas une structure reconnue → musicien
    if (["ASSO7", "CB ASSO7", "CAISSE ASSO7"].includes(benef)) return motifRules[benef];
    return motifRules["musicien"];
}

if (motifSelect) {
    const selectedBenef = quiSelect ? quiSelect.value.trim() : "";
    const allowedMotifs = getMotifAllowedList(selectedBenef);

    for (const option of motifSelect.options) {
        if (!allowedMotifs.includes(option.value)) {
            option.disabled = true;
            option.hidden = true;
        } else {
            option.disabled = false;
            option.hidden = false;
        }
    }
    // Si le motif sélectionné n’est plus autorisé, sélectionne le premier motif valide
    if (!allowedMotifs.includes(motifSelect.value)) {
        motifSelect.value = allowedMotifs[0];
    }

    // Grise le champ BRUT sauf si 'Salaire'
    if (motifSelect.value === "Salaire") {
        brutField.disabled = false;
        brutField.style.background = ""; // normal
    } else {
        brutField.disabled = true;
        brutField.value = ""; // optionnel, pour effacer si pas salaire
        brutField.style.background = "#f3f3f3";
    }
}



        // Forcer certains comportements pour CAISSE ASSO7 (débit interdit, mode espèces forcé)
		const isCaisse = selectedBenef === "CAISSE ASSO7";
		if (debitRadio) debitRadio.disabled = isCaisse;
		if (creditRadio && isCaisse) creditRadio.checked = true;

		if (isCaisse) {
			// Mode Espèces coché, non modifiable
			for (const radio of modeRadios) {
				radio.disabled = true;
				if (radio.value === "Espèces") radio.checked = true;
			}
		} else {
			// Mode Compte coché par défaut, tout redevient modifiable
			for (const radio of modeRadios) {
				radio.disabled = false;
				if (radio.value === "Compte") radio.checked = true;
			}
		}


			// Ajuster type d'opération selon le motif sélectionné et le bénéficiaire
			creditRadio.disabled = false;
			debitRadio.disabled = false;

			if (selectedMotif === "Vente") {
				creditRadio.checked = true;
			} else if (selectedMotif === "Recette concert") {
				creditRadio.checked = true;
				creditRadio.disabled = true;
				debitRadio.disabled = true;
			} else if (selectedMotif === "Salaire") {
				debitRadio.checked = true;
				creditRadio.disabled = true;
				debitRadio.disabled = true;
			} else if (selectedMotif === "Frais") {
				if (["CB ASSO7", "CAISSE ASSO7"].includes(selectedBenef)) {
					debitRadio.checked = true;
					creditRadio.disabled = true;
					debitRadio.disabled = true;
				} else {
					creditRadio.checked = true;
					creditRadio.disabled = true;
					debitRadio.disabled = true;
				}
			} else {
				// Par défaut, aucune sélection automatique
			}


    }

    if (quiSelect) {
        quiSelect.addEventListener('change', updateFormFields);
    }
    if (motifSelect) motifSelect.addEventListener('change', updateFormFields);

    // Initialisation au chargement
    updateFormFields();

    // === Coloration des options spéciales et placement correct ===
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

    // On reconstruit la liste dans l'ordre souhaité (optionnel mais plus propre)
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
}



/* ===============================
   3. Autocomplete + Calendrier Flatpickr
   =============================== */

function initConcertAutocomplete() {
    const concertField = document.getElementById("concert_field");
    const concertIdField = document.getElementById("concert_id");
    const concertAutocomplete = document.getElementById("concert_autocomplete");
    const calendarIcon = document.getElementById("calendar_icon");
    const concertDatePicker = document.getElementById("concert_date_picker"); // input caché pour Flatpickr (concert lié)
    const musicienSelect = document.getElementById("musicien");
    const motifSelect = document.getElementById("motif");
    const dateField = document.getElementById("date"); // champ date général

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
        const motifsQuiActivent = ["Frais", "Recette concert"];
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
        if (concertDatePicker._flatpickr) {
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
