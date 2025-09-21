"use strict";

/**
 * Autocomplete + création rapide pour Lieux.
 * Dépend des endpoints:
 *  - GET  /api/lieux/search?q=...
 *  - POST /api/lieux  (JSON)
 * Champs attendus dans le formulaire:
 *  - #lieu_field (name="lieu")
 *  - #lieu_id    (name="lieu_id")
 */
function initLieuxUI() {
  const field = document.getElementById("lieu_field");
  const hiddenId = document.getElementById("lieu_id");
  const list = document.getElementById("lieux_autocomplete");
  const btnNew = document.getElementById("btn_nouveau_lieu");

  const modal = document.getElementById("lieuModal");
  const closeModal = document.getElementById("closeLieuModal");
  const btnCreate = document.getElementById("btn_creer_lieu");
  const btnCancel = document.getElementById("btn_annuler_lieu");

  if (!field || !hiddenId || !list) return;

  let current = [];
  let idx = -1;

  function showList(items) {
    list.innerHTML = "";
    if (!items.length) { list.style.display = "none"; return; }
    items.forEach((it, i) => {
      const div = document.createElement("div");
      div.className = "autocomplete-item";
      div.textContent = it.ville ? `${it.nom} — ${it.ville}` : it.nom;
      div.addEventListener("mousedown", () => {
        field.value = it.nom;
        hiddenId.value = it.id;
        list.style.display = "none";
      });
      list.appendChild(div);
    });
    list.style.display = "block";
  }

  let fetchCtrl;
  field.addEventListener("input", async () => {
    hiddenId.value = "";
    const q = (field.value || "").trim();
    if (q.length < 1) { list.style.display = "none"; return; }

    try {
      if (fetchCtrl) fetchCtrl.abort();
      fetchCtrl = new AbortController();
      const res = await fetch(`/api/lieux/search?q=${encodeURIComponent(q)}`, { signal: fetchCtrl.signal });
      const data = await res.json();
      current = data || [];
      idx = -1;
      showList(current);
    } catch (e) {
      // silencieux si abort
    }
  });

  field.addEventListener("keydown", (e) => {
    const items = list.querySelectorAll(".autocomplete-item");
    if (!items.length) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      idx = (idx + 1) % items.length;
      items.forEach((it, i) => it.classList.toggle("active", i === idx));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      idx = (idx - 1 + items.length) % items.length;
      items.forEach((it, i) => it.classList.toggle("active", i === idx));
    } else if (e.key === "Enter" && idx >= 0) {
      e.preventDefault();
      items[idx].dispatchEvent(new Event("mousedown"));
    } else if (e.key === "Escape") {
      list.style.display = "none";
    }
  });

  field.addEventListener("blur", () => setTimeout(() => list.style.display = "none", 120));

  // Modal Nouveau Lieu
  if (btnNew && modal) {
    const getV = id => document.getElementById(id).value.trim();

    const open = () => { modal.style.display = "block"; };
    const close = () => { modal.style.display = "none"; };

    btnNew.addEventListener("click", open);
    btnCancel && btnCancel.addEventListener("click", close);
    closeModal && closeModal.addEventListener("click", close);

    btnCreate && btnCreate.addEventListener("click", async () => {
      const payload = {
        nom:         getV("m_lieu_nom"),
        ville:       getV("m_lieu_ville"),
        code_postal: getV("m_lieu_cp"),
        adresse:     getV("m_lieu_adresse"),
        email:       getV("m_lieu_email"),
        telephone:   getV("m_lieu_tel"),
        contacts:    getV("m_lieu_contacts"),
        note:        getV("m_lieu_note"),
      };
      if (!payload.nom || !payload.ville || !payload.code_postal) {
        alert("Nom, Ville et Code postal sont requis."); return;
      }
      try {
        const res = await fetch("/api/lieux", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const data = await res.json();
        if (!data.success) { alert(data.message || "Création impossible."); return; }
        // Remplit le formulaire du concert avec ce nouveau lieu
        field.value = `${data.lieu.nom}`;
        hiddenId.value = data.lieu.id;
        close();
      } catch (e) {
        alert("Erreur réseau lors de la création du lieu.");
      }
    });
  }
}
