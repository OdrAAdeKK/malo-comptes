(function() {
  function qs(sel, root=document){ return root.querySelector(sel); }
  function qsa(sel, root=document){ return Array.from(root.querySelectorAll(sel)); }

  function normalizeNumberInput(v){
    if (v == null) return "";
    return String(v)
      .trim()
      .replace(/\u00A0/g, "") // espaces insécables
      .replace(/\s+/g, "")    // espaces
      .replace(",", ".");     // virgule -> point
  }

  function showPopupAjust(concertId){
    // Garde-fou : le partial doit être présent dans la page
    if (!qs("#popup-ajustements")) {
      alert("Le pop-up d'ajustement est absent du template.");
      return;
    }

    fetch(`/participants_concert/${concertId}`)
      .then(async r => {
        let payload=null;
        try { payload = await r.json(); } catch(e){ /* pas du JSON */ }
        if (!payload) throw new Error("Réponse invalide du serveur.");
        return payload;
      })
      .then(data=>{
        if(!data.success){ alert(data.message || "Erreur de chargement des participants"); return; }

        const wrap = qs("#ajustements-list");
        wrap.innerHTML = "";

        data.items.forEach(it=>{
          const row = document.createElement("div");
          row.className = "row";

          const label = document.createElement("label");
          label.textContent = `${it.nom}`;

          // ⚠️ text + inputmode decimal = tolère la virgule FR
          const input = document.createElement("input");
          input.type = "text";
          input.inputMode = "decimal";
          input.placeholder = "laisser vide = non fixé";
          input.value = (it.fixe !== null && it.fixe !== undefined) ? it.fixe : "";
          input.dataset.participationId = it.participation_id;

          const span = document.createElement("span");
          span.className = "note";
          const actuel = (data.paye ? Number(it.reel || 0) : Number(it.potentiel || 0)).toFixed(2);
          span.textContent = ` (actuel: ${actuel} €)`;

          row.appendChild(label);
          row.appendChild(input);
          row.appendChild(span);
          wrap.appendChild(row);
        });

        qs("#popup-ajustements").style.display = "flex";

        const btnSave = qs("#ajust-save");
        const btnCancel = qs("#ajust-cancel");

        btnSave.onclick = function(){
          const overrides = {};
          qsa("#ajustements-list input").forEach(inp=>{
            const raw = normalizeNumberInput(inp.value);
            overrides[inp.dataset.participationId] = raw === "" ? null : raw;
          });

          btnSave.disabled = true;

          fetch("/ajuster_gains", {
            method:"POST",
            headers:{ "Content-Type":"application/json" },
            body: JSON.stringify({ concert_id: concertId, overrides })
          })
          .then(async r=>{
            let payload=null;
            try { payload = await r.json(); } catch(e){ /* pas du JSON */ }
            if (!payload) throw new Error("Réponse invalide du serveur");
            // si le serveur renvoie 4xx/5xx avec un JSON {message}, on surface l'erreur
            if (!r.ok && payload && payload.message) throw new Error(payload.message);
            return payload;
          })
          .then(res=>{
            if(res.success){ location.reload(); }
            else { throw new Error(res.message || "Erreur d'enregistrement"); }
          })
          .catch(err=>{
            alert(err.message || "Erreur réseau / serveur");
          })
          .finally(()=>{
            btnSave.disabled = false;
          });
        };

        btnCancel.onclick = function(){
          qs("#popup-ajustements").style.display = "none";
        };
        qs("#popup-ajustements .popup-backdrop").onclick = function(){
          qs("#popup-ajustements").style.display = "none";
        };
        document.addEventListener("keydown", function escClose(ev){
          if (ev.key === "Escape") {
            qs("#popup-ajustements").style.display = "none";
            document.removeEventListener("keydown", escClose);
          }
        }, { once:true });
      })
      .catch(err=>{
        alert(err.message || "Erreur de chargement");
      });
  }

  // bouton par ligne
  document.addEventListener("click", function(e){
    const a = e.target.closest(".adjust-button");
    if(a){
      e.preventDefault();
      const id = a.dataset.id;
      showPopupAjust(id);
    }
  });
})();
