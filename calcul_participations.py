from models import db, Concert, Participation, Musicien

def get_recette_utilisee(concert):
    """Retourne la recette réelle si payée ou présente, sinon la recette attendue (si non payée)."""
    if concert.recette is not None:
        return concert.recette
    elif not concert.paye and concert.recette_attendue is not None:
        return concert.recette_attendue
    return None


def partage_benefices_concert(concert):
    """Renvoie un dictionnaire {musicien_id: montant}, montant_asso7, montant_jerome"""
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
    musiciens = Musicien.query.filter(Musicien.id.in_(musiciens_ids)).all()

    jerome = next((m for m in musiciens if m.nom.upper() == "ARNOULD" and m.prenom.upper().startswith("JÉRÔME")), None)
    asso7 = next((m for m in musiciens if m.nom.upper() == "ASSO7"), None)

    pour_jerome = round(benefices * 0.10, 2) if jerome else 0
    reste = benefices - pour_jerome
    nb_parts = len([m for m in musiciens if m.nom.upper() != "ASSO7"]) + 1
    part = round(reste / nb_parts, 2) if nb_parts else 0

    resultats = {}
    for m in musiciens:
        if m.nom.upper() == "ASSO7":
            continue
        if jerome and m.id == jerome.id:
            resultats[m.id] = round(part + pour_jerome, 2)
        else:
            resultats[m.id] = part

    print(f"[✓] Concert id={concert.id} → part={part}, jerome={pour_jerome}, total_benef={benefices}")
    return resultats, part, pour_jerome


def mettre_a_jour_credit_calcule(concert):
    """Remplit le champ credit_calcule pour un concert PAYÉ"""
    credits, credit_asso7, _ = partage_benefices_concert(concert)
    for part in concert.participations:
        montant = credits.get(part.musicien_id)
        if montant is None and part.musicien.nom.upper() == "ASSO7":
            montant = credit_asso7
        part.credit_calcule = montant or 0.0
        print(f"[✓] crédit réel → participation id={part.id} → {part.credit_calcule:.2f}")
    db.session.commit()


def mettre_a_jour_credit_calcule_potentiel_pour_concert(concert_id):
    """Met à jour le crédit POTENTIEL (si concert non payé), ou vide les potentiels si payé, et recalcule le réel"""
    db.session.expire_all()
    concert = Concert.query.get(concert_id)
    if not concert:
        print(f"[!] Concert id={concert_id} introuvable.")
        return

    print(f"[DEBUG] Concert récupéré id={concert.id}, payé={concert.paye}")
    asso7 = Musicien.query.filter(Musicien.nom.ilike("ASSO7")).first()

    if asso7 and not any(p.musicien_id == asso7.id for p in concert.participations):
        nouvelle_part = Participation(concert_id=concert.id, musicien_id=asso7.id)
        db.session.add(nouvelle_part)
        concert.participations.append(nouvelle_part)
        print(f"[+] Participation ajoutée pour ASSO7 au concert id={concert.id}")

    if concert.paye:
        print("[DEBUG] Bloc concert PAYÉ exécuté")
        for part in concert.participations:
            part.credit_calcule_potentiel = 0.0
        mettre_a_jour_credit_calcule(concert)
    else:
        print("[DEBUG] Bloc concert NON PAYÉ exécuté")
        for part in concert.participations:
            part.credit_calcule = 0.0
            print(f"[RESET] crédit réel participation id={part.id} → 0.0")

        credits, credit_asso7, _ = partage_benefices_concert(concert)
        for part in concert.participations:
            montant = credits.get(part.musicien_id)
            if montant is None and part.musicien.nom.upper() == "ASSO7":
                montant = credit_asso7
            part.credit_calcule_potentiel = montant or 0.0
            print(f"[OK] potentiel → participation id={part.id} → {part.credit_calcule_potentiel:.2f}")

    db.session.commit()
    print(f"[✓] Mise à jour terminée pour concert id={concert_id}")


def mettre_a_jour_credit_calcule_potentiel():
    """Met à jour tous les concerts non payés + vide les potentiels et recalcule le réel pour les concerts payés"""
    concerts_non_payes = Concert.query.filter(Concert.paye == 0).all()
    print(f"\n🔍 Concerts non payés trouvés : {len(concerts_non_payes)}")

    asso7 = Musicien.query.filter(Musicien.nom.ilike("ASSO7")).first()

    for concert in concerts_non_payes:
        if asso7 and not any(p.musicien_id == asso7.id for p in concert.participations):
            nouvelle_part = Participation(concert_id=concert.id, musicien_id=asso7.id)
            db.session.add(nouvelle_part)
            concert.participations.append(nouvelle_part)
            print(f"[+] Participation ajoutée pour ASSO7 au concert id={concert.id}")

        for part in concert.participations:
            part.credit_calcule = 0.0

        credits, credit_asso7, _ = partage_benefices_concert(concert)
        for part in concert.participations:
            montant = credits.get(part.musicien_id)
            if montant is None and part.musicien.nom.upper() == "ASSO7":
                montant = credit_asso7
            part.credit_calcule_potentiel = montant or 0.0
            print(f"[OK] potentiel → participation id={part.id} → {part.credit_calcule_potentiel:.2f}")

    concerts_payes = Concert.query.filter(Concert.paye == 1).all()
    print(f"\n💰 Concerts payés trouvés : {len(concerts_payes)}")
    for concert in concerts_payes:
        for part in concert.participations:
            part.credit_calcule_potentiel = 0.0
            print(f"[PAYÉ] participation id={part.id} → 0.0 (potentiel)")
        mettre_a_jour_credit_calcule(concert)

    db.session.commit()
    print("\n✅ Mise à jour des crédits potentiels et réels terminée.")


def executer_recalcul_complet():
    """Appel global si utilisé comme script autonome"""
    mettre_a_jour_credit_calcule_potentiel()


if __name__ == "__main__":
    from App import app
    with app.app_context():
        executer_recalcul_complet()
