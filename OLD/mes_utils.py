# ─────────────────────────────────────────────
# 1. 📦 IMPORTS & CONSTANTES
# ─────────────────────────────────────────────

from models import Musicien, Participation, Report, Concert, db
from datetime import date, datetime
from models import Operation
from pathlib import Path
import json
import sqlite3



# ─────────────────────────────────────────────
# 2. 🗃️ CHARGEMENT / SAUVEGARDE JSON & SQLITE
# ─────────────────────────────────────────────

# def sauvegarder_json(filepath, data):
# def charger_json(filepath):
# def get_operations_dict():
def get_reports_dict(musiciens):
    d = {}
    for m in musiciens:
        key = f"{(m.prenom or '').strip()} {(m.nom or '').strip()}".strip()
        report = Report.query.filter_by(musicien_id=m.id).first()
        d[key] = report.montant if report else 0.0
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

def get_musiciens_dict():
    return {m.id: m for m in Musicien.query.all()}



def calculer_credit_actuel(musicien, concerts):
    aujourd_hui = date.today()
    credit = 0.0

    is_cb_asso7 = (musicien.nom or '').strip().lower() == "cb asso7"

    if is_cb_asso7:
        for concert in concerts:
            if concert.recette and concert.date <= aujourd_hui and concert.paye:
                credit += concert.recette

        operations = Operation.query.filter_by(musicien_id=musicien.id).all()
        for op in operations:
            if op.date <= aujourd_hui:
                op_type = (op.type or "").lower()

                if op_type == "debit":
                    # ⚠️ Ne pas double-compter les auto-générées
                    credit -= op.montant or 0
                elif op_type == "credit":
                    # ⚠️ Ne prendre en compte que les crédits manuels
                    if not getattr(op, "auto_cb_asso7", False):
                        credit += op.montant or 0

        return credit

    # Pour tous les autres musiciens
    for concert in concerts:
        if concert.date > aujourd_hui or not concert.paye:
            continue
        credits, credit_asso7, _ = partage_benefices_concert(concert)
        if musicien.nom == "ASSO7":
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

    if (musicien.nom or '').strip().lower() == "cb asso7":
        for concert in concerts:
            # ✅ Inclure toutes les recettes des concerts NON PAYÉS, qu'ils soient futurs ou passés
            if concert.recette and not concert.paye:
                credit += concert.recette

        # ✅ On conserve la logique : opérations futures seulement
        operations = Operation.query.filter_by(musicien_id=musicien.id).all()
        for op in operations:
            if op.date > aujourd_hui:
                if op.type == "debit":
                    credit -= op.montant or 0
                elif op.type == "credit":
                    credit += op.montant or 0
        return credit

    for concert in concerts:
        # ✅ Inclure tous les concerts non payés, qu'ils soient passés ou futurs
        if concert.paye:
            continue
        credits, credit_asso7, _ = partage_benefices_concert(concert)
        if musicien.nom == "ASSO7":
            credit += credit_asso7 or 0
        else:
            credit += credits.get(musicien.id, 0)

    # ✅ On conserve la logique : opérations futures seulement
    operations = Operation.query.filter_by(musicien_id=musicien.id).all()
    for op in operations:
        if op.date > aujourd_hui:
            if op.type == "debit":
                credit -= op.montant or 0
            elif op.type == "credit":
                credit += op.montant or 0

    return credit



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



# ─────────────────────────────────────────────
# 4. 🎤 GESTION DES CONCERTS & PARTICIPATIONS
# ─────────────────────────────────────────────

def partage_benefices_concert(concert):
    """
    Calcule le partage du bénéfice d'un concert :
    - 10% à Jérôme Arnould (si présent)
    - 90% à répartir à parts égales entre TOUS les participants + 1 part pour ASSO7
    Retourne :
        - credits : {musicien_id: crédit_calculé}
        - credit_asso7 : crédit attribué à ASSO7
        - credit_jerome : crédit total de Jérôme (10% + part variable)
    """
    if concert.recette is None:
        return {}, 0.0, 0.0

    frais = concert.frais if concert.frais is not None else 0
    benefice = concert.recette - frais

    participations = Participation.query.filter_by(concert_id=concert.id).all()
    if not participations:
        return {}, 0.0, 0.0

    jerome = Musicien.query.filter(
        db.func.lower(Musicien.prenom) == "jérôme",
        db.func.lower(Musicien.nom) == "arnould"
    ).first()
    jerome_id = jerome.id if jerome else None

    jerome_present = any(p.musicien_id == jerome_id for p in participations) if jerome_id else False
    jerome_bonus = benefice * 0.10 if jerome_present else 0.0
    reste = benefice - jerome_bonus

    nb_parts = len(participations) + 1  # +1 pour ASSO7
    part = reste / nb_parts if nb_parts else 0.0

    credits = {}
    for p in participations:
        if p.musicien_id == jerome_id:
            credits[p.musicien_id] = round(jerome_bonus + part, 2)
        else:
            credits[p.musicien_id] = round(part, 2)

    credit_asso7 = round(part, 2)
    credit_jerome = credits.get(jerome_id, 0.0)

    return credits, credit_asso7, credit_jerome
    
def get_credits_concerts(concerts):
    credits_musiciens = {}
    credits_asso7 = {}
    credits_jerome = {}
    for concert in concerts:
        credits, credit_asso7, credit_jerome = partage_benefices_concert(concert)
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



# ─────────────────────────────────────────────
# 5. 💸 GESTION DES OPÉRATIONS
# ─────────────────────────────────────────────


def enregistrer_operation_en_db(data):
    nom_saisi = (data["musicien"] or "").strip().lower()
    musiciens = Musicien.query.all()

    cible = next(
        (m for m in musiciens if f"{(m.prenom or '').strip()} {(m.nom or '').strip()}".strip().lower() == nom_saisi),
        None
    )
    if not cible:
        raise ValueError(f"Musicien introuvable pour le nom : {data['musicien']}")

    date_op = datetime.strptime(data["date"], "%Y-%m-%d").date()

    op = Operation(
        musicien_id=cible.id,
        type=data["type"],
        motif=data["motif"],
        precision=data.get("precision", ""),
        montant=float(data["montant"]),
        date=date_op,
        brut=float(data["brut"]) if data.get("brut") else None,
        concert_id=data.get("concert_id")
    )
    db.session.add(op)
    db.session.flush()  # permet de récupérer op.id

    # 💼 COMMISSION LIONEL POUR SALAIRES
    is_salaire = data["motif"] == "Salaire"
    has_brut = data.get("brut") and float(data["brut"]) > 0
    if is_salaire and has_brut and nom_saisi != "lionel arnould":
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

    # 💥 DEBIT AUTO CB ASSO7 POUR TOUT DEBIT NON-GÉNÉRÉ
    cible_nom_normalise = (cible.nom or "").strip().lower()
    print(f"➡️ Génération CB ASSO7 ? cible={cible_nom_normalise}, type={data['type']}, motif={data['motif']}")

    if data["type"] == "debit" and data["motif"] != "Commission Lionel" and cible_nom_normalise != "cb asso7":
        cb_asso7 = next((m for m in musiciens if (m.nom or "").strip().lower() == "cb asso7"), None)
        if cb_asso7:
            db.session.flush()
            debit_cb_asso7 = Operation(
                musicien_id=cb_asso7.id,
                type="debit",
                motif=f"Débit pour {data['musicien']}",
                precision=f"Retrait lié à {data['motif']}",
                montant=float(data["montant"]),
                date=date_op,
                operation_liee_id=op.id,
                auto_cb_asso7=True
            )
            db.session.add(debit_cb_asso7)

            # Mise à jour du lien inverse (op vers CB_ASSO7)
            op.operation_liee_id = debit_cb_asso7.id
            db.session.add(op)

    # 🎫 FRAIS DE CONCERT
    if data["motif"].lower() == "frais" and data.get("concert_id"):
        try:
            concert = Concert.query.get(data["concert_id"])
            if concert:
                concert.frais = (concert.frais or 0.0) + float(data["montant"])
                db.session.add(concert)
        except Exception as e:
            print("⚠️ Erreur mise à jour frais concert:", e)

    db.session.commit()

def annuler_operation(id):
    operation = db.session.get(Operation, id)
    if not operation:
        print(f"❌ Opération ID={id} introuvable.")
        return False

    # Supprime toutes les opérations qui sont liées à cette opération (inverse ou directe)
    if operation.operation_liee_id:
        liee = db.session.get(Operation, operation.operation_liee_id)
        if liee:
            db.session.delete(liee)

    liees_inverse = Operation.query.filter_by(operation_liee_id=operation.id).all()
    for op_liee in liees_inverse:
        db.session.delete(op_liee)

    # Si frais, déduire du concert
    if operation.motif.lower() == "frais" and operation.concert_id:
        concert = Concert.query.get(operation.concert_id)
        if concert and concert.frais:
            concert.frais = max(0.0, concert.frais - (operation.montant or 0.0))
            db.session.add(concert)

    db.session.delete(operation)
    db.session.commit()
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
    musiciens_normaux = [dict(m) for m in musiciens if m["nom"] not in ("ASSO7", "CB ASSO7")]
    structures = [dict(m) for m in musiciens if m["nom"] in ("ASSO7", "CB ASSO7")]
    return musiciens_normaux, structures

def preparer_concerts_js(concerts):
    return [
        {
            "id": c["id"],
            "date": c["date"] if isinstance(c["date"], str)
                else c["date"].strftime("%Y-%m-%d"),
            "lieu": c["lieu"]
        }
        for c in concerts
    ]

from models import Concert

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
    Génère la liste des comptes pour chaque musicien et structure.
    Retourne :
        - tableau_comptes : liste de dictionnaires avec crédits et infos.
        - musiciens_length : nombre de musiciens dans la liste (utile pour affichage).
    """
    # Récupère tous les concerts en base pour optimiser les appels en cascade
    concerts = Concert.query.all()

    # Tous les musiciens actifs (type = 'musicien')
    musiciens = [m for m in Musicien.query.filter_by(actif=True, type='musicien').all()]

    # Structures spécifiques à traiter à part (ordre important : ASSO7 puis CB ASSO7)
    asso7 = Musicien.query.filter_by(nom='ASSO7').first()
    cb_asso7 = Musicien.query.filter_by(nom='CB ASSO7').first()

    tableau_comptes = []

    # 1. Comptes des musiciens physiques (prénom + nom)
    for m in musiciens:
        tableau_comptes.append({
            'nom': f"{m.prenom} {m.nom}".strip(),
            'credit_actuel': calculer_credit_actuel(m, concerts),
            'gains_a_venir': calculer_gains_a_venir(m, concerts),
            'credit_potentiel': calculer_credit_potentiel(m, concerts),
            'type': 'musicien'
        })

    # 2. Comptes des structures
    structures = []
    for s in (asso7, cb_asso7):
        if s:
            structures.append({
                'nom': s.nom,
                'credit_actuel': calculer_credit_actuel(s, concerts),
                'gains_a_venir': calculer_gains_a_venir(s, concerts),
                'credit_potentiel': calculer_credit_potentiel(s, concerts),
                'type': 'structure'
            })

    # Nombre de musiciens avant d'ajouter les structures (utile pour séparer dans l'affichage)
    musiciens_length = len(tableau_comptes)

    # Ajoute les structures à la fin du tableau
    tableau_comptes.extend(structures)

    return tableau_comptes, musiciens_length
