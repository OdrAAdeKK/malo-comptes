# calcul_participations.py

from models import db, Concert, Participation, Musicien

# --------------------------- Utilitaires ---------------------------

def get_recette_utilisee(concert: Concert) -> float | None:
    """Recette réelle si présente, sinon recette_attendue si non payé, sinon None."""
    if concert.recette is not None:
        return float(concert.recette)
    if not concert.paye and concert.recette_attendue is not None:
        return float(concert.recette_attendue)
    return None


def _is_jerome(m: Musicien) -> bool:
    n = (m.nom or "").strip().casefold()
    p = (m.prenom or "").strip().casefold()
    return n == "arnould" and p.startswith("jérôme")


def _is_asso7(m: Musicien) -> bool:
    # tu utilises un Musicien "ASSO7" (nom ou prénom) comme structure
    return (m.nom or "").strip().upper() == "ASSO7" or (m.prenom or "").strip().upper() == "ASSO7"


# --------------------------- Partage "standard" ---------------------------

def partage_benefices_concert(concert: Concert):
    """
    Renvoie:
      - dict {musicien_id: montant} pour tous les musiciens (hors ASSO7),
      - montant_asso7 (part côté ASSO7),
      - montant_jerome (bonus 10% si Jérôme participe).
    """
    recette_utilisee = get_recette_utilisee(concert)
    if recette_utilisee is None:
        print(f"[!] Concert id={concert.id} ignoré (aucune recette/preview)")
        return {}, 0.0, 0.0

    frais = float(concert.frais or 0.0)
    benefices = recette_utilisee - frais
    if benefices <= 0:
        print(f"[!] Concert id={concert.id} ignoré (bénéfice négatif ou nul)")
        return {}, 0.0, 0.0

    # participants (objets Participation + Musicien chargés)
    parts = Participation.query.filter_by(concert_id=concert.id).all()
    if not parts:
        return {}, 0.0, 0.0

    musiciens_map = {p.musicien_id: Musicien.query.get(p.musicien_id) for p in parts}
    presents = [m for m in musiciens_map.values() if m]

    # détection
    jerome_obj = next((m for m in presents if _is_jerome(m)), None)
    asso7_obj = next((m for m in presents if _is_asso7(m)), None)

    # 10% pour Jérôme s'il est là
    pour_jerome = round(benefices * 0.10, 2) if jerome_obj else 0.0
    reste = benefices - pour_jerome

    # parts égales entre tous les participants "hors ASSO7" + 1 part pour ASSO7
    nb_participants_hors_asso7 = sum(1 for m in presents if not _is_asso7(m))
    nb_parts = nb_participants_hors_asso7 + 1  # +1 pour ASSO7
    part_unitaire = round(reste / nb_parts, 2) if nb_parts else 0.0

    # montants par musicien (hors ASSO7)
    resultats = {}
    for mid, m in musiciens_map.items():
        if _is_asso7(m):
            continue
        if jerome_obj and m.id == jerome_obj.id:
            resultats[mid] = round(part_unitaire + pour_jerome, 2)
        else:
            resultats[mid] = part_unitaire

    print(f"[✓] Concert id={concert.id} → part={part_unitaire}, jerome={pour_jerome}, total_benef={benefices}")
    return resultats, part_unitaire, pour_jerome


def _build_base_distribution(concert: Concert) -> dict:
    """
    Construit un dict de référence:
       { <musicien_id:int>: montant, "ASSO7": montant }
    à partir du partage standard.
    """
    credits_musiciens, part_asso7, _bonus_j = partage_benefices_concert(concert)

    base = {"ASSO7": float(part_asso7 or 0.0)}
    # inclure uniquement les participations présentes (y compris ASSO7)
    for p in concert.participations:
        m = Musicien.query.get(p.musicien_id)
        if not m:
            continue
        if _is_asso7(m):
            # la clé réservée pour la structure
            base["ASSO7"] = float(part_asso7 or 0.0)
        else:
            base[p.musicien_id] = float(credits_musiciens.get(p.musicien_id, 0.0))
    return base


# --------------------------- Application des "gains fixés" ---------------------------

def _collect_overrides(concert_id: int) -> dict:
    overrides = {}
    for p in Participation.query.filter_by(concert_id=concert_id).all():
        if p.gain_fixe is None:
            continue
        m = Musicien.query.get(p.musicien_id)
        if not m:
            continue
        key = "ASSO7" if (m.nom or "").strip().upper() == "ASSO7" or (m.prenom or "").strip().upper() == "ASSO7" else p.musicien_id
        overrides[key] = float(p.gain_fixe)
    print(f"[FIXES] overrides lus pour concert {concert_id} :", overrides)  # ⬅️ ajout
    return overrides


def _appliquer_gains_fixes(concert_id: int, parts: dict) -> dict:
    """
    parts: { <musicien_id:int>: montant, 'ASSO7': montant }
    Applique les montants fixés et redistribue proportionnellement
    le reste entre les non-fixés (y compris ASSO7 si non fixé).
    """
    if not parts:
        return parts

    overrides = _collect_overrides(concert_id)
    if not overrides:
        return parts

    # cast -> float
    parts = {k: float(v or 0.0) for k, v in parts.items()}
    total_net = sum(parts.values())

    # somme des fixes qui ciblent uniquement des clés existantes
    somme_fixes = sum(v for k, v in overrides.items() if k in parts)

    if somme_fixes > total_net + 1e-6:
        raise ValueError("La somme des gains fixés dépasse le total disponible.")

    # clés qui restent à répartir (toutes celles qui ne sont pas fixées)
    rest_keys = [k for k in parts.keys() if k not in overrides]
    base_rest_sum = sum(parts[k] for k in rest_keys)
    reste_a_repartir = total_net - somme_fixes

    adjusted = {}

    # 1) appliquer fixes
    for k, v in overrides.items():
        if k in parts:
            adjusted[k] = float(v)

    # 2) redistribuer le reste proportionnellement aux parts "de base"
    if base_rest_sum <= 0:
        # tout ce qui reste va à ASSO7 si présent
        for k in rest_keys:
            adjusted[k] = 0.0
        if "ASSO7" in parts:
            adjusted["ASSO7"] = adjusted.get("ASSO7", 0.0) + reste_a_repartir
    else:
        for k in rest_keys:
            poids = parts[k] / base_rest_sum
            adjusted[k] = reste_a_repartir * poids

    # (optionnel) arrondir au centime
    adjusted = {k: round(v, 2) for k, v in adjusted.items()}

    print(f"[FIXES] overrides={overrides} | total={total_net} | somme_fixes={somme_fixes} | reste={reste_a_repartir}")
    return adjusted


# --------------------------- Écritures DB ---------------------------

def _assurer_part_asso7(concert: Concert) -> None:
    """Ajoute automatiquement une participation ASSO7 si la structure existe mais n'est pas présente."""
    asso7 = Musicien.query.filter(Musicien.nom.ilike("ASSO7")).first()
    if not asso7:
        return
    if any(p.musicien_id == asso7.id for p in concert.participations):
        return
    nouvelle_part = Participation(concert_id=concert.id, musicien_id=asso7.id)
    db.session.add(nouvelle_part)
    concert.participations.append(nouvelle_part)
    print(f"[+] Participation ajoutée pour ASSO7 au concert id={concert.id}")


def _write_parts(concert: Concert, parts_final: dict, *, to_field: str) -> None:
    """
    Écrit les parts dans Participation.<to_field>.
    to_field ∈ {"credit_calcule", "credit_calcule_potentiel"}.
    """
    for part in concert.participations:
        m = Musicien.query.get(part.musicien_id)
        if not m:
            continue
        key = "ASSO7" if _is_asso7(m) else part.musicien_id
        value = float(parts_final.get(key, 0.0))

        if to_field == "credit_calcule":
            part.credit_calcule = value
        else:
            part.credit_calcule_potentiel = value

        db.session.add(part)


# --------------------------- API appelées par les routes ---------------------------

def mettre_a_jour_credit_calcule(concert: Concert) -> None:
    """Remplit credit_calcule selon le partage standard (utilisé lors du paiement)."""
    credits, credit_asso7, _ = partage_benefices_concert(concert)
    for part in concert.participations:
        m = Musicien.query.get(part.musicien_id)
        if not m:
            continue
        if _is_asso7(m):
            part.credit_calcule = float(credit_asso7 or 0.0)
        else:
            part.credit_calcule = float(credits.get(part.musicien_id, 0.0))
        print(f"[✓] crédit réel → participation id={part.id} → {part.credit_calcule:.2f}")
        db.session.add(part)
    db.session.commit()


def mettre_a_jour_credit_calcule_reel_pour_concert(concert_id: int) -> None:
    """
    APPELÉE quand un concert devient PAYÉ.
    - met à 0 les potentiels
    - calcule la distribution standard
    - applique les fixes
    - écrit dans credit_calcule
    """
    db.session.expire_all()
    concert = Concert.query.get(concert_id)
    if not concert:
        print(f"[!] Concert id={concert_id} introuvable.")
        return

    _assurer_part_asso7(concert)

    # Distribution de base + fixes
    base = _build_base_distribution(concert)
    final = _appliquer_gains_fixes(concert.id, base)

    # Zéro le potentiel et écris le réel
    for part in concert.participations:
        part.credit_calcule_potentiel = 0.0
        db.session.add(part)
    _write_parts(concert, final, to_field="credit_calcule")
    db.session.commit()
    print(f"[✓] Réel ajusté écrit pour concert id={concert.id}")


def mettre_a_jour_credit_calcule_potentiel_pour_concert(concert_id: int) -> None:
    """
    APPELÉE pour (re)calculer les potentiels d'un concert NON PAYÉ,
    ou si payé → bascule sur le réel.
    """
    db.session.expire_all()
    concert = Concert.query.get(concert_id)
    if not concert:
        print(f"[!] Concert id={concert_id} introuvable.")
        return

    _assurer_part_asso7(concert)

    if concert.paye:
        # si déjà payé, calcule le réel
        mettre_a_jour_credit_calcule_reel_pour_concert(concert.id)
        return

    # NON PAYÉ → base + fixes → écrire POTENTIEL
    base = _build_base_distribution(concert)
    final = _appliquer_gains_fixes(concert.id, base)

    # reset du réel par précaution
    for part in concert.participations:
        part.credit_calcule = 0.0
        db.session.add(part)

    _write_parts(concert, final, to_field="credit_calcule_potentiel")
    db.session.commit()
    print(f"[✓] Potentiel ajusté écrit pour concert id={concert.id}")


# -------------------------------------------------------------------
# Recalc global (compat avec l'ancien import dans mes_utils.py)
# -------------------------------------------------------------------

def mettre_a_jour_credit_calcule_potentiel() -> None:
    """
    Back-compat: recalcul global attendu par mes_utils.py
      - Concerts NON PAYÉS  -> écrit POTENTIEL ajusté
      - Concerts PAYÉS      -> écrit RÉEL ajusté (et remet POTENTIEL à 0)
    """
    # NON PAYÉS
    non_payes = Concert.query.filter(Concert.paye.is_(False)).all()
    print(f"\n🔍 Concerts non payés : {len(non_payes)}")
    for c in non_payes:
        mettre_a_jour_credit_calcule_potentiel_pour_concert(c.id)

    # PAYÉS
    payes = Concert.query.filter(Concert.paye.is_(True)).all()
    print(f"💰 Concerts payés : {len(payes)}")
    for c in payes:
        mettre_a_jour_credit_calcule_reel_pour_concert(c.id)

    print("✅ Mise à jour des crédits potentiels et réels terminée.")


# -------------------------------------------------------------------
# Script autonome
# -------------------------------------------------------------------

def executer_recalcul_complet():
    """Appel global si utilisé comme script autonome."""
    mettre_a_jour_credit_calcule_potentiel()

if __name__ == "__main__":
    from App import app
    with app.app_context():
        executer_recalcul_complet()
