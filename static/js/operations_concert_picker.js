let concerts = [];
let fp = null;

document.addEventListener("DOMContentLoaded", function () {
    if (flatpickr && flatpickr.l10ns && flatpickr.l10ns.fr) {
        flatpickr.localize(flatpickr.l10ns.fr);
    } else {
        console.warn("❌ flatpickr.l10ns.fr non disponible !");
    }

    const concertField = document.getElementById("concert_field");
    const concertIdField = document.getElementById("concert_id");
    const concertAutocomplete = document.getElementById("concert_autocomplete");
    const calendarIcon = document.getElementById("calendar_icon");
    const dateField = document.getElementById("date");

    concerts = (window.concerts || []).map(c => {
        const [y, m, d] = c.date.split("-");
        return {
            ...c,
            dateFr: `${d}/${m}/${y}`
        };
    });

    function formatDate(isoDate) {
        const [year, month, day] = isoDate.split("-");
        return `${day}/${month}/${year}`;
    }

    let selectedConcert = null;

    fp = flatpickr(concertField, {
        dateFormat: "Y-m-d",
        locale: flatpickr.l10ns.fr,
        enable: concerts.map(c => c.date),
        clickOpens: false,
        allowInput: true,
        onChange: function (selectedDates, dateStr) {
            const concert = concerts.find(c => c.date === dateStr);
            if (concert) {
                selectedConcert = concert;
                concertField.value = `${concert.dateFr} — ${concert.lieu}`;
                concertIdField.value = concert.id;
                concertField.dataset.locked = "true";
                concertAutocomplete.style.display = "none";
                if (window.flatpickrInstance) {
                    window.flatpickrInstance.setDate(concert.date, true);
                }
            }
        }
    });

    calendarIcon.addEventListener("click", () => fp.open());

    const flatpickrInstance = flatpickr("#date", {
        dateFormat: "Y-m-d",
        locale: flatpickr.l10ns.fr,
        altInput: true,
        altFormat: "d/m/Y",
    });
    window.flatpickrInstance = flatpickrInstance;

    let currentIndex = -1;
    let currentMatches = [];

    concertField.addEventListener("input", function () {
        const value = concertField.value.trim().toLowerCase();
        concertAutocomplete.innerHTML = "";

        if (concertField.dataset.locked === "true") return;

        selectedConcert = null;
        concertIdField.value = "";
        concertField.dataset.locked = "";

        if (value.length < 1) {
            concertAutocomplete.style.display = "none";
            return;
        }

        const matches = concerts.filter(c => {
            const dateJJMMYYYY = formatDate(c.date);
            const label = `${dateJJMMYYYY} — ${c.lieu}`;
            const valueLower = value.toLowerCase();
            return (
                label.toLowerCase().startsWith(valueLower) ||
                c.lieu.toLowerCase().startsWith(valueLower)
            );
        });

        currentMatches = matches;
        currentIndex = -1;

        if (matches.length === 0) {
            concertAutocomplete.style.display = "none";
            return;
        }

        matches.forEach((c, i) => {
            const item = document.createElement("div");
            item.textContent = `${c.dateFr} — ${c.lieu}`;
            item.style.padding = "6px 10px";
            item.style.cursor = "pointer";
            item.style.borderBottom = "1px solid #ddd";
            item.style.background = "white";

            item.addEventListener("mousedown", function (e) {
                e.preventDefault();
                selectedConcert = c;
                concertField.value = `${c.dateFr} — ${c.lieu}`;
                concertIdField.value = c.id;
                concertField.dataset.locked = "true";
                if (window.flatpickrInstance) {
                    window.flatpickrInstance.setDate(c.date, true);
                }
                concertAutocomplete.style.display = "none";
            });

            concertAutocomplete.appendChild(item);
        });

        concertAutocomplete.style.display = "block";
    });

    concertField.addEventListener("blur", function () {
        if (selectedConcert && concertField.dataset.locked === "true") {
            concertField.value = `${selectedConcert.dateFr} — ${selectedConcert.lieu}`;
        }
    });

    concertField.addEventListener("keydown", function (e) {
        if (concertField.dataset.locked === "true" && !["Tab", "ArrowUp", "ArrowDown"].includes(e.key)) {
            e.preventDefault();
            return;
        }

        const items = concertAutocomplete.querySelectorAll("div");
        if (items.length === 0) return;

        if (e.key === "ArrowDown") {
            e.preventDefault();
            currentIndex = (currentIndex + 1) % items.length;
        } else if (e.key === "ArrowUp") {
            e.preventDefault();
            currentIndex = (currentIndex - 1 + items.length) % items.length;
        } else if (e.key === "Tab") {
            if (currentIndex >= 0) {
                e.preventDefault();
                const selected = currentMatches[currentIndex];
                selectedConcert = selected;
                concertField.value = `${selected.dateFr} — ${selected.lieu}`;
                concertIdField.value = selected.id;
                concertField.dataset.locked = "true";
                if (window.flatpickrInstance) {
                    window.flatpickrInstance.setDate(selected.date, true);
                }
                concertAutocomplete.style.display = "none";
            }
        }

        items.forEach((item, i) => {
            item.style.background = (i === currentIndex) ? "#eef" : "white";
        });
    });

    document.addEventListener("mousedown", function (e) {
        if (!concertAutocomplete.contains(e.target) && e.target !== concertField) {
            concertAutocomplete.style.display = "none";
        }
    });
});

function updateConcertsForMusicien(nomComplet) {
    const motif = document.getElementById('motif')?.value;

    let data;
    if (motif === "Recette concert") {
        data = window.concerts || [];  // ✅ TOUS les concerts
        console.log("🎯 Affichage des concerts pour RECETTE (tous)");
    } else {
        data = window.concertsParMusicien?.[nomComplet] || [];  // ✅ Filtrage par musicien
        console.log("🎯 Affichage des concerts pour FRAIS (musicien)", nomComplet);
    }

    concerts = data.map(c => {
        const [y, m, d] = c.date.split("-");
        return {
            ...c,
            dateFr: `${d}/${m}/${y}`
        };
    });

    if (fp) {
        fp.set('enable', concerts.map(c => c.date));
        console.log("🔄 Calendrier mis à jour avec concerts :", concerts.map(c => c.dateFr));
    } else {
        console.warn("⚠️ fp (flatpickr) non défini !");
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const musicienSelect = document.getElementById('musicien');
    if (!musicienSelect) {
        console.warn("⚠️ Élément #musicien introuvable dans le DOM.");
        return;
    }

    musicienSelect.addEventListener('change', function () {
        const nomComplet = this.value;
        console.log("👤 Musicien sélectionné :", nomComplet);
        console.log("📚 Clés disponibles dans concertsParMusicien :", Object.keys(window.concertsParMusicien));
        updateConcertsForMusicien(nomComplet);
    });

    if (musicienSelect.value) {
        updateConcertsForMusicien(musicienSelect.value);
    }
});
