# === NOTE: mois FR centralisés ===
# Ce fichier a été harmonisé pour utiliser une UNIQUE source MONTHS_FR
# et les helpers mois_nom_fr/mois_annee_fr/grouper_par_mois.
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
from sqlalchemy import and_, extract, func, or_

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


# ─────────────────────────────────────────────
# 🗓️ Mois FR — Source unique + helpers
# ─────────────────────────────────────────────
from collections import OrderedDict, defaultdict
from datetime import date, datetime

MONTHS_FR = {
    1: "janvier", 2: "février", 3: "mars", 4: "avril",
    5: "mai", 6: "juin", 7: "juillet", 8: "août",
    9: "septembre", 10: "octobre", 11: "novembre", 12: "décembre",
}
# Ordre scolaire/septembre→août (utile pour archives cachets)
MONTH_ORDER_SEP2AUG = [9,10,11,12,1,2,3,4,5,6,7,8]

def _to_date(d):
    """Accepte date/datetime/ISO 'YYYY-MM-DD' ou 'DD/MM/YYYY' → date | None"""
    if d is None:
        return None
    if isinstance(d, date) and not isinstance(d, datetime):
        return d
    if isinstance(d, datetime):
        return d.date()
    s = str(d).strip()
    try:
        if "-" in s:   # 'YYYY-MM-DD' (ou datetime ISO)
            return datetime.fromisoformat(s[:10]).date()
        if "/" in s:   # 'DD/MM/YYYY'
            j, m, a = s.split("/")
            return date(int(a), int(m), int(j))
    except Exception:
        pass
    return None

def mois_nom_fr(mois: int, *, capitalize: bool = False) -> str:
    """1..12 -> 'janvier' (ou 'Janvier' si capitalize=True)"""
    nom = MONTHS_FR.get(int(mois), "")
    return nom.capitalize() if (capitalize and nom) else nom

def mois_annee_fr(dt: date | datetime | str, *, capitalize: bool = True) -> str:
    """Date -> 'Septembre 2025' (ou 'septembre 2025' si capitalize=False)"""
    d = _to_date(dt)
    if not d:
        return "—"
    nom = MONTHS_FR.get(d.month, "")
    nom = nom.capitalize() if capitalize else nom
    return f"{nom} {d.year}"

def grouper_par_mois(items, date_attr: str, *, descending: bool = True):
    """
    Regroupe une liste d'objets/dicts par mois (clé 'YYYY-MM').
    Retourne OrderedDict trié (desc par défaut):
      { 'YYYY-MM': { 'label': 'Septembre 2025', 'items': [...] }, ... }
    """
    buckets = defaultdict(list)
    for it in items:
        raw = getattr(it, date_attr, None) if hasattr(it, date_attr) else (it.get(date_attr) if isinstance(it, dict) else None)
        d = _to_date(raw)
        if not d:
            continue
        key = f"{d.year:04d}-{d.month:02d}"
        buckets[key].append(it)

    keys = sorted(buckets.keys(), reverse=descending)
    out = OrderedDict()
    for k in keys:
        y, m = k.split("-")
        d = date(int(y), int(m), 1)
        out[k] = {"label": mois_annee_fr(d), "items": buckets[k]}
    return out



def formater_cachets_html(cachets):
    """Formate une liste de cachets en HTML groupé par musicien, trié par nom puis date."""
    musiciens = {}
    for c in sorted(cachets, key=lambda x: (x.musicien.nom, x.date)):
        nom_complet = f"{c.musicien.prenom} {c.musicien.nom}"
        musiciens.setdefault(nom_complet, []).append(
            f"{c.date.strftime('%d/%m/%Y')} – {c.montant:.2f} €"
        )
    blocs = []
    for nom, lignes in musiciens.items():
        bloc = f"<p style='margin-left: 20px;'><strong>{nom}</strong><br>" + "<br>".join(lignes) + "</p>"
        blocs.append(bloc)
    return "\n".join(blocs)


def regrouper_cachets_par_mois(cachets, *, ordre_scolaire: bool = True):
    """
    Retourne une liste : [
        ( 'Septembre', [(musicien_obj, [Cachet,...]), ...] ),
        ( 'Octobre',   [(musicien_obj, [Cachet,...]), ...] ),
        ...
    ]
    ⚠️ Format 100% compatible avec ton template actuel.
    """

    # 1) Bucket par mois (nom FR) puis par musicien -> liste de cachets
    data = defaultdict(lambda: defaultdict(list))
    for c in cachets:
        m = getattr(c, "date", None).month if getattr(c, "date", None) else None
        if not m:
            continue
        mois_str = MONTHS_FR.get(m, "")
        if not mois_str:
            continue
        data[mois_str][c.musicien].append(c)

    if not data:
        return []

    # 2) Trie des mois
    def mois_index(mois_nom: str) -> int:
        # mappage "septembre" -> 0, ..., "août" -> 11
        try:
            num = next(k for k, v in MONTHS_FR.items() if v == mois_nom)
        except StopIteration:
            return 0
        return MONTH_ORDER_SEP2AUG.index(num) if num in MONTH_ORDER_SEP2AUG else 0

    mois_liste = list(data.keys())
    if ordre_scolaire:
        mois_liste.sort(key=mois_index)
    else:
        # Tri chronologique classique janvier→décembre
        mois_liste.sort(key=lambda mn: next((k for k, v in MONTHS_FR.items() if v == mn), 0))

    # 3) Formattage final pour le template
    out = []
    for mois_nom in mois_liste:
        # Trie des musiciens par NOM, puis PRÉNOM
        musiciens_tries = sorted(
            data[mois_nom].items(),
            key=lambda x: ((x[0].nom or "").lower(), (x[0].prenom or "").lower())
        )
        out.append((mois_nom.capitalize(), musiciens_tries))

    return out


def mois_annee_label_fr(d: date) -> str:
    """Renvoie 'Septembre 2025' à partir d'une date"""
    if not d:
        return "—"
    mois = MONTHS_FR.get(d.month, "")
    return f"{mois.capitalize()} {d.year}"


# ─────────────────────────────────────────────
# 3. 🧾 UTILITAIRES MUSICIENS
# ─────────────────────────────────────────────

from datetime import date
from sqlalchemy import func, or_
from models import Musicien, Operation, Participation, Concert, Report, db


def get_etat_comptes():
    """Construit le tableau pour /comptes (musiciens + structures)."""
    aujourd_hui = date.today()
    tableau = []

    concerts = Concert.query.all()

    def _sum_ops(musicien_id: int, *, passees: bool) -> float:
        """
        Somme (credit - debit) des opérations.
        - passées  := date <= aujourd_hui ET (previsionnel is False/None)
        - à venir := (date > aujourd_hui) OU (previsionnel is True)
        """
        q = Operation.query.filter(Operation.musicien_id == musicien_id)
        if passees:
            q = (q.filter(Operation.date <= aujourd_hui)
                   .filter(or_(Operation.previsionnel.is_(False),
                               Operation.previsionnel.is_(None))))
        else:
            q = q.filter(or_(Operation.date > aujourd_hui,
                             Operation.previsionnel.is_(True)))

        total = 0.0
        for op in q.all():
            typ = (op.type or "").lower().replace("é", "e")
            if typ == "credit":
                total += (op.montant or 0.0)
            elif typ == "debit":
                total -= (op.montant or 0.0)
        return total

    # ---------- MUSICIENS (tout ce qui n'est PAS 'structure') ----------
    musiciens = (
        Musicien.query
        .filter(Musicien.actif.is_(True), Musicien.type != 'structure')
        .order_by(Musicien.nom, Musicien.prenom)
        .all()
    )

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

        # Gains à venir = participations potentielles + opérations à venir (inclut prévisionnels)
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
        credit = calculer_credit_actuel(s, concerts)

        report_s = (db.session.query(func.sum(Report.montant))
                    .filter_by(musicien_id=s.id)
                    .scalar() or 0.0)
        credit += report_s

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
        # ➕ inclure aussi les opérations à venir (dont prévisionnels)
        ops_avenir_cb = _sum_ops(cb_asso7.id, passees=False)

        gains_cb = (recettes_a_venir_cb or 0.0) + ops_avenir_cb

        tableau.append({
            "nom": "CB ASSO7",
            "credit": credit_cb,
            "gains_a_venir": gains_cb,
            "credit_potentiel": credit_cb + gains_cb,
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
        # ➕ inclure aussi les opérations à venir (dont prévisionnels)
        ops_avenir_caisse = _sum_ops(caisse_asso7.id, passees=False)

        gains_caisse = (recettes_a_venir_caisse or 0.0) + ops_avenir_caisse

        tableau.append({
            "nom": "CAISSE ASSO7",
            "credit": credit_caisse,
            "gains_a_venir": gains_caisse,
            "credit_potentiel": credit_caisse + gains_caisse,
            "structure": True
        })

    # --- TRESO ASSO7 = CB + CAISSE ---
    if cb_asso7 or caisse_asso7:
        cb_row = next((r for r in tableau if r.get("nom") == "CB ASSO7"), None)
        caisse_row = next((r for r in tableau if r.get("nom") == "CAISSE ASSO7"), None)

        treso_credit = (cb_row["credit"] if cb_row else 0.0) + (caisse_row["credit"] if caisse_row else 0.0)
        treso_gains  = (cb_row["gains_a_venir"] if cb_row else 0.0) + (caisse_row["gains_a_venir"] if caisse_row else 0.0)

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

# ... (imports OK : Participation est déjà importé en haut du fichier)

# --- à mettre dans mes_utils.py (remplace la fonction existante) ---
from sqlalchemy import func, or_

def calculer_credit_actuel(musicien, concerts):
    """
    Crédit ACTUEL = (participations réelles déjà écrites en DB) + (opérations passées).
    - Pour ASSO7 (et autres structures "non spéciales") : on LIT Participation.credit_calcule (montants FIXÉS).
    - Pour CB/CAISSE/TRESO : pas de participations → on ne prend que les opérations passées.
    """
    if musicien is None:
        return 0.0

    aujourd_hui = date.today()
    nom = (musicien.nom or "").strip().upper()

    # Helper: somme des opérations passées (non prévisionnelles)
    def _sum_ops_passees(mid: int) -> float:
        q = (
            Operation.query
            .filter(Operation.musicien_id == mid)
            .filter(Operation.date <= aujourd_hui)
            .filter(or_(Operation.previsionnel.is_(False),
                        Operation.previsionnel.is_(None)))
        )
        total = 0.0
        for op in q.all():
            typ = (op.type or "").lower().replace("é", "e")
            if typ == "credit":
                total += (op.montant or 0.0)
            elif typ == "debit":
                total -= (op.montant or 0.0)
        return total

    # Structures "spéciales" : uniquement les opérations passées
    if nom in ["CB ASSO7", "CAISSE ASSO7", "TRESO ASSO7"]:
        return _sum_ops_passees(musicien.id)

    # Structures "classiques" (dont ASSO7) et musiciens normaux :
    # on lit ce qui a été ÉCRIT lors du paiement : Participation.credit_calcule (réel),
    # puis on ajoute leurs opérations passées.
    parts_reelles = (
        db.session.query(func.sum(Participation.credit_calcule))
        .filter(Participation.musicien_id == musicien.id)
        .scalar() or 0.0
    )
    return float(parts_reelles) + _sum_ops_passees(musicien.id)




def calculer_gains_a_venir(musicien, concerts):
    aujourd_hui = date.today()
    credit = 0.0
    nom = (musicien.nom or "").strip().upper()

    # Pour les concerts non payés, on lit Participation.credit_calcule_potentiel
    for concert in concerts:
        if not concert.paye:
            part = next((p for p in concert.participations if p.musicien_id == musicien.id), None)
            if part is not None:
                credit += float(part.credit_calcule_potentiel or 0.0)

    # Opérations futures
    operations = Operation.query.filter_by(musicien_id=musicien.id).all()
    for op in operations:
        if op.date > aujourd_hui:
            typ = (op.type or "").lower()
            if typ == "debit":
                credit -= op.montant or 0
            elif typ == "credit":
                credit += op.montant or 0

    # Recette attendue pour CB ASSO7 / CAISSE ASSO7
    if nom in ["CB ASSO7", "CAISSE ASSO7"]:
        for concert in concerts:
            if not concert.paye and concert.mode_paiement_prevu and nom in concert.mode_paiement_prevu.upper():
                credit += concert.recette_attendue or 0

    return credit


# --- imports nécessaires (ajoute-les s'ils ne sont pas déjà présents) ---
from collections import defaultdict
from typing import Dict
from sqlalchemy import func, or_, case
from models import db, Operation  # Concert pas nécessaire ici

def collecter_frais_par_musicien(concerts):
    """
    Renvoie un dict { concert_id: { musicien_id: total_frais } }.
    On additionne:
      - DEBIT  -> +montant
      - CREDIT -> -montant   (ex: remboursement)
    On ignore les opérations prévisionnelles.
    """
    concert_ids = [c.id for c in concerts] or [-1]

    signed_sum = func.sum(
        case(
            (func.lower(Operation.type) == "debit",  Operation.montant),
            (func.lower(Operation.type) == "credit", -Operation.montant),
            else_=0.0,
        )
    )

    rows = (
        Operation.query
        .with_entities(Operation.concert_id, Operation.musicien_id, signed_sum.label("total"))
        .filter(
            Operation.concert_id.in_(concert_ids),
            db.func.lower(db.func.coalesce(Operation.motif, "" )).in_(["frais", "frais de concerts"]),
            Operation.previsionnel.is_(False)
        )
        .group_by(Operation.concert_id, Operation.musicien_id)
        .all()
    )

    out = {}
    for cid, mid, total in rows:
        if total is None:
            continue
        out.setdefault(cid, {})[mid] = float(total)
    return out



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

# en haut si pas déjà importés
from sqlalchemy import func, or_

ALLOWED_TYPES = {"musicien", "structure"}

def _normalize_type(raw: str | None) -> str | None:
    s = (raw or "").strip().lower()
    # synonymes acceptés
    mapping = {
        "musicien": "musicien",
        "musiciens": "musicien",
        "pers": "musicien",
        "personne": "musicien",  # legacy mappé vers "musicien"
        "structure": "structure",
        "structures": "structure",
        "asso": "structure",
        "association": "structure",
    }
    t = mapping.get(s, s)
    return t if t in ALLOWED_TYPES else None

def _clean(s: str | None) -> str:
    return " ".join((s or "").replace("\xa0", " ").split())

def _display_case_nom(nom: str) -> str:
    # conserve majuscules des sigles (ASSO7, CB ASSO7) si tout en majuscules
    if nom.isupper():
        return nom
    return nom.upper()  # pour les NOMs des personnes on garde majuscules

def _display_case_prenom(p: str) -> str:
    # Jérôme, Nathalie, etc. (simple title-case)
    return p.capitalize() if p else ""

def sanitize_musicien_payload(payload: dict) -> dict:
    """
    Valide et normalise les champs pour créer un musicien OU une structure.
    - type ∈ {'musicien', 'structure'} sinon ValueError
    - musiciens: prénom & nom obligatoires
    - structures: nom obligatoire, prénom forcé vide
    - normalise et empêche les doublons évidents
    """
    t = _normalize_type(payload.get("type"))
    if not t:
        raise ValueError("Type invalide. Valeurs autorisées : 'musicien' ou 'structure'.")

    nom = _clean(payload.get("nom"))
    prenom = _clean(payload.get("prenom"))

    if t == "musicien":
        if not nom or not prenom:
            raise ValueError("Pour un musicien, 'prenom' et 'nom' sont obligatoires.")
        nom_aff = _display_case_nom(nom)
        prenom_aff = _display_case_prenom(prenom)
        # doublon: même prenom+nom (insensible casse/espaces)
        exists = Musicien.query.filter(
            func.lower(func.trim(Musicien.nom)) == nom.lower(),
            func.lower(func.trim(Musicien.prenom)) == prenom.lower()
        ).first()
        if exists:
            raise ValueError("Ce musicien existe déjà.")
        return {"type": "musicien", "nom": nom_aff, "prenom": prenom_aff, "actif": True}

    else:  # structure
        if not nom:
            raise ValueError("Pour une structure, 'nom' est obligatoire.")
        prenom_aff = ""  # pas de prénom pour une structure
        nom_aff = nom.upper()  # les structures en MAJ (ASSO7, CB ASSO7…)
        # doublon: même nom (insensible casse/espaces) et pas de prénom
        exists = Musicien.query.filter(
            func.lower(func.trim(Musicien.nom)) == nom.lower(),
            or_(Musicien.prenom.is_(None), func.trim(Musicien.prenom) == "")
        ).first()
        if exists:
            raise ValueError("Cette structure existe déjà.")
        return {"type": "structure", "nom": nom_aff, "prenom": prenom_aff, "actif": True}



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
        mois_label = f"{MONTHS_FR[concert.date.month].capitalize()} {concert.date.year}"
        if mois_label not in groupes:
            groupes[mois_label] = []
        groupes[mois_label].append(concert)

    # Trie par année, puis par mois
    def mois_key(label):
        nom_mois, annee = label.split()
        mois_num = list(MONTHS_FR.values()).index(nom_mois.lower())+1
        return (int(annee), mois_num)
    groupes_tries = OrderedDict(
        sorted(groupes.items(), key=lambda x: mois_key(x[0]))
    )
    return groupes_tries

def recalculer_frais_concert(concert_id: int, op_to_remove_id: int | None = None):
    """
    Recalcule la somme des opérations 'Frais' rattachées au concert,
    en EXCLUANT:
      - les opérations prévisionnelles (previsionnel = TRUE),
      - éventuellement une opération donnée (op_to_remove_id) si on l'appelle AVANT sa suppression.
    Met à jour concert.frais et retourne le total calculé.
    """
    # 1) Récupération du concert
    concert = Concert.query.get(concert_id)
    if concert is None:
        print(f"❌ Le concert {concert_id} n'existe pas")
        return 0.0

    # 2) Construction de la requête: Frais réels uniquement (prévisionnels exclus)
    q = db.session.query(db.func.coalesce(db.func.sum(Operation.montant), 0.0)).filter(
        Operation.concert_id == concert_id,
        db.func.lower(db.func.coalesce(Operation.motif, "" )).in_(["frais", "frais de concerts"]),
        db.or_(Operation.previsionnel.is_(False), Operation.previsionnel.is_(None))
    )


    # 3) Si on connaît l'ID d'une op à retirer (appel avant suppression), on l'exclut de la somme
    if op_to_remove_id:
        q = q.filter(Operation.id != op_to_remove_id)

    frais_total = float(q.scalar() or 0.0)
    print(f"✅ Total des frais (hors prévisionnels){' et hors op '+str(op_to_remove_id) if op_to_remove_id else ''} : {frais_total:.2f} €")

    # 4) Écriture en base
    try:
        concert.frais = frais_total
        db.session.add(concert)
        db.session.commit()
        print(f"✅ Frais mis à jour pour le concert {concert_id} : {frais_total:.2f} €")
    except Exception as e:
        db.session.rollback()
        print(f"❌ Erreur lors de la mise à jour des frais pour le concert {concert_id} :", e)

    return frais_total


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


def creer_recette_concert_si_absente(concert_id, montant=None, date_op=None, mode=None):
    """
    Crée (si absente) l'opération de crédit 'Recette concert' au profit de CB ASSO7 ou CAISSE ASSO7,
    déterminés à partir du 'mode' effectif : accepte 'Compte' / 'Espèces' ET 'CB_ASSO7' / 'CAISSE_ASSO7'
    (ainsi que variantes 'cb asso7', 'caisse asso7', etc.).
    AUCUN fallback vers 'ASSO7' : si on ne trouve pas le bénéficiaire, on lève une erreur.
    Idempotent sur (motif='Recette concert', concert_id=...).
    """
    concert = Concert.query.get(concert_id)
    if not concert:
        raise ValueError(f"Concert introuvable id={concert_id}")

    # -- Montant --
    montant_final = (
        float(montant) if montant is not None
        else float(concert.recette if concert.recette is not None
                   else (concert.recette_attendue or 0.0))
    )
    if montant_final <= 0:
        print(f"[WARN] Recette concert id={concert_id} avec montant <= 0 : rien créé.")
        return None

    # -- Date --
    from datetime import date as _date
    date_finale = date_op or getattr(concert, "date", None) or _date.today()

    # -- Résolution du bénéficiaire à partir du 'mode' effectif --
    #    On accepte : "Compte", "CB_ASSO7", "cb asso7", "Espèces", "CAISSE_ASSO7", "caisse asso7", etc.
    def _norm(s: str) -> str:
        s = (s or "").strip().lower()
        # simpliste mais efficace (évite d'ajouter une dépendance unidecode)
        remap = str.maketrans({"é": "e", "è": "e", "ê": "e", "à": "a", "ù": "u", "ï": "i", "î": "i", "ô": "o", "ç": "c"})
        s = s.translate(remap)
        for ch in ("_", "-", ".", "/"):
            s = s.replace(ch, " ")
        s = " ".join(s.split())
        return s

    mode_eff = _norm(mode or getattr(concert, "mode_paiement_prevu", "") or "compte")

    # Dictionnaire des intentions → cible
    # tout ce qui ressemble à "compte" ou "cb..." => CB ASSO7
    # tout ce qui ressemble à "especes" ou "caisse..." => CAISSE ASSO7
    def _is_cb(key: str) -> bool:
        return any(tok in key for tok in [
            "compte", "cb asso7", "cbasso7", "cb", "cb asso", "cb_asso7"
        ])

    def _is_caisse(key: str) -> bool:
        return any(tok in key for tok in [
            "especes", "espece", "caisse asso7", "caisseasso7", "caisse", "caisse_asso7"
        ])

    musiciens = Musicien.query.all()

    def _find_by_nom(targets):
        return next(
            (m for m in musiciens if (m.nom or "").strip().lower() in targets),
            None
        )

    cible_benef = None
    if _is_cb(mode_eff):
        cible_benef = _find_by_nom({"cb asso7"})
    elif _is_caisse(mode_eff):
        cible_benef = _find_by_nom({"caisse asso7"})

    if not cible_benef:
        raise ValueError(
            f"Impossible de déterminer le bénéficiaire de la recette pour mode='{mode}'. "
            f"Attendu: CB ASSO7 ou CAISSE ASSO7."
        )

    # -- Idempotence : existe déjà ? --
    op_existante = Operation.query.filter_by(
        motif="Recette concert",
        concert_id=concert.id
    ).first()

    if op_existante:
        maj = False
        if float(op_existante.montant or 0) != float(montant_final):
            op_existante.montant = float(montant_final); maj = True
        if getattr(op_existante, "date", None) != date_finale:
            op_existante.date = date_finale; maj = True
        if getattr(op_existante, "musicien_id", None) != cible_benef.id:
            op_existante.musicien_id = cible_benef.id; maj = True
        if maj:
            db.session.add(op_existante)
    else:
        # -- Création --
        op = Operation(
            musicien_id=cible_benef.id,
            type="credit",
            motif="Recette concert",
            precision=(f"Recette concert {getattr(concert, 'titre', '') or ''}").strip() or None,
            montant=float(montant_final),
            date=date_finale,
            concert_id=concert.id,
            # Surtout PAS auto_cb_asso7=True : on veut que ça apparaisse dans les archives.
        )
        db.session.add(op)

    # Marquer payé si besoin (normalement déjà géré par l'appelant, mais idempotent)
    if not concert.paye:
        concert.paye = True
        db.session.add(concert)

    db.session.flush()  # s'assure des IDs
    # pas de commit ici : on laisse la route appeler commit, puis recalculer
    return True

def supprimer_recette_concert_pour_concert(concert_id: int) -> int:
    """
    Supprime TOUTE opération 'Recette concert' liée à un concert (idempotent).
    On identifie en priorité par motif/precision normalisés côté Python, mais on
    récupère toutes les opérations par concert_id pour éviter les ratés SQL.
    Retourne le nombre d'opérations supprimées.
    """
    def _norm(s: str) -> str:
        s = (s or "").replace("\xa0", " ").strip().lower()
        # remplace accents usuels sans dépendance externe
        table = str.maketrans({
            "é": "e", "è": "e", "ê": "e", "ë": "e",
            "à": "a", "â": "a",
            "î": "i", "ï": "i",
            "ô": "o",
            "ù": "u", "û": "u",
            "ç": "c",
        })
        s = s.translate(table)
        # condense espaces multiples
        s = " ".join(s.split())
        return s

    ops = Operation.query.filter_by(concert_id=concert_id).all()
    if not ops:
        return 0

    # 1) Cible stricte : motif == "recette concert" (normalisé) OU precision contient "recette concert"
    candidats = []
    for o in ops:
        motif_n = _norm(o.motif)
        prec_n = _norm(getattr(o, "precision", None))
        if motif_n == "recette concert" or "recette concert" in prec_n:
            candidats.append(o)

    # 2) Fallback prudent : type=credit et (motif contient 'recette' ET 'concert')
    if not candidats:
        for o in ops:
            motif_n = _norm(o.motif)
            if (o.type or "").strip().lower() == "credit" and ("recette" in motif_n and "concert" in motif_n):
                candidats.append(o)

    if not candidats:
        print(f"[INFO] Aucune 'Recette concert' détectée pour concert_id={concert_id}")
        return 0

    # Supprime via le helper cascade qui gère les FKs auto-référentes
    suppr_count = 0
    for o in candidats:
        try:
            supprimer_operation_en_db(o.id)  # déjà transaction-safe
            suppr_count += 1
        except Exception as e:
            print(f"[WARN] Suppression op 'Recette concert' id={o.id} échouée: {e}")

    print(f"[OK] {suppr_count} opération(s) 'Recette concert' supprimée(s) pour concert_id={concert_id}")
    return suppr_count
    
def basculer_statut_paiement_concert(concert_id: int, paye: bool, montant: float | None = None, mode: str | None = None):
    from calcul_participations import (
        mettre_a_jour_credit_calcule_reel_pour_concert,
        mettre_a_jour_credit_calcule_potentiel_pour_concert,
    )
    from mes_utils import creer_recette_concert_si_absente, supprimer_recette_concert_pour_concert
    
    concert = Concert.query.get(concert_id)
    if not concert:
        raise ValueError(f"Concert introuvable id={concert_id}")

    # utilitaires locaux
    def _to_float(x):
        if x is None:
            return None
        s = str(x).strip().replace(",", ".")
        return float(s) if s else None

    if paye:
        # ===== NON PAYÉ -> PAYÉ =====
        # 1) Déterminer recette finale
        montant_val = _to_float(montant)
        if montant_val is not None:
            concert.recette = montant_val
        elif concert.recette_attendue is not None:
            concert.recette = float(concert.recette_attendue)
        else:
            concert.recette = float(concert.recette or 0.0)

        # 2) Etat payé + nettoyer la prévision
        concert.paye = True
        concert.recette_attendue = None
        db.session.add(concert)

        # 3) Créer (si absente) l'opération 'Recette concert' vers le bon compte
        mode_final = (mode or getattr(concert, "mode_paiement_prevu", "") or "Compte").strip()
        creer_recette_concert_si_absente(
            concert_id=concert.id,
            montant=concert.recette,
            date_op=None,
            mode=mode_final
        )

        # 4) Commit + recalcul réel
        db.session.commit()
        try:
            db.session.expire_all()
            mettre_a_jour_credit_calcule_reel_pour_concert(concert.id)
            db.session.commit()
        except Exception as e:
            print(f"[WARN] recalcul réel échoué pour concert {concert.id}: {e}")

        return {
            "concert_id": concert.id,
            "paye": True,
            "recette": concert.recette,
            "mode": mode_final,
        }

    else:
        # ===== PAYÉ -> NON PAYÉ =====
        try:
            # 1) Restaurer recette_attendue si absente
            if (concert.recette_attendue is None) and (concert.recette is not None):
                try:
                    concert.recette_attendue = float(concert.recette) or 0.0
                except Exception:
                    concert.recette_attendue = 0.0

            # 2) Supprimer opérations 'Recette concert'
            nb_suppr = supprimer_recette_concert_pour_concert(concert.id)
            print(f"[INFO] {nb_suppr} op(s) 'Recette concert' supprimée(s) pour concert_id={concert.id}")

            # 3) Etat non payé + nettoyer recette
            concert.recette = None
            concert.paye = False
            db.session.add(concert)

            # 4) Commit + recalcul potentiel
            db.session.commit()
            try:
                db.session.expire_all()
                mettre_a_jour_credit_calcule_potentiel_pour_concert(concert.id)
                db.session.commit()
            except Exception as e:
                print(f"[WARN] recalcul potentiel échoué pour concert {concert.id}: {e}")

            return {
                "concert_id": concert.id,
                "paye": False,
                "recette_attendue": float(concert.recette_attendue or 0.0),
                "recettes_supprimees": nb_suppr,
            }

        except Exception as e:
            db.session.rollback()
            raise


from datetime import date
from models import db, Operation, Concert, Musicien

def _get_compte_cbaso7():
    # Adapte si tu as une façon “officielle” d’identifier CB ASSO7
    return Musicien.query.filter(
        (Musicien.nom.ilike('%ASSO7%')) | (Musicien.prenom.ilike('%ASSO7%'))
    ).first()

def _parse_montant(txt: str | None) -> float | None:
    if not txt:
        return None
    s = str(txt).strip().replace(" ", "").replace("\xa0", "").replace(",", ".")
    if not s:
        return None
    try:
        v = round(float(s), 2)
        return v if v > 0 else None
    except Exception:
        return None

def recompute_frais_previsionnels(concert_id: int) -> float:
    """Recalcule concerts.frais_previsionnels en sommant les opérations
    prévisionnelles 'Frais' (débit) imputées à CB ASSO7 pour ce concert."""
    from models import db, Operation, Musicien, Concert

    cb_id = (
        Musicien.query
        .filter(db.func.lower(db.func.trim(Musicien.nom)) == 'cb asso7')
        .with_entities(Musicien.id)
        .scalar()
    )
    if not cb_id:
        # Pas de CB ASSO7 => par prudence, 0 ET on met le champ à None
        c = Concert.query.get(concert_id)
        if c:
            c.frais_previsionnels = None
            db.session.add(c)
            db.session.commit()
        return 0.0

    total = (
        db.session.query(db.func.coalesce(db.func.sum(Operation.montant), 0.0))
        .filter(
            Operation.concert_id == concert_id,
            Operation.previsionnel.is_(True),
            db.func.lower(db.func.coalesce(Operation.motif, '')) == 'frais',
            db.func.lower(db.func.coalesce(Operation.type,  '')) == 'debit',
            Operation.musicien_id == cb_id,
        )
        .scalar()
        or 0.0
    )

    c = Concert.query.get(concert_id)
    if c:
        c.frais_previsionnels = (None if float(total) == 0.0 else float(total))
        db.session.add(c)
        db.session.commit()
    return float(total)

def ensure_op_frais_previsionnels(concert_id: int, frais_txt: str | None) -> None:
    """
    Crée / met à jour / supprime l'opération prévisionnelle 'Frais' liée à un concert.
    ✅ Imputée par défaut à **CB ASSO7** (fallback 'ASSO7' si CB absent).
    """
    from models import db, Concert, Operation, Musicien

    concert = Concert.query.get(concert_id)
    if not concert:
        return

    montant = _parse_montant(frais_txt)

    # CB ASSO7 prioritaire
    cb = Musicien.query.filter(Musicien.nom == "CB ASSO7").first()
    if not cb:
        cb = Musicien.query.filter(Musicien.nom == "ASSO7").first()

    # — Cas SUPPRESSION : montant vide/0 → on purge TOUTES les prévisionnelles "Frais" de ce concert
    if not montant:
        ops_prev = Operation.query.filter_by(
            concert_id=concert.id,
            previsionnel=True,
            motif="Frais"
        ).all()
        for opx in ops_prev:
            db.session.delete(opx)

        concert.op_prevision_frais_id = None
        # On ne fixe pas directement frais_previsionnels : on laisse le recompute
        db.session.add(concert)
        db.session.commit()

        # recalcul agrégé (mettra None si total = 0)
        recompute_frais_previsionnels(concert.id)
        return

    # — Cas CREATION / MISE A JOUR
    op = None
    if concert.op_prevision_frais_id:
        op = Operation.query.get(concert.op_prevision_frais_id)
    if not op:
        op = Operation.query.filter_by(
            concert_id=concert.id,
            previsionnel=True,
            motif="Frais"
        ).first()

    if not op:
        op = Operation(
            musicien_id=(cb.id if cb else None),
            type="debit",
            motif="Frais",
            nature="frais",
            precision=f"Frais prévisionnels — Concert #{concert.id} {concert.lieu}",
            montant=montant,
            date=concert.date,
            concert_id=concert.id,
            previsionnel=True,
            auto_cb_asso7=False,  # visible dans « à venir »
        )
        db.session.add(op)
        db.session.flush()           # récupère op.id
        concert.op_prevision_frais_id = op.id
    else:
        op.musicien_id = (cb.id if cb else op.musicien_id)
        op.type = "debit"
        op.motif = "Frais"
        op.nature = "frais"
        op.montant = montant
        op.date = concert.date
        op.previsionnel = True
        op.auto_cb_asso7 = False
        db.session.add(op)

    db.session.add(concert)
    db.session.commit()

    # recalcul agrégé (et écrit le champ concert.frais_previsionnels)
    recompute_frais_previsionnels(concert.id)


def detach_prevision_if_needed(op: Operation):
    """À appeler avant de supprimer une op : nettoie le lien côté Concert si c'était une prévision et recalcule."""
    from models import db, Concert
    if op and op.previsionnel and op.concert_id:
        c = Concert.query.get(op.concert_id)
        if c and c.op_prevision_frais_id == op.id:
            c.op_prevision_frais_id = None
            db.session.add(c)
            db.session.commit()
            # recalcul (mettra None/0 si plus rien)
            recompute_frais_previsionnels(c.id)

# ─────────────────────────────────────────────
# 5. 💸 GESTION DES OPÉRATIONS
# ─────────────────────────────────────────────

from calcul_participations import mettre_a_jour_credit_calcule_potentiel_pour_concert

def enregistrer_operation_en_db(data):
    # --- Helpers locaux (évite toute dépendance externe) ---
    def _to_float(x):
        if x is None:
            return None
        s = str(x).strip().replace(",", ".")
        return float(s) if s else None

    def _to_int_or_none(x):
        if x is None:
            return None
        s = str(x).strip()
        return int(s) if s.isdigit() else None

    def _infer_type_from_motif_if_missing(type_val, motif_val):
        t = (type_val or "").strip().lower()
        if t:
            # normalisation simple
            return "credit" if t.startswith("cr") else "debit"
        m = (motif_val or "").strip().lower()
        if m == "salaire":
            return "debit"
        if m == "recette concert":
            return "credit"
        # Frais: par défaut, on laissera la logique plus bas (CB/CAISSE) décider,
        # mais s'il faut un fallback strict :
        return "debit"

    nom_saisi = (data.get("musicien") or "").strip().lower()
    musiciens = Musicien.query.all()

    cible = next(
        (m for m in musiciens if f"{(m.prenom or '').strip()} {(m.nom or '').strip()}".strip().lower() == nom_saisi),
        None
    )
    if not cible:
        raise ValueError(f"Musicien introuvable pour le nom : {data.get('musicien')}")

    # 📆 Conversion date : accepte 'jj/mm/aaaa' ou déjà 'aaaa-mm-jj'
    date_str = (data.get("date") or "").strip()
    if "/" in date_str:
        try:
            jour, mois, annee = date_str.split("/")
            date_str = f"{annee}-{mois.zfill(2)}-{jour.zfill(2)}"
        except Exception as e:
            print("Erreur de conversion date :", data.get("date"), e)
            raise
    try:
        date_op = datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception as e:
        print("Erreur de parsing date ISO :", date_str, e)
        raise

    # Champs normalisés
    motif = data.get("motif")
    type_op = _infer_type_from_motif_if_missing(data.get("type"), motif)
    precision = data.get("precision", "")

    # 🎯 Déduction automatique du type selon le motif (garde ta logique existante)
    cible_nom_normalise = (cible.nom or "").strip().lower()
    concert_id = _to_int_or_none(data.get("concert_id"))  # <- *** fix: '' devient None ***
    if motif == "Frais de concerts": 
        # même règle qu'avant : CB/CAISSE => débit, sinon crédit
        type_op = "debit" if cible_nom_normalise in ["cb asso7", "caisse asso7"] else "credit"
    elif motif == "Frais divers":
        # hors concert => toujours débit
        type_op = "debit"
    elif motif == "Recette concert":
        type_op = "credit"
    elif motif == "Salaire":
        type_op = "debit"
    elif motif == "Remboursement frais divers":
        type_op = "debit"

    # Montants sécurisés (gère virgules)
    montant = _to_float(data.get("montant"))
    if montant is None:
        raise ValueError("Montant manquant ou invalide")
    brut_val = _to_float(data.get("brut"))

    op = Operation(
        musicien_id=cible.id,
        type=type_op,
        motif=motif,
        precision=precision,
        montant=float(montant),
        date=date_op,
        brut=float(brut_val) if brut_val is not None else None,
        concert_id=concert_id  # <- None si vide, OK pour INTEGER NULL en DB
    )
    db.session.add(op)
    db.session.flush()

    # 💸 Commission Lionel sur salaire brut
    is_salaire = (motif == "Salaire")
    has_brut = (brut_val is not None and float(brut_val) > 0)
    if is_salaire and has_brut:
        commission = round(float(brut_val) * 0.03, 2)
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

    # --- LIEN AUTO POUR ASSO7 -> CB/CAISSE SELON LE MODE ---
    # Si on saisit une opération sur ASSO7, on crée une op miroir sur CB ASSO7 (mode Compte)
    # ou CAISSE ASSO7 (mode Espèces) pour impacter la trésorerie.
    # Cette op "auto_cb_asso7" est ignorée côté ASSO7 dans les totaux.
    if cible_nom_normalise == "asso7":
        mode_val = (data.get("mode") or "Compte").strip().lower()

        # cible trésorerie: CB pour "compte/cb/carte", CAISSE pour "espèces/caisse"
        cible_treso = None
        if mode_val in ("compte", "cb", "carte", "cb asso7"):
            cible_treso = next((m for m in musiciens if (m.nom or "").strip().lower() == "cb asso7"), None)
        elif mode_val in ("especes", "espèces", "caisse", "caisse asso7"):
            cible_treso = next((m for m in musiciens if (m.nom or "").strip().lower() == "caisse asso7"), None)

        if cible_treso:
            op_treso = Operation(
                musicien_id=cible_treso.id,
                type=type_op,                         # même type que l'op principale (debit/crédit)
                motif=(motif or ""),
                precision=(precision or f"Auto pour ASSO7 ({mode_val})"),
                montant=float(montant),
                date=date_op,
                concert_id=concert_id,
                auto_cb_asso7=True,                   # clé : comptera dans CB/CAISSE mais pas pour ASSO7
                operation_liee_id=op.id               # lien vers l'op principale
            )
            db.session.add(op_treso)


    # 🔄 Débit automatique sur CB ASSO7 / CAISSE ASSO7 pour Salaire / Remboursement frais divers / Frais divers
    is_remb_frais  = (str(motif or "").strip().lower() == "remboursement frais divers")
    is_frais_divers = (str(motif or "").strip().lower() == "frais divers")

    if (is_salaire or is_remb_frais or is_frais_divers) and cible_nom_normalise not in ["cb asso7", "caisse asso7"]:
        mode_val = (data.get("mode") or "Compte").strip().lower()
        cible_debit = None
        if mode_val == "compte":
            cible_debit = next((m for m in musiciens if (m.nom or "").strip().lower() == "cb asso7"), None)
        elif mode_val in ("especes", "espèces"):
            cible_debit = next((m for m in musiciens if (m.nom or "").strip().lower() == "caisse asso7"), None)

        if cible_debit:
            db.session.flush()  # garantir op.id
            if is_salaire:
                lib = "Salaire"
            elif is_remb_frais:
                lib = "Remboursement frais"
            else:
                lib = "Frais divers"

            debit_auto = Operation(
                musicien_id=cible_debit.id,
                type="debit",
                motif=f"Débit {lib} {data.get('musicien') or (cible.prenom + ' ' + (cible.nom or ''))}".strip(),
                precision=f"{lib} payé à {data.get('musicien') or (cible.prenom + ' ' + (cible.nom or ''))}".strip(),
                montant=float(montant),
                date=date_op,
                operation_liee_id=op.id,
                auto_debit_salaire=bool(is_salaire)   # flag uniquement pour Salaire
            )
            db.session.add(debit_auto)
            # on lie aussi l'op principale au débit auto
            op.operation_liee_id = debit_auto.id
            db.session.add(op)


    # 🧾 Mise à jour frais sur concert si motif = "Frais" OU "Frais de concerts"
    if (motif or "").strip().lower() in {"frais", "frais de concerts"} and concert_id:
        try:
            concert = Concert.query.get(concert_id)
            if concert:
                # 1) toujours recalculer la somme des frais SQL (évite écarts si modifs/suppressions)
                recalculer_frais_concert(concert.id)
                db.session.flush()  # s'assure que concert.frais est à jour en DB

                # 2) recalcul immédiat des potentiels pour CE concert
                from calcul_participations import mettre_a_jour_credit_calcule_potentiel_pour_concert
                mettre_a_jour_credit_calcule_potentiel_pour_concert(concert.id)
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
        
        # --- RECOMPUTE POTENTIAL (FIX UnboundLocalError) --------------------------
        # Recalcule le crédit potentiel si l'opération est liée à un concert
        cid_raw = data.get("concert_id")
        try:
            cid = int(str(cid_raw).strip()) if cid_raw else None
        except Exception:
            cid = None

        if cid:
            # Import local AVANT l'appel (évite l'UnboundLocalError)
            from calcul_participations import mettre_a_jour_credit_calcule_potentiel_pour_concert
            try:
                mettre_a_jour_credit_calcule_potentiel_pour_concert(cid)
            except Exception as e:
                # On logge mais on ne casse pas la requête
                print(f"[WARN] Recalcul potentiel ignoré pour concert {cid}: {e}")
    # --------------------------------------------------------------------------
            
        print(f"[OK] Operation {motif} enregistrée pour {data.get('musicien')}")

        if concert_id:
            db.session.expire_all()
            concert_verif = Concert.query.get(concert_id)
            print(f"[CHECK] Avant recalcul → concert_id={concert_id}, payé={concert_verif.paye}")
            mettre_a_jour_credit_calcule_potentiel_pour_concert(concert_id)
    except Exception as e:
        db.session.rollback()
        print(f"❌ Erreur lors de l'enregistrement de l'opération : {e}")
        raise


def supprimer_operation_en_db(operation_id: int):
    """
    Supprime une opération et TOUTES ses opérations liées, en cassant d'abord les FK (operation_liee_id) pour éviter
    la violation de contrainte sur la table auto-référente 'operations'.

    Stratégie :
      1) Explore le graphe des liens via operation_liee_id (enfants directs et indirects + pair réciproque éventuel).
      2) Met operation_liee_id = NULL sur TOUTES les lignes qui pointent vers l'un des IDs à supprimer (y compris entre elles).
      3) Supprime les opérations collectées.
      4) Commit + recalcul éventuel si concert associé.
    """
    op = db.session.get(Operation, operation_id)
    if not op:
        raise ValueError(f"Opération ID={operation_id} introuvable.")

    # --- 1) Construire l'ensemble des opérations à supprimer (cascade applicative) ---
    to_delete = set()
    stack = [op]

    seen = set()
    while stack:
        cur = stack.pop()
        if cur.id in seen:
            continue
        seen.add(cur.id)
        to_delete.add(cur)

        # enfants (ceux qui pointent vers cur)
        enfants = Operation.query.filter_by(operation_liee_id=cur.id).all()
        for e in enfants:
            if e.id not in seen:
                stack.append(e)

        # lien réciproque éventuel (cur pointe vers un "pair")
        if cur.operation_liee_id:
            pair = db.session.get(Operation, cur.operation_liee_id)
            if pair and pair.id not in seen:
                stack.append(pair)

    if not to_delete:
        return True

    ids_to_delete = [o.id for o in to_delete]

    # --- 2) Casser TOUTES les références vers ces IDs (y compris références croisées dans le lot) ---
    try:
        # Mettre operation_liee_id = NULL pour toute ligne (dans toute la table) qui référence l'un des IDs
        # synchronize_session=False : plus efficace, on flush ensuite.
        (
            db.session.query(Operation)
            .filter(Operation.operation_liee_id.in_(ids_to_delete))
            .update({Operation.operation_liee_id: None}, synchronize_session=False)
        )
        db.session.flush()

        # --- 3) Supprimer les opérations collectées ---
        # On peut supprimer dans n'importe quel ordre maintenant que les FK sont nullifiées
        for o in to_delete:
            db.session.delete(o)

        db.session.commit()

        # --- 4) Recalcul éventuel si une des opérations supprimées concernait un concert ---
        try:
            # On tente un recalcul minimal : si l'op initiale avait un concert_id
            if getattr(op, "concert_id", None):
                mettre_a_jour_credit_calcule_potentiel_pour_concert(op.concert_id)
        except Exception as e:
            print(f"[WARN] recalcul après suppression op {op.id} : {e}")

        print(f"[OK] Suppression cascade réussie pour opérations {ids_to_delete}")
        return True

    except Exception as e:
        db.session.rollback()
        print(f"❌ Erreur suppression opération {operation_id}: {e}")
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
    if (operation.motif or "").strip().lower() in {"frais", "frais de concerts"} and concert_id:
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
    # Helpers locaux
    def _to_float(x):
        if x is None:
            return None
        s = str(x).strip().replace(",", ".")
        return float(s) if s else None

    def _to_int_or_none(x):
        if x is None:
            return None
        s = str(x).strip()
        return int(s) if s.isdigit() else None

    def _infer_type_from_motif_if_missing(type_val, motif_val, cible_nom_norm):
        t = (type_val or "").strip().lower()
        if t:
            return "credit" if t.startswith("cr") else "debit"
        m = (motif_val or "").strip().lower()
        if m == "salaire":
            return "debit"
        if m == "recette concert":
            return "credit"
        if m == "frais":
            return "debit" if cible_nom_norm in ["cb asso7", "caisse asso7"] else "credit"
        return "debit"

    # Copie modifiable
    data = dict(form_data)

    # Conversion de la date JJ/MM/AAAA → AAAA-MM-JJ si besoin
    if "date" in data and isinstance(data["date"], str) and "/" in data["date"]:
        try:
            jour, mois, annee = data["date"].split("/")
            data["date"] = f"{annee}-{mois.zfill(2)}-{jour.zfill(2)}"
        except Exception as e:
            print("Erreur de conversion date :", data.get("date"), e)
            raise

    # --- Récupération de l'opération principale
    op = db.session.get(Operation, operation_id)
    if not op:
        raise ValueError(f"Opération ID={operation_id} introuvable.")

    # --- Récupération de tous les musiciens
    musiciens = Musicien.query.all()

    # --- Détermination du musicien cible ---
    musicien_id = data.get("musicien")  # ID (str) attendu, mais on tolère legacy nom complet
    nom_saisi = (data.get("musicien_nom") or "").strip().lower()  # Ancien fallback

    cible = None
    if musicien_id:
        # Cherche d'abord par ID
        cible = next((m for m in musiciens if str(m.id) == str(musicien_id)), None)
        if not cible:
            # Cas legacy : nom complet dans "musicien"
            cible = next(
                (m for m in musiciens if f"{(m.prenom or '').strip()} {(m.nom or '').strip()}".strip().lower() == str(musicien_id).strip().lower()),
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

    # Conversion date si nécessaire (à ce stade, data["date"] est au bon format ISO)
    try:
        date_op = datetime.strptime(data["date"], "%Y-%m-%d").date()
    except Exception as e:
        print("Erreur de conversion date :", data["date"], e)
        raise

    # Normalisations champs
    motif = data.get("motif")
    cible_nom_normalise = (cible.nom or "").strip().lower()
    concert_id = _to_int_or_none(data.get("concert_id"))  # <-- fix: '' -> None
    montant_val = _to_float(data.get("montant"))
    brut_val = _to_float(data.get("brut"))
    if montant_val is None:
        raise ValueError("Montant manquant ou invalide.")

    # Type selon motif (même logique que création, avec fallback)
    type_op = _infer_type_from_motif_if_missing(data.get("type"), motif, cible_nom_normalise)

    # --- MAJ de l’opération principale (sans commit)
    op.musicien = cible
    op.date = date_op
    op.type = type_op
    op.mode = data.get("mode")
    op.motif = motif
    op.precision = data.get("precision")
    op.montant = float(montant_val)
    op.brut = float(brut_val) if brut_val is not None else None
    op.concert_id = concert_id  # <-- important pour éviter l'INSERT/UPDATE avec '' sur INTEGER

    db.session.flush()

    # --- Supprimer SEULEMENT les opérations techniques non 'auto_cb_asso7' ---
    # (on garde l'op liée trésorerie pour la mettre à jour juste après)
    operations_techniques = Operation.query.filter_by(operation_liee_id=op.id).all()
    for op_tech in operations_techniques:
        # Si l'attribut n'existe pas, getattr(...) renverra False par défaut
        if getattr(op_tech, "auto_cb_asso7", False):
            continue  # on préserve cette op, elle sera synchronisée ci-dessous
        db.session.delete(op_tech)
    db.session.flush()

    # --- Sync / recréation de l'opération liée auto_cb_asso7 lors d'une MODIFICATION ---
    try:
        cible_nom = (getattr(op.musicien, "nom", "") or "").strip().lower()

        if cible_nom == "asso7":
            mode_val = (str(data.get("mode") or "Compte")).strip().lower()

            # Trouver la cible trésorerie (CB ou CAISSE)
            cb = next((m for m in musiciens if (m.nom or "").strip().lower() == "cb asso7"), None)
            caisse = next((m for m in musiciens if (m.nom or "").strip().lower() == "caisse asso7"), None)

            cible_treso = None
            if mode_val in ("compte", "cb", "carte", "cb asso7"):
                cible_treso = cb
            elif mode_val in ("especes", "espèces", "caisse", "caisse asso7"):
                cible_treso = caisse

            # Retrouver l'opération liée auto (si elle existe encore)
            op_auto = Operation.query.filter_by(
                operation_liee_id=op.id,
                auto_cb_asso7=True
            ).first()

            if cible_treso is None:
                # Pas de cible trésor => on supprime l'op auto si elle existe
                if op_auto:
                    db.session.delete(op_auto)
            else:
                if op_auto:
                    # Mettre à jour l'op liée existante
                    op_auto.musicien_id = cible_treso.id
                    op_auto.type = op.type                       # 'debit' ou 'credit'
                    op_auto.motif = op.motif or ""
                    op_auto.precision = op.precision or f"Auto pour ASSO7 ({mode_val})"
                    op_auto.montant = float(op.montant or 0)
                    op_auto.date = op.date
                    op_auto.concert_id = op.concert_id
                    op_auto.auto_cb_asso7 = True
                else:
                    # Recréer l'op liée si elle a disparu
                    op_auto = Operation(
                        musicien_id=cible_treso.id,
                        type=op.type,
                        motif=op.motif or "",
                        precision=op.precision or f"Auto pour ASSO7 ({mode_val})",
                        montant=float(op.montant or 0),
                        date=op.date,
                        concert_id=op.concert_id,
                        auto_cb_asso7=True,
                        operation_liee_id=op.id
                    )
                    db.session.add(op_auto)
        else:
            # Si ce n'est plus ASSO7, supprimer l'auto-op éventuelle
            op_auto = Operation.query.filter_by(
                operation_liee_id=op.id,
                auto_cb_asso7=True
            ).first()
            if op_auto:
                db.session.delete(op_auto)

    except Exception as e:
        # Utilise ton logger applicatif si disponible
        print("Erreur sync op auto_cb_asso7 lors de la modification:", e)

    # --- Génération des opérations techniques (comme lors de la création) ---
    is_salaire = (motif == "Salaire")
    has_brut = (brut_val is not None and float(brut_val) > 0)
    if is_salaire and has_brut:
        commission = round(float(brut_val) * 0.03, 2)
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
                precision=f"3% brut de {data.get('musicien') or (cible.prenom + ' ' + cible.nom)}",
                montant=commission,
                date=date_op,
                operation_liee_id=op.id
            )
            db.session.add(commission_credit)

    is_remb_frais = (str(motif or "").strip().lower() == "remboursement frais divers")

    # 🔥 Débit automatique du compte payeur (CB/CAISSE) pour Salaire ou Remboursement frais (≠ ASSO7)
    if (is_salaire or is_remb_frais) and cible_nom_normalise not in ["cb asso7", "caisse asso7"]:
        mode_val = (data.get("mode") or "Compte").strip().lower()
        cible_debit = None
        if mode_val == "compte":
            cible_debit = next((m for m in musiciens if (m.nom or "").strip().lower() == "cb asso7"), None)
        elif mode_val in ("especes", "espèces"):
            cible_debit = next((m for m in musiciens if (m.nom or "").strip().lower() == "caisse asso7"), None)

        if cible_debit:
            db.session.flush()
            lib = "Salaire" if is_salaire else "Remboursement frais"
            debit_auto = Operation(
                musicien_id=cible_debit.id,
                type="debit",
                motif=f"Débit {lib} {data.get('musicien') or (cible.prenom + ' ' + (cible.nom or ''))}".strip(),
                precision=f"{lib} payé à {data.get('musicien') or (cible.prenom + ' ' + (cible.nom or ''))}".strip(),
                montant=float(montant_val),
                date=date_op,
                operation_liee_id=op.id,
                auto_debit_salaire=bool(is_salaire)
            )
            db.session.add(debit_auto)
            op.operation_liee_id = debit_auto.id
            db.session.add(op)

    # 🎫 FRAIS DE CONCERT
    if (motif or "").strip().lower() in {"frais", "frais de concerts"} and concert_id:
        try:
            concert = Concert.query.get(concert_id)
            if concert:
                recalculer_frais_concert(concert.id)
        except Exception as e:
            print("⚠️ Erreur mise à jour frais concert:", e)

    db.session.commit()

    # ✅ Recalcul du partage du concert concerné (après commit et rechargement)
    if concert_id:
        try:
            from calcul_participations import partage_benefices_concert, mettre_a_jour_credit_calcule_potentiel
            db.session.expire_all()
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



# --- Back-compat: options de motifs par bénéficiaire ---
def motifs_pour_beneficiaire(nom_beneficiaire: str) -> list[str]:
    """
    Ancien helper utilisé par certaines vues.
    Retourne une liste de motifs suggérés selon le bénéficiaire.
    """
    b = (nom_beneficiaire or "").strip().lower()
    structures = {"asso7", "cb asso7", "caisse asso7", "treso asso7"}
    if b in structures:
        # pour comptes structure/asso7
        return [
            "Recette concert",
            "Frais",
            "Commission Lionel",
            "Virement",
            "Divers",
        ]
    # pour musiciens "personnes"
    return [
        "Salaire",
        "Remboursement frais divers",
        "Frais",
        "Virement",
        "Divers",
    ]


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




from sqlalchemy import or_, func, not_

def get_tous_musiciens_actifs():
    """
    Musiciens actifs à proposer dans 'Déclarer un cachet'.
    Inclut type 'musicien' ET 'personne' (legacy), et accepte NULL/vides.
    Exclut les structures (ASSO7, CB ASSO7, CAISSE ASSO7, TRESO ASSO7).
    """
    structures_noms = {"asso7", "cb asso7", "caisse asso7", "treso asso7"}

    return (
        Musicien.query
        .filter(
            Musicien.actif.is_(True),
            # exclure les structures par leur nom (sécurité)
            not_(func.lower(func.trim(Musicien.nom)).in_(structures_noms)),
            # accepter plusieurs types "humains"
            or_(
                Musicien.type.is_(None),
                func.trim(Musicien.type) == "",
                func.lower(Musicien.type).in_(["musicien", "personne"])
            )
        )
        .order_by(Musicien.prenom, Musicien.nom)
        .all()
    )


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




from collections import defaultdict
from datetime import date


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



def region_from_cp(cp: str) -> str:
    """
    Retourne une région en MAJUSCULES depuis un code postal FR.
    Bretagne priorisée ailleurs dans l'affichage, ici on mappe juste.
    """
    if not cp:
        return "DIVERS"
    s = str(cp).strip().replace(' ', '')
    if len(s) < 2:
        return "DIVERS"

    # Corse : CP commence par 20xxx
    if s.startswith('20'):
        return "CORSE"

    # Outre-mer
    if s.startswith('97') or s.startswith('98'):
        return "OUTRE-MER"

    dep = s[:2]
    # mapping départements -> régions (Métropole)
    R = {
        # AUVERGNE-RHÔNE-ALPES
        '01':'AUVERGNE-RHÔNE-ALPES','03':'AUVERGNE-RHÔNE-ALPES','07':'AUVERGNE-RHÔNE-ALPES',
        '15':'AUVERGNE-RHÔNE-ALPES','26':'AUVERGNE-RHÔNE-ALPES','38':'AUVERGNE-RHÔNE-ALPES',
        '42':'AUVERGNE-RHÔNE-ALPES','43':'AUVERGNE-RHÔNE-ALPES','63':'AUVERGNE-RHÔNE-ALPES',
        '69':'AUVERGNE-RHÔNE-ALPES','73':'AUVERGNE-RHÔNE-ALPES','74':'AUVERGNE-RHÔNE-ALPES',
        # BOURGOGNE-FRANCHE-COMTÉ
        '21':'BOURGOGNE-FRANCHE-COMTÉ','25':'BOURGOGNE-FRANCHE-COMTÉ','39':'BOURGOGNE-FRANCHE-COMTÉ',
        '58':'BOURGOGNE-FRANCHE-COMTÉ','70':'BOURGOGNE-FRANCHE-COMTÉ','71':'BOURGOGNE-FRANCHE-COMTÉ',
        '89':'BOURGOGNE-FRANCHE-COMTÉ','90':'BOURGOGNE-FRANCHE-COMTÉ',
        # BRETAGNE
        '22':'BRETAGNE','29':'BRETAGNE','35':'BRETAGNE','56':'BRETAGNE',
        # CENTRE-VAL DE LOIRE
        '18':'CENTRE-VAL DE LOIRE','28':'CENTRE-VAL DE LOIRE','36':'CENTRE-VAL DE LOIRE',
        '37':'CENTRE-VAL DE LOIRE','41':'CENTRE-VAL DE LOIRE','45':'CENTRE-VAL DE LOIRE',
        # GRAND EST
        '08':'GRAND EST','10':'GRAND EST','51':'GRAND EST','52':'GRAND EST','54':'GRAND EST',
        '55':'GRAND EST','57':'GRAND EST','67':'GRAND EST','68':'GRAND EST','88':'GRAND EST',
        # HAUTS-DE-FRANCE
        '02':'HAUTS-DE-FRANCE','59':'HAUTS-DE-FRANCE','60':'HAUTS-DE-FRANCE',
        '62':'HAUTS-DE-FRANCE','80':'HAUTS-DE-FRANCE',
        # ÎLE-DE-FRANCE
        '75':'ÎLE-DE-FRANCE','77':'ÎLE-DE-FRANCE','78':'ÎLE-DE-FRANCE','91':'ÎLE-DE-FRANCE',
        '92':'ÎLE-DE-FRANCE','93':'ÎLE-DE-FRANCE','94':'ÎLE-DE-FRANCE','95':'ÎLE-DE-FRANCE',
        # NORMANDIE
        '14':'NORMANDIE','27':'NORMANDIE','50':'NORMANDIE','61':'NORMANDIE','76':'NORMANDIE',
        # NOUVELLE-AQUITAINE
        '16':'NOUVELLE-AQUITAINE','17':'NOUVELLE-AQUITAINE','19':'NOUVELLE-AQUITAINE',
        '23':'NOUVELLE-AQUITAINE','24':'NOUVELLE-AQUITAINE','33':'NOUVELLE-AQUITAINE',
        '40':'NOUVELLE-AQUITAINE','47':'NOUVELLE-AQUITAINE','64':'NOUVELLE-AQUITAINE',
        '79':'NOUVELLE-AQUITAINE','86':'NOUVELLE-AQUITAINE','87':'NOUVELLE-AQUITAINE',
        # OCCITANIE
        '09':'OCCITANIE','11':'OCCITANIE','12':'OCCITANIE','30':'OCCITANIE','31':'OCCITANIE',
        '32':'OCCITANIE','34':'OCCITANIE','46':'OCCITANIE','48':'OCCITANIE','65':'OCCITANIE',
        '66':'OCCITANIE','81':'OCCITANIE','82':'OCCITANIE',
        # PAYS DE LA LOIRE
        '44':'PAYS DE LA LOIRE','49':'PAYS DE LA LOIRE','53':'PAYS DE LA LOIRE',
        '72':'PAYS DE LA LOIRE','85':'PAYS DE LA LOIRE',
        # PROVENCE-ALPES-CÔTE D'AZUR
        '04':'PROVENCE-ALPES-CÔTE D\'AZUR','05':'PROVENCE-ALPES-CÔTE D\'AZUR',
        '06':'PROVENCE-ALPES-CÔTE D\'AZUR','13':'PROVENCE-ALPES-CÔTE D\'AZUR',
        '83':'PROVENCE-ALPES-CÔTE D\'AZUR','84':'PROVENCE-ALPES-CÔTE D\'AZUR',
    }
    return R.get(dep, "DIVERS")
