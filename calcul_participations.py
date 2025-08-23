# calcul_participations.py

from models import db, Concert, Participation, Musicien

# --------------------------- Utilitaires ---------------------------

def get_recette_utilisee(concert):
    """Retourne la recette réelle si payée ou présente, sinon la recette attendue (si non payée)."""
    if concert.recette is not None:
        return concert.recette
    elif not concert.paye and concert.recette_attendue is not None:
        return concert.recette_attendue
    return None


def partage_benefices_concert(concert):
    """
    Renvoie:
      - dict {musicien_id: montant} pour tous les musiciens (hors ASSO7),
      - montant_asso7 (part fixe côté ASSO7),
      - montant_jerome (bonus 10% si Jérôme participe).
    """
    recette_utilisee = get_recette_utilisee(concert)

    if recette_utilisee is None:
        print(f"[!] Concert id={concert.id} ignoré (aucune recette)")
        return {}, 0, 0

    frais = concert.frais or 0.0
    benefices = recette_utilisee - frais
    if benefices <= 0:
        print(f"[!] Concert id={concert.id} ignoré (bénéfice négatif ou nul)")
        return {}, 0, 0

    participations = Participation.query.filter_by(concert_id=concert.id).all()
    musiciens_ids = [p.musicien_id for p in participations]
    if not musiciens_ids:
        return {}, 0, 0

    musiciens = Musicien.query.filter(Musicien.id.in_(musiciens_ids)).all()

    # Détection Jérôme & ASSO7
    jerome = next(
        (m for m in musiciens
         if m.nom.upper() == "ARNOULD" and (m.prenom or "").upper().startswith("JÉRÔME")),
        None
    )
    asso7 = next((m for m in musiciens if m.nom.upper() == "ASSO7"), None)

    # 10% pour Jérôme s'il est présent
    pour_jerome = round(benefices * 0.10, 2) if jerome else 0.0

    reste = benefices - pour_jerome

    # Parts égales pour tous les participants "hors ASSO7" + 1 part pour ASSO7
    nb_parts = len([m for m in musiciens if m.nom.upper() != "ASSO7"]) + 1
    part_asso7 = round(reste / nb_parts, 2) if nb_parts else 0.0

    # Montants par musicien (hors ASSO7)
    resultats = {}
    for m in musiciens:
        if m.nom.upper() == "ASSO7":
            continue
        if jerome and m.id == jerome.id:
            resultats[m.id] = round(part_asso7 + pour_jerome, 2)
        else:
            resultats[m.id] = part_asso7

    print(
        f"[✓] Concert id={concert.id} → part={part_asso7}, jerome={pour_jerome}, total_benef={benefices}"
    )
    return resultats, part_asso7, pour_jerome


# ---------------------- Calculs des champs crédit ----------------------

def mettre_a_jour_credit_calcule(concert):
    """Remplit le champ credit_calcule pour un concert PAYÉ."""
    credits, credit_asso7, _ = partage_benefices_concert(concert)
    for part in concert.participations:
        montant = credits.get(part.musicien_id)
        if montant is None and part.musicien and (part.musicien.nom or "").upper() == "ASSO7":
            montant = credit_asso7
        part.credit_calcule = float(montant or 0.0)
        print(f"[✓] crédit réel → participation id={part.id} → {part.credit_calcule:.2f}")
    db.session.commit()


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


def mettre_a_jour_credit_calcule_reel_pour_concert(concert_id: int) -> None:
    """
    APPELÉE PAR LES ROUTES quand un concert devient PAYÉ.
    - met à 0 les potentiels
    - calcule les crédits réels (credit_calcule) via partage_benefices_concert
    """
    db.session.expire_all()
    concert = Concert.query.get(concert_id)
    if not concert:
        print(f"[!] Concert id={concert_id} introuvable.")
        return

    _assurer_part_asso7(concert)

    # On nettoie le potentiel si jamais présent
    for part in concert.participations:
        part.credit_calcule_potentiel = 0.0

    # Et on calcule le réel
    mettre_a_jour_credit_calcule(concert)
    print(f"[✓] Crédit RÉEL mis à jour pour concert id={concert_id}")


def mettre_a_jour_credit_calcule_potentiel_pour_concert(concert_id: int) -> None:
    """
    APPELÉE PAR LES ROUTES pour (re)calculer les potentiels d'un concert non payé,
    ou vider les potentiels et recalculer le réel si le concert est payé.
    """
    db.session.expire_all()
    concert = Concert.query.get(concert_id)
    if not concert:
        print(f"[!] Concert id={concert_id} introuvable.")
        return

    print(f"[DEBUG] Concert récupéré id={concert.id}, payé={concert.paye}")
    _assurer_part_asso7(concert)

    if concert.paye:
        print("[DEBUG] Bloc concert PAYÉ exécuté")
        for part in concert.participations:
            part.credit_calcule_potentiel = 0.0
        mettre_a_jour_credit_calcule(concert)
    else:
        print("[DEBUG] Bloc concert NON PAYÉ exécuté")
        # On remet le réel à 0 (précaution)
        for part in concert.participations:
            part.credit_calcule = 0.0
            print(f"[RESET] crédit réel participation id={part.id} → 0.0")

        credits, credit_asso7, _ = partage_benefices_concert(concert)
        for part in concert.participations:
            montant = credits.get(part.musicien_id)
            if montant is None and part.musicien and (part.musicien.nom or "").upper() == "ASSO7":
                montant = credit_asso7
            part.credit_calcule_potentiel = float(montant or 0.0)
            print(f"[OK] potentiel → participation id={part.id} → {part.credit_calcule_potentiel:.2f}")

        db.session.commit()

    print(f"[✓] Mise à jour POTENTIEL/REEL terminée pour concert id={concert_id}")


def mettre_a_jour_credit_calcule_potentiel() -> None:
    """
    Met à jour tous les concerts non payés (potentiels),
    et s'assure que les concerts payés ont bien leur réel calculé et le potentiel remis à 0.
    """
    # Concerts non payés → calcul potentiel
    concerts_non_payes = Concert.query.filter(Concert.paye.is_(False)).all()
    print(f"\n🔍 Concerts non payés trouvés : {len(concerts_non_payes)}")

    for concert in concerts_non_payes:
        _assurer_part_asso7(concert)

        # On met le réel à 0 par précaution
        for part in concert.participations:
            part.credit_calcule = 0.0

        credits, credit_asso7, _ = partage_benefices_concert(concert)
        for part in concert.participations:
            montant = credits.get(part.musicien_id)
            if montant is None and part.musicien and (part.musicien.nom or "").upper() == "ASSO7":
                montant = credit_asso7
            part.credit_calcule_potentiel = float(montant or 0.0)
            print(f"[OK] potentiel → participation id={part.id} → {part.credit_calcule_potentiel:.2f}")

    # Concerts payés → potentiel à 0 + réel recalculé
    concerts_payes = Concert.query.filter(Concert.paye.is_(True)).all()
    print(f"\n💰 Concerts payés trouvés : {len(concerts_payes)}")
    for concert in concerts_payes:
        for part in concert.participations:
            part.credit_calcule_potentiel = 0.0
            print(f"[PAYÉ] participation id={part.id} → 0.0 (potentiel)")
        mettre_a_jour_credit_calcule(concert)

    db.session.commit()
    print("\n✅ Mise à jour des crédits potentiels et réels terminée.")


# --------------------------- Script autonome ---------------------------

def executer_recalcul_complet():
    """Appel global si utilisé comme script autonome."""
    mettre_a_jour_credit_calcule_potentiel()


if __name__ == "__main__":
    from App import app
    with app.app_context():
        executer_recalcul_complet()
