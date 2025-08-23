# ─────────────────────────────────────────────
# 1. 📦 IMPORTS & CONSTANTES
# ─────────────────────────────────────────────

from models import Musicien, Participation, Report, Concert, db
from datetime import date, datetime
from models import Operation
from pathlib import Path
import json
# 📦 Standard Python
import os
import re
import sqlite3
from datetime import datetime
from flask import current_app


# 📦 Librairies tierces
import fitz  # PyMuPDF
from dotenv import load_dotenv
from sqlalchemy import and_, extract, func

# 📁 Modules internes
from models import db, Cachet, Concert, Musicien
from calcul_participations import partage_benefices_concert, mettre_a_jour_credit_calcule_potentiel


# ─────────────────────────────────────────────
# 2. 🗃️ CHARGEMENT / SAUVEGARDE JSON & SQLITE
# ─────────────────────────────────────────────

# def sauvegarder_json(filepath, data):
# def charger_json(filepath):
# def get_operations_dict():
def get_reports_dict(musiciens):
    d = {}
    for m in musiciens:
        report = Report.query.filter_by(musicien_id=m.id).first()
        d[m.id] = report.montant if report else 0.0
    return d


def get_all_dates_from_json(path, champ_dates):
    """
    Extrait toutes les dates présentes dans un fichier JSON (ex: cachets, opérations, ...).
    - path : chemin vers le fichier
    - champ_dates : nom du champ listant les dicts de dates (ex: "details_dates") OU fonction personnalisée à appliquer sur chaque entrée.
    Retourne une liste de dates (datetime.date)
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = []

    dates = []
    for entry in data:
        # Si champ_dates est un nom de champ
        if isinstance(champ_dates, str):
            # S'adapte au format cachets.json qui a une clé "declaration"
            details = entry.get("declaration", entry).get(champ_dates, [])
            for c in details:
                try:
                    dte = datetime.strptime(c["date"], "%Y-%m-%d").date()
                    dates.append(dte)
                except Exception:
                    continue
        # Si champ_dates est une fonction personnalisée
        elif callable(champ_dates):
            ds = champ_dates(entry)
            if isinstance(ds, list):
                dates.extend(ds)
            elif ds:
                dates.append(ds)
    return dates



# ─────────────────────────────────────────────
# 3. 🧾 UTILITAIRES MUSICIENS
# ─────────────────────────────────────────────

from collections import defaultdict
from datetime import date
from models import Musicien, Operation
from sqlalchemy import func


from sqlalchemy import func  # <-- en haut du fichier si pas déjà présent

def get_etat_comptes():
    """Construit le tableau pour /comptes (musiciens + structures)."""
    aujourd_hui = date.today()
    tableau = []

    # On va réutiliser la même liste de concerts pour calculer les crédits
    concerts = Concert.query.all()

    # ---------- MUSICIENS (tout ce qui n'est PAS 'structure') ----------
    musiciens = (
        Musicien.query
        .filter(Musicien.actif.is_(True), Musicien.type != 'structure')
        .order_by(Musicien.nom, Musicien.prenom)
        .all()
    )

    def _sum_ops(musicien_id, *, passees=True):
        """Somme des opérations passées/à venir (credit - debit)."""
        q = Operation.query.filter(Operation.musicien_id == musicien_id)
        if passees:
            q = q.filter(Operation.date <= aujourd_hui)
        else:
            q = q.filter(Operation.date > aujourd_hui)

        total = 0.0
        for op in q.all():
            op_type = (op.type or "").lower().replace("é", "e")
            if op_type == "credit":
                total += op.montant or 0
            elif op_type == "debit":
                total -= op.montant or 0
        return total

    for m in musiciens:
        # Crédit réel = participations réelles + reports + opérations passées
        credit_reel = (db.session.query(func.sum(Participation.credit_calcule))
                       .filter_by(musicien_id=m.id)
                       .scalar() or 0.0)

        report = (db.session.query(func.sum(Report.montant))
                  .filter_by(musicien_id=m.id)
                  .scalar() or 0.0)

        ops_passees = _sum_ops(m.id, passees=True)
        credit_reel += report + ops_passees

        # Gains à venir = participations potentielles + opérations à venir
        gains_potentiels = (db.session.query(func.sum(Participation.credit_calcule_potentiel))
                            .filter_by(musicien_id=m.id)
                            .scalar() or 0.0)
        ops_avenir = _sum_ops(m.id, passees=False)
        gains_potentiels += ops_avenir

        tableau.append({
            "nom": f"{(m.prenom or '').strip()} {(m.nom or '').strip()}".strip(),
            "credit": credit_reel,
            "gains_a_venir": gains_potentiels,
            "credit_potentiel": credit_reel + gains_potentiels,
            "structure": False
        })

    # ---------- SÉPARATEUR VISUEL ----------
    tableau.append({"separateur": True})

    # ---------- STRUCTURES (hors spéciaux) ----------
    structures = (
        Musicien.query
        .filter(
            Musicien.type == 'structure',
            ~Musicien.nom.in_(["CB ASSO7", "CAISSE ASSO7", "TRESO ASSO7"])
        )
        .order_by(Musicien.nom)
        .all()
    )

    for s in structures:
        # Crédit actuel coté structure (utilise ta logique existante)
        credit = calculer_credit_actuel(s, concerts)

        # Report associé à la structure
        report_s = (db.session.query(func.sum(Report.montant))
                    .filter_by(musicien_id=s.id)
                    .scalar() or 0.0)
        credit += report_s

        # Gains à venir = participations potentielles + opérations à venir
        gains_a_venir = (db.session.query(func.sum(Participation.credit_calcule_potentiel))
                         .filter_by(musicien_id=s.id)
                         .scalar() or 0.0)
        gains_a_venir += _sum_ops(s.id, passees=False)

        tableau.append({
            "nom": (s.nom or "").strip(),
            "credit": credit,
            "gains_a_venir": gains_a_venir,
            "credit_potentiel": credit + gains_a_venir,
            "structure": True
        })

    # ---------- STRUCTURES SPÉCIALES ----------
    cb_asso7 = Musicien.query.filter_by(nom="CB ASSO7").first()
    caisse_asso7 = Musicien.query.filter_by(nom="CAISSE ASSO7").first()

    # --- CB ASSO7 ---
    if cb_asso7:
        credit_cb = calculer_credit_actuel(cb_asso7, concerts)
        report_cb = (db.session.query(func.sum(Report.montant))
                     .filter_by(musicien_id=cb_asso7.id)
                     .scalar() or 0.0)
        credit_cb += report_cb

        recettes_a_venir_cb = (db.session.query(func.sum(Concert.recette_attendue))
                               .filter(Concert.paye.is_(False),
                                       Concert.mode_paiement_prevu == "CB ASSO7")
                               .scalar() or 0.0)
        tableau.append({
            "nom": "CB ASSO7",
            "credit": credit_cb,
            "gains_a_venir": recettes_a_venir_cb,
            "credit_potentiel": credit_cb + recettes_a_venir_cb,
            "structure": True
        })

    # --- CAISSE ASSO7 ---
    if caisse_asso7:
        credit_caisse = calculer_credit_actuel(caisse_asso7, concerts)
        report_caisse = (db.session.query(func.sum(Report.montant))
                         .filter_by(musicien_id=caisse_asso7.id)
                         .scalar() or 0.0)
        credit_caisse += report_caisse

        recettes_a_venir_caisse = (db.session.query(func.sum(Concert.recette_attendue))
                                   .filter(Concert.paye.is_(False),
                                           Concert.mode_paiement_prevu == "CAISSE ASSO7")
                                   .scalar() or 0.0)
        tableau.append({
            "nom": "CAISSE ASSO7",
            "credit": credit_caisse,
            "gains_a_venir": recettes_a_venir_caisse,
            "credit_potentiel": credit_caisse + recettes_a_venir_caisse,
            "structure": True
        })

    # --- TRESO ASSO7 = CB + CAISSE ---
    if cb_asso7 or caisse_asso7:
        # Recalcule à partir des lignes qu’on vient de pousser
        cb_row = next((r for r in tableau if r.get("nom") == "CB ASSO7"), None)
        caisse_row = next((r for r in tableau if r.get("nom") == "CAISSE ASSO7"), None)

        treso_credit = (cb_row["credit"] if cb_row else 0.0) + (caisse_row["credit"] if caisse_row else 0.0)
        treso_gains = (cb_row["gains_a_venir"] if cb_row else 0.0) + (caisse_row["gains_a_venir"] if caisse_row else 0.0)

        tableau.append({
            "nom": "TRESO ASSO7",
            "credit": treso_credit,
            "gains_a_venir": treso_gains,
            "credit_potentiel": treso_credit + treso_gains,
            "structure": True
        })

    return tableau




def get_musiciens_dict():
    return {m.id: m for m in Musicien.query.all()}

def calculer_credit_actuel(musicien, concerts):
    if musicien is None:
        # Cas où l'ID ou l'objet musicien est introuvable → on renvoie 0
        # ou on pourrait logger un avertissement si besoin
        return 0.0

    aujourd_hui = date.today()
    credit = 0.0

    nom = (musicien.nom or "").strip().upper()

    # Cas spéciaux : CAISSE ASSO7, TRESO ASSO7
    if nom in ["CAISSE ASSO7", "CB ASSO7", "TRESO ASSO7"]:
        operations = Operation.query.filter_by(musicien_id=musicien.id).all()
        for op in operations:
            if op.date <= aujourd_hui:
                if (op.type or "").lower() == "debit":
                    credit -= op.montant or 0
                elif (op.type or "").lower() == "credit":
                    credit += op.montant or 0
        return credit

    # Pour tous les autres musiciens/structures classiques
    for concert in concerts:
        # CREDIT ACTUEL : on ne prend QUE les concerts payés ET dont la date est passée ou aujourd'hui
        if concert.paye and concert.date <= aujourd_hui:
            credits, credit_asso7, _ = partage_benefices_concert(concert)
            if nom == "ASSO7":
                credit += credit_asso7 or 0
            else:
                credit += credits.get(musicien.id, 0)

    report = Report.query.filter_by(musicien_id=musicien.id).first()
    if report:
        credit += report.montant or 0.0

    operations = Operation.query.filter_by(musicien_id=musicien.id).all()
    for op in operations:
        if op.date <= aujourd_hui:
            op_type = (op.type or "").lower()
            if op_type == "debit":
                if not getattr(op, "auto_cb_asso7", False):
                    credit -= op.montant or 0
            elif op_type == "credit":
                if not getattr(op, "auto_cb_asso7", False):
                    credit += op.montant or 0

    return credit


def calculer_gains_a_venir(musicien, concerts):
    aujourd_hui = date.today()
    credit = 0.0

    nom = (musicien.nom or "").strip().upper()

    # Cas spécial : CB ASSO7 et CAISSE ASSO7 → gains virtuels sur TOUS les concerts non payés, passés ou à venir
    if nom in ["CB ASSO7", "CAISSE ASSO7"]:
        for concert in concerts:
            # Concert non payé, recette renseignée, et mode_paiement_prevu = ce compte
            if (not getattr(concert, "paye", False)
                and getattr(concert, "recette", None)
                and getattr(concert, "mode_paiement_prevu", None)
                and concert.mode_paiement_prevu.strip().upper() == nom):
                credit += concert.recette or 0
        # Optionnel : tu peux garder ici les opérations à venir (ex : virements programmés, etc.)
        operations = Operation.query.filter_by(musicien_id=musicien.id).all()
        for op in operations:
            if op.date > aujourd_hui:
                if (op.type or "").lower() == "debit":
                    credit -= op.montant or 0
                elif (op.type or "").lower() == "credit":
                    credit += op.montant or 0
        return credit

    # Cas spécial : TRESO ASSO7 (somme CB + CAISSE) — probablement déjà géré ailleurs

    # Cas ASSO7 ou musiciens classiques : logique existante (cachets, part des concerts futurs non encore payés, etc.)
    for concert in concerts:
        # On conserve la logique précédente pour ASSO7/musiciens
        # (tu peux affiner selon tes besoins, par exemple inclure part de la recette d’un concert non payé…)
        if (not concert.paye and concert.date > aujourd_hui) or (concert.paye and concert.date > aujourd_hui):
            credits, credit_asso7, _ = partage_benefices_concert(concert)
            if nom == "ASSO7":
                credit += credit_asso7 or 0
            else:
                credit += credits.get(musicien.id, 0)

    # On ajoute aussi les opérations à venir
    operations = Operation.query.filter_by(musicien_id=musicien.id).all()
    for op in operations:
        if op.date > aujourd_hui:
            if (op.type or "").lower() == "debit":
                credit -= op.montant or 0
            elif (op.type or "").lower() == "credit":
                credit += op.montant or 0

    return credit






def verifier_ou_creer_structures():
    """
    Vérifie si ASSO7 et CB ASSO7 existent, sinon les crée comme musiciens 'structure'.
    """
    noms_structures = ['ASSO7', 'CB ASSO7']
    for nom in noms_structures:
        existant = Musicien.query.filter_by(nom=nom).first()
        if not existant:
            nouveau = Musicien(nom=nom, prenom='', actif=True, type='structure')
            db.session.add(nouveau)
            print(f"✅ Création automatique : {nom}")
    db.session.commit()

def calculer_credit_potentiel(musicien, concerts):
    """
    Le crédit potentiel est défini comme la somme du crédit actuel et des gains à venir.
    """
    return calculer_credit_actuel(musicien, concerts) + calculer_gains_a_venir(musicien, concerts)


def format_currency(value):
    try:
        if value is None:
            return ''
        return f"{value:,.2f} €".replace(',', ' ').replace('.', ',')
    except Exception:
        return str(value)

def musicien_to_dict(musicien):
    """Convertit un objet Musicien SQLAlchemy en dictionnaire."""
    return {
        "id": musicien.id,
        "prenom": musicien.prenom,
        "nom": musicien.nom,
        "actif": musicien.actif,
        "type": musicien.type,
        "credit_actuel": musicien.credit_actuel,
        "gains_a_venir": musicien.gains_a_venir,
        "credit_potentiel": musicien.credit_potentiel
    }


def preparer_concerts_par_musicien():
    """
    Prépare un mapping { 'Prénom Nom': [ {id, date, lieu}... ] }
    pour tous les concerts auxquels chaque musicien a participé.
    """
    concerts = Concert.query.all()
    mapping = {}

    for concert in concerts:
        for participation in concert.participations:
            musicien = participation.musicien
            if not musicien:
                continue
            nom_complet = f"{(musicien.prenom or '').strip()} {(musicien.nom or '').strip()}".strip()
            if nom_complet not in mapping:
                mapping[nom_complet] = []
            mapping[nom_complet].append({
                "id": concert.id,
                "date": concert.date.isoformat(),
                "lieu": concert.lieu
            })

    return mapping




# ─────────────────────────────────────────────
# 4. 🎤 GESTION DES CONCERTS & PARTICIPATIONS
# ─────────────────────────────────────────────


    
def get_credits_concerts_from_db(concerts):
    credits_musiciens = {}
    credits_asso7 = {}
    credits_jerome = {}

    for concert in concerts:
        credits = {}
        credit_asso7 = 0.0
        credit_jerome = 0.0

        for part in concert.participations:
            # 🔁 Utilise le bon champ selon l’état du concert
            montant = (
                part.credit_calcule if concert.paye else part.credit_calcule_potentiel
            ) or 0.0

            musicien = part.musicien
            nom = (musicien.nom or "").strip().upper()
            prenom = (musicien.prenom or "").strip().upper()

            if nom == "ASSO7":
                credit_asso7 = montant
            elif nom == "ARNOULD" and prenom.startswith("JÉRÔME"):
                credit_jerome = montant
                credits[musicien.id] = montant
            else:
                credits[musicien.id] = montant

        credits_musiciens[concert.id] = credits
        credits_asso7[concert.id] = credit_asso7
        credits_jerome[concert.id] = credit_jerome

    return credits_musiciens, credits_asso7, credits_jerome



def enregistrer_participations(concert_id, participants_ids, jerome_id=None):
    Participation.query.filter_by(concert_id=concert_id).delete()
    if jerome_id:
        participants_ids.add(jerome_id)
    for musicien_id in participants_ids:
        db.session.add(Participation(concert_id=concert_id, musicien_id=musicien_id))
    db.session.commit()
# def get_operations_concert(concert_id):
# def partage_benefices_concert(concert_id):

def concerts_groupes_par_mois(concerts):
    """Renvoie un OrderedDict { 'Mois Année': [concerts...] } trié chronologiquement."""
    from collections import OrderedDict

    groupes = {}
    for concert in concerts:
        mois_label = f"{MOIS_FR[concert.date.month - 1].capitalize()} {concert.date.year}"
        if mois_label not in groupes:
            groupes[mois_label] = []
        groupes[mois_label].append(concert)

    # Trie par année, puis par mois
    def mois_key(label):
        nom_mois, annee = label.split()
        mois_num = MOIS_FR.index(nom_mois.lower()) + 1
        return (int(annee), mois_num)
    groupes_tries = OrderedDict(
        sorted(groupes.items(), key=lambda x: mois_key(x[0]))
    )
    return groupes_tries

def recalculer_frais_concert(concert_id, op_to_remove_id=None):
    """
    Recalcule la somme des opérations de type 'Frais' associées au concert,
    en excluant éventuellement l'opération supprimée, et met à jour la colonne `frais` dans la table `concert`.
    """
    # Récupérer le concert
    concert = Concert.query.get(concert_id)
    if concert is None:
        print(f"❌ Le concert {concert_id} n'existe pas")
        return  # Si le concert n'existe pas, on ne fait rien

    # Calcul des frais actuels avant la suppression
    frais_total = db.session.query(db.func.sum(Operation.montant)).filter(
        Operation.concert_id == concert_id,
        Operation.motif == "Frais"
    ).scalar()

    if frais_total is None:
        frais_total = 0.0

    print(f"✅ Frais actuels avant suppression : {frais_total} €")

    # Si une opération a été supprimée, on la retire des frais actuels
    if op_to_remove_id:
        operation_to_remove = Operation.query.get(op_to_remove_id)
        if operation_to_remove and operation_to_remove.motif == "Frais":
            print(f"⛔ Suppression de l'opération {operation_to_remove_id} de type 'Frais' : {operation_to_remove.montant} €")
            frais_total -= operation_to_remove.montant  # Déduire le montant de l'opération supprimée
            print(f"✅ Nouveau total des frais après suppression : {frais_total} €")

    # Mettre à jour le champ `frais` du concert
    try:
        concert.frais = frais_total
        db.session.commit()
        print(f"✅ Frais mis à jour pour le concert {concert_id} : {frais_total} €")
    except Exception as e:
        print(f"❌ Erreur lors de la mise à jour des frais pour le concert {concert_id} :", e)

def concerts_non_payes(concerts):
    """Retourne les concerts passés et non payés."""
    today = datetime.today().date()
    return [c for c in concerts if c.date < today and not c.paye]

def concert_to_dict(concert):
    """Convertit un objet Concert SQLAlchemy en dictionnaire utilisable côté JS/template."""
    return {
        "id": concert.id,
        "date": concert.date.strftime("%d/%m/%Y") if concert.date else "",
        "lieu": concert.lieu,
        "recette": concert.recette,
        "recette_attendue": concert.recette_attendue,
        "paye": concert.paye,
    }

# ─────────────────────────────────────────────
# 5. 💸 GESTION DES OPÉRATIONS
# ─────────────────────────────────────────────

from calcul_participations import mettre_a_jour_credit_calcule_potentiel_pour_concert

def enregistrer_operation_en_db(data):
    nom_saisi = (data.get("musicien") or "").strip().lower()
    musiciens = Musicien.query.all()

    cible = next(
        (m for m in musiciens if f"{(m.prenom or '').strip()} {(m.nom or '').strip()}".strip().lower() == nom_saisi),
        None
    )
    if not cible:
        raise ValueError(f"Musicien introuvable pour le nom : {data['musicien']}")

    # 📆 Conversion date au format YYYY-MM-DD
    if "/" in data["date"]:
        try:
            jour, mois, annee = data["date"].split("/")
            data["date"] = f"{annee}-{mois.zfill(2)}-{jour.zfill(2)}"
        except Exception as e:
            print("Erreur de conversion date :", data["date"], e)
            raise

    date_op = datetime.strptime(data["date"], "%Y-%m-%d").date()
    type_op = data.get("type", "").lower()
    motif = data.get("motif")
    cible_nom_normalise = (cible.nom or "").strip().lower()
    concert_id = data.get("concert_id")

    # 🎯 Déduction automatique du type selon le motif
    if motif == "Frais":
        type_op = "debit" if cible_nom_normalise in ["cb asso7", "caisse asso7"] else "credit"
    elif motif == "Recette concert":
        type_op = "credit"
    elif motif == "Salaire":
        type_op = "debit"

    op = Operation(
        musicien_id=cible.id,
        type=type_op,
        motif=motif,
        precision=data.get("precision", ""),
        montant=float(data["montant"]),
        date=date_op,
        brut=float(data["brut"]) if data.get("brut") else None,
        concert_id=concert_id
    )
    db.session.add(op)
    db.session.flush()

    # 💸 Commission Lionel sur salaire brut
    is_salaire = motif == "Salaire"
    has_brut = data.get("brut") and float(data["brut"]) > 0
    if is_salaire and has_brut:
        commission = round(float(data["brut"]) * 0.03, 2)
        commission_debit = Operation(
            musicien_id=cible.id,
            type="debit",
            motif="Commission Lionel",
            precision="3% brut salaire",
            montant=commission,
            date=date_op,
            operation_liee_id=op.id
        )
        db.session.add(commission_debit)

        lionel = next((m for m in musiciens if f"{(m.prenom or '').strip()} {(m.nom or '').strip()}".lower() == "lionel arnould"), None)
        if lionel:
            commission_credit = Operation(
                musicien_id=lionel.id,
                type="credit",
                motif="Commission Lionel",
                precision=f"3% brut de {data['musicien']}",
                montant=commission,
                date=date_op,
                operation_liee_id=op.id
            )
            db.session.add(commission_credit)

    # 🔄 Débit automatique sur CB ASSO7 ou CAISSE ASSO7 si Salaire
    if is_salaire and cible_nom_normalise not in ["cb asso7", "caisse asso7"]:
        mode = data.get("mode", "Compte")
        cible_debit = None
        if mode == "Compte":
            cible_debit = next((m for m in musiciens if (m.nom or "").strip().lower() == "cb asso7"), None)
        elif mode == "Espèces":
            cible_debit = next((m for m in musiciens if (m.nom or "").strip().lower() == "caisse asso7"), None)

        if cible_debit:
            db.session.flush()
            debit_salaire = Operation(
                musicien_id=cible_debit.id,
                type="debit",
                motif=f"Débit Salaire {data['musicien']}",
                precision=f"Salaire payé à {data['musicien']}",
                montant=float(data["montant"]),
                date=date_op,
                operation_liee_id=op.id,
                auto_debit_salaire=True
            )
            db.session.add(debit_salaire)

            # 🛠️ Lien vers op principal, mais PAS de réajout
            op.operation_liee_id = debit_salaire.id

    # 🧾 Mise à jour frais sur concert si motif = Frais
    if motif.lower() == "frais" and concert_id:
        try:
            concert = Concert.query.get(concert_id)
            if concert:
                concert.frais = (concert.frais or 0.0) + float(data["montant"])
                db.session.add(concert)
        except Exception as e:
            print("⚠️ Erreur mise à jour frais concert:", e)

    # 💡 Si Recette concert : marquer le concert comme payé
    if motif == "Recette concert" and concert_id:
        concert = Concert.query.get(concert_id)
        if concert:
            print(f"[DEBUG] Bloc 'Recette concert' exécuté pour concert_id={concert_id}, payé={concert.paye}")
            if not concert.paye:
                concert.paye = True
                db.session.add(concert)
                print(f"[✓] Concert {concert_id} marqué comme payé")

    # 💾 Enregistrement global + recalcul
    try:
        db.session.commit()
        print(f"[OK] Operation {motif} enregistrée pour {data['musicien']}")

        if concert_id:
            db.session.expire_all()
            concert_verif = Concert.query.get(concert_id)
            print(f"[CHECK] Avant recalcul → concert_id={concert_id}, payé={concert_verif.paye}")
            mettre_a_jour_credit_calcule_potentiel_pour_concert(concert_id)
    except Exception as e:
        db.session.rollback()
        print(f"❌ Erreur lors de l'enregistrement de l'opération : {e}")
        raise




def annuler_operation(id):
    operation = db.session.get(Operation, id)
    if not operation:
        print(f"❌ Opération ID={id} introuvable.")
        return False

    concert_id = operation.concert_id
    etait_recette = operation.motif == "Recette concert"

    # Supprime toutes les opérations liées
    if operation.operation_liee_id:
        liee = db.session.get(Operation, operation.operation_liee_id)
        if liee:
            db.session.delete(liee)

    liees_inverse = Operation.query.filter_by(operation_liee_id=operation.id).all()
    for op_liee in liees_inverse:
        db.session.delete(op_liee)

    # Si frais, déduire du concert
    if operation.motif.lower() == "frais" and concert_id:
        concert = Concert.query.get(concert_id)
        if concert and concert.frais:
            concert.frais = max(0.0, concert.frais - (operation.montant or 0.0))
            db.session.add(concert)

    db.session.delete(operation)
    db.session.commit()

    # Si c'était une recette de concert, on remet le concert en "non payé"
    if etait_recette and concert_id:
        concert = Concert.query.get(concert_id)
        if concert:
            concert.paye = False
            db.session.add(concert)
            db.session.commit()
            # Recalcul des crédits potentiels
            try:
                from calcul_participations import mettre_a_jour_credit_calcule_potentiel
                print(f"[INFO] Recalcul des participations potentielles pour concert {concert.id}")
                mettre_a_jour_credit_calcule_potentiel(concert)
                db.session.commit()
            except Exception as e:
                print(f"⚠️ Erreur recalcul concert {concert.id} après suppression recette :", e)

    return True


def formulaire_to_data(request_form):
    data = request_form.to_dict()
    data["montant"] = float(data.get("montant", 0))

    if "brut" in data and data["brut"]:
        data["brut"] = float(data["brut"])
    else:
        data["brut"] = None

    data["concert_id"] = int(data["concert_id"]) if data.get("concert_id") else None
    return data

def charger_musiciens_et_concerts_sqlite(chemin_db):
    musiciens, concerts = [], []
    try:
        conn = sqlite3.connect(chemin_db)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT prenom, nom FROM musicien WHERE actif=1")
        musiciens = cursor.fetchall()
        cursor.execute("SELECT id, date, lieu FROM concert ORDER BY date DESC")
        concerts = cursor.fetchall()
    except Exception as e:
        print("⚠️ Erreur chargement musiciens/concerts :", e)
    finally:
        try:
            conn.close()
        except:
            pass
    return musiciens, concerts


def separer_structures_et_musiciens(musiciens):
    """
    Prend une liste de musiciens et les sépare par leur champ 'type' (musicien ou structure).
    """
    musiciens_normaux = []
    structures = []

    for m in musiciens:
        # Accès tolérant selon type (objet ou dict)
        type_val = m["type"] if isinstance(m, dict) else getattr(m, "type", None)
        if type_val == "structure":
            structures.append(m)
        else:
            musiciens_normaux.append(m)

    return musiciens_normaux, structures


def preparer_concerts_js(concerts):
    """Prépare les données des concerts au format JSON pour le frontend, que ce soit des objets ou des dicts."""
    concerts_js = []

    for c in concerts:
        get = lambda attr, default=None: (
            getattr(c, attr, default) if not isinstance(c, dict) else c.get(attr, default)
        )

        date_val = get("date")
        concerts_js.append({
            "id": get("id"),
            "date": date_val.isoformat() if hasattr(date_val, 'isoformat') else date_val,
            "lieu": get("lieu"),
            "recette": get("recette"),
            "frais": get("frais"),
            "paye": get("paye")
        })

    return concerts_js




def preparer_concerts_data():
    return [
        {
            "id": c.id,
            "date": c.date.isoformat() if hasattr(c.date, 'isoformat') else str(c.date),
            "lieu": c.lieu,
            "musiciens": [
                f"{(p.musicien.prenom or '').strip()} {(p.musicien.nom or '').strip()}"
                for p in c.participations if p.musicien is not None
            ],
        }
        for c in Concert.query.all()
    ]

def modifier_operation_en_db(operation_id, form_data):
    # Copie modifiable
    data = dict(form_data)

    # Conversion de la date JJ/MM/AAAA → AAAA-MM-JJ
    if "date" in data and "/" in data["date"]:
        jour, mois, annee = data["date"].split("/")
        data["date"] = f"{annee}-{mois.zfill(2)}-{jour.zfill(2)}"

    # --- Récupération de l'opération principale
    op = db.session.get(Operation, operation_id)
    if not op:
        raise ValueError(f"Opération ID={operation_id} introuvable.")

    # --- Récupération de tous les musiciens
    musiciens = Musicien.query.all()

    # --- Détermination du musicien cible ---
    musicien_id = data.get("musicien")         # Ici, on attend un ID (str)
    nom_saisi = (data.get("musicien_nom") or "").strip().lower()  # Ancien fallback

    cible = None
    if musicien_id:
        # Cherche d'abord par ID
        cible = next((m for m in musiciens if str(m.id) == str(musicien_id)), None)
        if not cible:
            # Cas legacy : nom complet dans "musicien"
            cible = next(
                (m for m in musiciens if f"{m.prenom} {m.nom}".strip().lower() == musicien_id.strip().lower()),
                None
            )
    elif nom_saisi:
        # Fallback pour les vieux formulaires où seul le nom serait transmis
        cible = next(
            (m for m in musiciens if f"{(m.prenom or '').strip()} {(m.nom or '').strip()}".strip().lower() == nom_saisi),
            None
        )

    if not cible:
        raise ValueError(f"Musicien introuvable pour l'identifiant '{musicien_id}' ou le nom : '{nom_saisi}'")

    # Conversion date si nécessaire (à ce stade, data["date"] est au bon format)
    try:
        date_op = datetime.strptime(data["date"], "%Y-%m-%d").date()
    except Exception as e:
        print("Erreur de conversion date :", data["date"], e)
        raise

    # --- MAJ de l’opération principale (sans commit)
    type_op = data.get("type", "").lower()
    motif = data.get("motif")
    cible_nom_normalise = (cible.nom or "").strip().lower()

    # Type selon motif (même logique que la création)
    if motif == "Frais":
        if cible_nom_normalise in ["cb asso7", "caisse asso7"]:
            type_op = "debit"
        else:
            type_op = "credit"
    elif motif == "Recette concert":
        type_op = "credit"
    elif motif == "Salaire":
        type_op = "debit"

    op.musicien = cible
    op.date = date_op
    op.type = type_op
    op.mode = data.get("mode")
    op.motif = data.get("motif")
    op.precision = data.get("precision")
    op.montant = data.get("montant")
    op.brut = data.get("brut")

    # --- Supprimer les opérations techniques liées existantes ---
    operations_techniques = Operation.query.filter_by(operation_liee_id=op.id).all()
    for op_tech in operations_techniques:
        db.session.delete(op_tech)
    db.session.flush()

    # --- Génération des opérations techniques (comme lors de la création) ---
    is_salaire = motif == "Salaire"
    has_brut = data.get("brut") and float(data["brut"]) > 0
    if is_salaire and has_brut:
        commission = round(float(data["brut"]) * 0.03, 2)
        commission_debit = Operation(
            musicien_id=cible.id,
            type="debit",
            motif="Commission Lionel",
            precision="3% brut salaire",
            montant=commission,
            date=date_op,
            operation_liee_id=op.id
        )
        db.session.add(commission_debit)

        lionel = next((m for m in musiciens if f"{(m.prenom or '').strip()} {(m.nom or '').strip()}".lower() == "lionel arnould"), None)
        if lionel:
            commission_credit = Operation(
                musicien_id=lionel.id,
                type="credit",
                motif="Commission Lionel",
                precision=f"3% brut de {data.get('musicien')}",
                montant=commission,
                date=date_op,
                operation_liee_id=op.id
            )
            db.session.add(commission_credit)

    # 🔥 DÉBIT AUTOMATIQUE du compte payeur (CB ASSO7 ou CAISSE ASSO7) lors d'un salaire
    if motif == "Salaire" and cible_nom_normalise not in ["cb asso7", "caisse asso7"]:
        mode = data.get("mode", "Compte")
        cible_debit = None
        if mode == "Compte":
            cible_debit = next((m for m in musiciens if (m.nom or "").strip().lower() == "cb asso7"), None)
        elif mode == "Espèces":
            cible_debit = next((m for m in musiciens if (m.nom or "").strip().lower() == "caisse asso7"), None)
        if cible_debit:
            db.session.flush()
            debit_salaire = Operation(
                musicien_id=cible_debit.id,
                type="debit",
                motif=f"Débit Salaire {data.get('musicien')}",
                precision=f"Salaire payé à {data.get('musicien')}",
                montant=float(data["montant"]),
                date=date_op,
                operation_liee_id=op.id,
                auto_debit_salaire=True
            )
            db.session.add(debit_salaire)
            op.operation_liee_id = debit_salaire.id
            db.session.add(op)

    # 🎫 FRAIS DE CONCERT
    if motif.lower() == "frais" and data.get("concert_id"):
        try:
            concert = Concert.query.get(data["concert_id"])
            if concert:
                recalculer_frais_concert(concert.id)
        except Exception as e:
            print("⚠️ Erreur mise à jour frais concert:", e)

    db.session.commit()

    # ✅ Recalcul du partage du concert concerné (après commit et rechargement)
    concert_id = data.get("concert_id")
    if concert_id:
        try:
            from calcul_participations import partage_benefices_concert, mettre_a_jour_credit_calcule_potentiel
            db.session.expire_all()  # 🔄 force la recharge de l’état réel du concert
            concert = Concert.query.get(concert_id)
            if concert:
                if concert.paye:
                    print(f"🎯 Recalcul du crédit RÉEL pour concert payé ID={concert.id}")
                    partage_benefices_concert(concert)
                else:
                    print(f"🎯 Recalcul du crédit POTENTIEL pour concert non payé ID={concert.id}")
                    mettre_a_jour_credit_calcule_potentiel(concert)
                db.session.commit()
        except Exception as e:
            print(f"⚠️ Erreur lors du recalcul du partage pour concert ID={concert_id} :", e)


    return op



# ─────────────────────────────────────────────
# 6. 📅 ARCHIVAGE / SAISONS
# ─────────────────────────────────────────────


def get_saison_actuelle():
    """
    Renvoie la saison actuelle au format '2023/2024' en fonction de la date d'aujourd'hui.
    """
    aujourd_hui = date.today()
    return saison_from_date(aujourd_hui)

def get_debut_fin_saison(saison):
    """Retourne les dates de début et fin de saison à partir d'une chaîne '2023/24' ou '23-24'"""
    if "-" in saison:
        saison = saison.replace("-", "/")

    try:
        debut_annee = int("20" + saison.split("/")[0][-2:])
        debut_saison = datetime(debut_annee, 9, 1)
        fin_saison = datetime(debut_annee + 1, 8, 31, 23, 59, 59)
        print(f"🔍 Début saison : {debut_saison}, Fin saison : {fin_saison}")
        return debut_saison, fin_saison
    except Exception as e:
        print(f"⚠️ Erreur parsing saison '{saison}' : {e}")
        return None, None


def saisons_from_dates(dt):
    """
    Reçoit une date (datetime.date) et renvoie la saison au format '2023-2024'.
    """
    if dt.month < 9:
        return f"{dt.year-1}-{dt.year}"
    else:
        return f"{dt.year}-{dt.year+1}"


MOIS_FR = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre"
]

    
def saison_from_date(dt):
    """
    Reçoit une date (datetime.date) et renvoie la saison correspondante au format '2023/2024'.
    """
    if dt.month < 9:
        return f"{dt.year - 1}/{dt.year}"
    else:
        return f"{dt.year}/{dt.year + 1}"

def charger_concerts():
    chemin = Path("data/concerts.json")
    if not chemin.exists():
        return []
    with open(chemin, "r", encoding="utf-8") as f:
        concerts = json.load(f)
    return concerts

# ─────────────────────────────────────────────
# 7.   COMPTES
# ─────────────────────────────────────────────
def generer_tableau_comptes():
    """
    Génère la liste des comptes pour chaque musicien et structure,
    avec CAISSE ASSO7 et TRESO ASSO7 toujours présents en bas, même à 0.
    Retourne :
        - tableau_comptes : liste de dictionnaires avec crédits et infos.
        - musiciens_length : nombre de musiciens dans la liste (utile pour affichage).
    """
    concerts = Concert.query.all()
    musiciens = [m for m in Musicien.query.filter_by(actif=True, type='musicien').all()]

    noms_structures = ['ASSO7', 'CB ASSO7', 'CAISSE ASSO7', 'TRESO ASSO7']
    structures_dict = {nom: Musicien.query.filter_by(nom=nom).first() for nom in noms_structures}

    tableau_comptes = []
    # 1. Tous les musiciens physiques
    for m in musiciens:
        tableau_comptes.append({
            'nom': f"{m.prenom} {m.nom}".strip(),
            'credit_actuel': calculer_credit_actuel(m, concerts),
            'gains_a_venir': calculer_gains_a_venir(m, concerts),
            'credit_potentiel': calculer_credit_potentiel(m, concerts),
            'type': 'musicien'
        })

    musiciens_length = len(tableau_comptes)
    
    # --- Ajout virtuel des gains à venir des recettes concerts à venir aux structures CB ASSO7 ou CAISSE ASSO7 ---
    for concert in concerts:
        if not concert.paye and concert.recette and concert.mode_paiement_prevu:
            # On crédite le "gains_a_venir" du bon compte structure (CB ASSO7 ou CAISSE ASSO7)
            for ligne in tableau_comptes:
                if ligne['nom'] == concert.mode_paiement_prevu:
                    ligne['gains_a_venir'] += float(concert.recette)
            # Et aussi pour TRESO ASSO7 (qui additionne CB et CAISSE)
            # --> ce sera pris en compte plus bas par la somme des deux
    

    # 2. Structures spéciales (sauf TRESO ASSO7)
    for nom in ['ASSO7', 'CB ASSO7', 'CAISSE ASSO7']:
        s = structures_dict.get(nom)
        if s:
            tableau_comptes.append({
                'nom': s.nom,
                'credit_actuel': calculer_credit_actuel(s, concerts),
                'gains_a_venir': calculer_gains_a_venir(s, concerts),
                'credit_potentiel': calculer_credit_potentiel(s, concerts),
                'type': 'structure'
            })
        else:
            tableau_comptes.append({
                'nom': nom,
                'credit_actuel': 0.0,
                'gains_a_venir': 0.0,
                'credit_potentiel': 0.0,
                'type': 'structure'
            })

    # 3. Ligne TRESO ASSO7 = somme CB ASSO7 + CAISSE ASSO7
    cb = structures_dict.get('CB ASSO7')
    caisse = structures_dict.get('CAISSE ASSO7')

    # On recalcule ici, même si la structure n'existe pas (reste à 0)
    if cb:
        credit_actuel_cb = calculer_credit_actuel(cb, concerts)
        gains_a_venir_cb = calculer_gains_a_venir(cb, concerts)
        credit_potentiel_cb = calculer_credit_potentiel(cb, concerts)
    else:
        credit_actuel_cb = gains_a_venir_cb = credit_potentiel_cb = 0.0

    if caisse:
        credit_actuel_caisse = calculer_credit_actuel(caisse, concerts)
        gains_a_venir_caisse = calculer_gains_a_venir(caisse, concerts)
        credit_potentiel_caisse = calculer_credit_potentiel(caisse, concerts)
    else:
        credit_actuel_caisse = gains_a_venir_caisse = credit_potentiel_caisse = 0.0

    # Ajoute la ligne TRESO ASSO7 toujours, même si non présente dans la base
    tableau_comptes.append({
        'nom': 'TRESO ASSO7',
        'credit_actuel': credit_actuel_cb + credit_actuel_caisse,
        'gains_a_venir': gains_a_venir_cb + gains_a_venir_caisse,
        'credit_potentiel': credit_potentiel_cb + credit_potentiel_caisse,
        'type': 'structure'
    })

    return tableau_comptes, musiciens_length


# ─────────────────────────────────────────────
# 8.   CACHETS
# ─────────────────────────────────────────────



def verifier_cachet_existant(session, musicien_id, date_iso):
    """Renvoie True si un cachet pour ce musicien à cette date existe déjà."""
    return session.query(Cachet).filter(
        and_(
            Cachet.musicien_id == musicien_id,
            Cachet.date == date_iso
        )
    ).first() is not None




def get_tous_musiciens_actifs():
    """
    Retourne uniquement les musiciens actifs de type 'musicien',
    triés par prénom puis nom.
    """
    return Musicien.query.filter_by(actif=True, type="musicien").order_by(Musicien.prenom, Musicien.nom).all()
    

    


def get_dernier_cachet_musicien(musicien_id):
    """Retourne le dernier montant de cachet pour un musicien donné (ou None)."""
    dernier = db.session.query(Cachet).filter_by(musicien_id=musicien_id).order_by(Cachet.date.desc()).first()
    return dernier.montant if dernier else None

def ajouter_cachets(musicien_id, dates, montant, nombre_cachets): 
    print("🔥 La fonction `ajouter_cachets` a bien été appelée")
    doublons = []

    for dt in dates:
        # Vérifie s’il existe déjà un cachet à cette date pour ce musicien
        existe = Cachet.query.filter_by(musicien_id=musicien_id, date=dt).first()
        if existe:
            doublons.append(dt)
        else:
            print(f" - {dt} : {montant}€ x{nombre_cachets}")
            cachet = Cachet(
                musicien_id=musicien_id,
                date=dt,
                montant=montant,
                nombre=1
            )
            db.session.add(cachet)

    if doublons:
        db.session.rollback()
        raise ValueError("Cachet déjà existant pour les dates suivantes : " +
                         ", ".join([dt.strftime("%d/%m/%Y") for dt in doublons]))

    db.session.commit()
    print("✅ Commit terminé")



LOG_EXTRACTION_PATH = "static/pdf_temp/log_extraction_paye.txt"
os.makedirs(os.path.dirname(LOG_EXTRACTION_PATH), exist_ok=True)

def extraire_infos_depuis_pdf(file_path):
    print("[DEBUG] Entrée dans extraire_infos_depuis_pdf")
    print("[DEBUG] Fichier à analyser :", file_path)
    try:
        text = ""
        print("[DEBUG] Tentative ouverture du PDF avec fitz.open...")
        with fitz.open(file_path) as doc:
            print("[DEBUG] PDF ouvert. Nombre de pages :", len(doc))
            for page_num, page in enumerate(doc):
                page_text = page.get_text()
                print(f"[DEBUG] Texte extrait de la page {page_num+1} (longueur : {len(page_text)})")
                text += page_text

        print("[DEBUG] Texte global extrait (premiers 500 caractères) :", repr(text[:500]))

        # Date de règlement
        print("[DEBUG] Recherche de la date de règlement...")
        date_match = re.search(r"R[ée]glement le\s*:\s*(\d{2}/\d{2}/\d{4})", text)
        date_str = ""
        if date_match:
            try:
                date_obj = datetime.strptime(date_match.group(1), "%d/%m/%Y")
                date_str = date_obj.strftime("%Y-%m-%d")
                print("[DEBUG] Date trouvée :", date_str)
            except ValueError:
                print("[DEBUG] Erreur de parsing date")
        else:
            print("[DEBUG] Aucune date de règlement trouvée")

        # Montant versé
        print("[DEBUG] Recherche du montant versé...")
        montant_match = re.search(r"Total\s+vers[éè]\s+par\s+l['’]employeur.*?(\d[\d\s ]*,\d{2})", text, re.DOTALL)
        montant_str = (
            montant_match.group(1).replace(" ", "").replace(" ", "").replace(",", ".")
            if montant_match else ""
        )
        print("[DEBUG] Montant trouvé :", montant_str)

        # Salaire brut
        print("[DEBUG] Recherche du salaire brut...")
        brut_match = re.search(r"SALAIRE BRUT\s+(\d[\d\s ]*,\d{2})", text)
        brut_str = (
            brut_match.group(1).replace(" ", "").replace(" ", "").replace(",", ".")
            if brut_match else ""
        )
        print("[DEBUG] Salaire brut trouvé :", brut_str)

        # Mois + année depuis "Périodes : du"
        print("[DEBUG] Recherche de la période...")
        periode_match = re.search(r"P[ée]riodes\s*:\s*du\s*(\d{2}/\d{2}/\d{4})", text)
        mois_annee = ""
        if periode_match:
            date_obj = datetime.strptime(periode_match.group(1), "%d/%m/%Y")
            mois_fr = {
                1: "Janvier", 2: "Février", 3: "Mars", 4: "Avril",
                5: "Mai", 6: "Juin", 7: "Juillet", 8: "Août",
                9: "Septembre", 10: "Octobre", 11: "Novembre", 12: "Décembre"
            }
            mois_annee = f"{mois_fr[date_obj.month]} {date_obj.year}"
            print("[DEBUG] Mois/année trouvé :", mois_annee)
        else:
            print("[DEBUG] Aucune période trouvée")

        # Log
        print("[DEBUG] Ouverture du log pour écrire le résultat d'extraction.")
        with open(LOG_EXTRACTION_PATH, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat()} - {os.path.basename(file_path)} - Date: {date_str} - Montant: {montant_str} - Brut: {brut_str} - Période: {mois_annee}\n")

        print("[DEBUG] Fin d'extraction - retour des données.")
        return {
            "date": date_str,
            "montant": montant_str,
            "brut": brut_str,
            "preciser": mois_annee
        }

    except Exception as e:
        print("[DEBUG][ERREUR]", str(e))
        raise RuntimeError(f"Erreur lors de l'analyse du PDF : {e}")





def get_cachets_par_mois(mois, annee):
    return (
        db.session.query(Cachet)
        .join(Musicien)
        .filter(
            extract('month', Cachet.date) == mois,
            extract('year', Cachet.date) == annee
        )
        .all()
    )



def log_mail_envoye(sujet, contenu):
    log_dir = Path("logs_mails")
    log_dir.mkdir(exist_ok=True)
    now = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    with open(log_dir / f"mail_{now}.txt", "w", encoding="utf-8") as f:
        f.write(f"Objet : {sujet}\n\n{contenu}")



def valider_concert_par_operation(concert_id, montant):
    concert = Concert.query.filter_by(id=concert_id).first()
    if concert:
        try:
            concert.recette = float(str(montant).replace(',', '.'))
        except Exception:
            concert.recette = montant
        concert.recette_attendue = None  # 🔄 on efface la prévision une fois le montant réel reçu
        concert.paye = True
        db.session.commit()


def get_ordered_comptes_bis(tableau_comptes):
    special_order = ["ASSO7", "CB ASSO7", "CAISSE ASSO7", "TRESO ASSO7"]
    comptes_dict = {c["nom"]: c for c in tableau_comptes}
    # Liste des musiciens normaux (pas spéciaux)
    musiciens = [c for c in tableau_comptes if c["nom"] not in special_order]
    # Liste des comptes spéciaux (toujours présents, même à zéro)
    comptes_speciaux = []
    for name in special_order:
        c = comptes_dict.get(name)
        if not c:
            c = {
                "nom": name,
                "credit_actuel": 0,
                "gains_a_venir": 0,
                "credit_potentiel": 0
            }
        comptes_speciaux.append(c)
    return musiciens + comptes_speciaux


def mois_fr(dt):
    mois_fr_map = {
        1: 'janvier', 2: 'février', 3: 'mars', 4: 'avril', 5: 'mai', 6: 'juin',
        7: 'juillet', 8: 'août', 9: 'septembre', 10: 'octobre', 11: 'novembre', 12: 'décembre'
    }
    return f"{mois_fr_map[dt.month]} {dt.year}"


from collections import defaultdict
from datetime import date

MOIS_FR = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre"
]

COULEURS_MOIS = {
    'septembre': '#FFE0E0',
    'octobre': '#FFF0C1',
    'novembre': '#F9F5D7',
    'décembre': '#D6F0FF',
    'janvier': '#DCE2FF',
    'février': '#F5DFFF',
    'mars': '#D8FFD8',
    'avril': '#E0FFE6',
    'mai': '#FFF5CC',
    'juin': '#FFEEDB',
    'juillet': '#FFDADA',
    'août': '#FFEFC1',
}

def regrouper_cachets_par_mois(cachets):
    """Retourne une liste triée : [(mois_fr, [(musicien, [cachets]), ...]), ...]"""
    data = defaultdict(lambda: defaultdict(list))
    for c in cachets:
        mois_str = MOIS_FR[c.date.month - 1]
        data[mois_str][c.musicien].append(c)

    mois_ordre = [
        'septembre', 'octobre', 'novembre', 'décembre',
        'janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet', 'août'
    ]
    cachets_par_mois = []
    for mois in mois_ordre:
        if mois in data:
            musiciens = sorted(
                data[mois].items(),
                key=lambda x: (x[0].nom.lower(), x[0].prenom.lower())
            )
            cachets_par_mois.append((mois.capitalize(), musiciens))
    return cachets_par_mois



