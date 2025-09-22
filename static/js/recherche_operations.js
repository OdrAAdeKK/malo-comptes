// static/js/recherche_operations.js (NOUVEAU CONTENU)

/* ----------------- Helpers ----------------- */
function normText(s){
  return (s||"")
    .toString()
    .normalize('NFD').replace(/\p{Diacritic}/gu,'')
    .toLowerCase()
    .trim();
}

function parseAmountCell(td){
  // Exemple cellule: "+ 50,00 €" ou "− 50,00 €"
  const raw = (td.innerText||"").replace(/\s/g,'').replace('€','').replace(',', '.');
  // garde le signe si présent, sinon parseFloat
  const num = parseFloat(raw.replace(/[^\d.\-+]/g,''));
  return isNaN(num) ? null : num;
}

function parseAmountQuery(q){
  if(!q) return null;
  const raw = q.replace(/\s/g,'').replace(',', '.');
  const num = parseFloat(raw.replace(/[^\d.\-+]/g,''));
  return isNaN(num) ? null : Math.abs(num);
}

function anyWordMatches(needle, hay){
  // needle: "rennes odradek" -> match si "rennes" OU "odradek" est présent
  const words = normText(needle).split(/\s+/).filter(Boolean);
  const h = normText(hay);
  return words.length === 0 ? false : words.some(w => h.includes(w));
}

/* Position des colonnes dans les tableaux d’archives (fixes dans le template) :
   0: Date | 1: Qui | 2: Type | 3: Motif | 4: Précision | 5: Montant | 6: Concert | 7: Actions
   cf. archives_operations_saison.html :contentReference[oaicite:2]{index=2}
*/

function filtrerLignes(critere, valeur){
  const tables = document.querySelectorAll("table.archived-table");
  const retourBtn = document.getElementById('btn-retour-liste'); // déjà dans le template :contentReference[oaicite:3]{index=3}
  let totalMatch = 0;

  const crit = (critere||'montant').toLowerCase();
  const q = (valeur||'').trim();

  // Hints dynamiques dans la popup
  const hintMontant = document.getElementById('hint-montant');
  const hintConcert = document.getElementById('hint-concert');
  if(hintMontant && hintConcert){
    hintMontant.style.display = (crit === 'montant') ? '' : 'none';
    hintConcert.style.display = (crit === 'concert') ? '' : 'none';
  }

  // Préparation selon critère
  let targetAbs = null;
  if(crit === 'montant'){
    targetAbs = parseAmountQuery(q);
    if(targetAbs === null){
      // Rien de chiffré : on n’affiche rien plutôt que tout
      tables.forEach(tbl => tbl.querySelectorAll('tbody tr').forEach(tr => tr.style.display='none'));
      if(retourBtn) retourBtn.style.display = '';
      return 0;
    }
  }

  tables.forEach(tbl => {
    const rows = tbl.querySelectorAll('tbody tr');
    rows.forEach(tr => {
      const tds = tr.children;
      let keep = false;

      if(crit === 'montant'){
        const cellVal = parseAmountCell(tds[5]);
        keep = (cellVal !== null) && (Math.abs(cellVal) === targetAbs);
      }
      else if(crit === 'date'){
        // On matche en substring sur la chaine JJ/MM/AAAA déjà affichée
        keep = normText(tds[0].innerText).includes(normText(q));
      }
      else if(crit === 'qui'){
        keep = normText(tds[1].innerText).includes(normText(q));
      }
      else if(crit === 'motif'){
        // Motif seul (col. 3). Si tu veux inclure aussi "Précision", remplace tds[3] par (tds[3].innerText + " " + tds[4].innerText)
        keep = normText(tds[3].innerText).includes(normText(q));
      }
      else if(crit === 'concert'){
        // Libellé “JJ/MM/AAAA — Lieu ...” : on considère match si au moins UN mot saisi est présent
        keep = anyWordMatches(q, tds[6].innerText);
      }

      tr.style.display = keep ? '' : 'none';
      if(keep) totalMatch++;
    });
  });

  if(retourBtn) retourBtn.style.display = '';
  return totalMatch;
}

/* API publique appelée par la popup */
function lancerRecherche(){
  const crit = document.getElementById('critere-recherche').value;
  const val  = document.getElementById('valeur-recherche').value;
  filtrerLignes(crit, val);
  fermerPopupRecherche();
}

/* Bouton “🔁 Retour à la liste complète” déjà présent dans le template (id=btn-retour-liste) */
window.retourListe = function(){
  document.querySelectorAll("table.archived-table tbody tr").forEach(tr => tr.style.display='');
  const retourBtn = document.getElementById('btn-retour-liste');
  if(retourBtn) retourBtn.style.display = 'none';
};

/* Optionnel: Modifier le libellé du bouton d’ouverture quand on change de critère */
document.addEventListener('DOMContentLoaded', () => {
  const critSel = document.getElementById('critere-recherche');
  const openButtons = document.querySelectorAll('button[onclick="ouvrirPopupRecherche()"]');
  if(critSel){
    critSel.addEventListener('change', () => {
      const crit = critSel.value;
      openButtons.forEach(btn => {
        if(crit === 'montant') btn.textContent = '🔍 Recherche par montant';
        else btn.textContent = '🔍 Recherche';
      });
      // Hints dynamiques si la popup est ouverte
      const hintMontant = document.getElementById('hint-montant');
      const hintConcert = document.getElementById('hint-concert');
      if(hintMontant && hintConcert){
        hintMontant.style.display = (crit === 'montant') ? '' : 'none';
        hintConcert.style.display = (crit === 'concert') ? '' : 'none';
      }
    });
  }
});

// Expose pour l’HTML
window.ouvrirPopupRecherche = ouvrirPopupRecherche;
window.fermerPopupRecherche = fermerPopupRecherche;
window.lancerRecherche = lancerRecherche;
