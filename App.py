# 📦 Standard Python
import os
import json
import locale
import sqlite3
import calendar
import io
from datetime import date, datetime
from collections import OrderedDict, defaultdict
from urllib.parse import quote

# 🌐 Flask & extensions
from flask import Flask, render_template, request, redirect, url_for, flash, current_app, jsonify, Response, send_file
from flask_migrate import Migrate
from flask_mail import Mail, Message
from dotenv import load_dotenv
from sqlalchemy.orm import joinedload
from sqlalchemy import or_, and_
from werkzeug.utils import secure_filename

from exports import generer_export_excel
from mes_utils import format_currency
print("format_currency importé depuis mes_utils :", format_currency)

# Chargement des variables d’environnement
load_dotenv("env.txt")


# Création de l'application Flask
app = Flask(__name__)
app.jinja_env.filters['format_currency'] = format_currency
app.secret_key = "kE9t#sgdFE35zgjKJlkj98_!9"


# --- Pour le mode local SQLite
db_path = os.path.join(os.path.dirname(__file__), "instance", "musiciens.db")
sqlite_url = f"sqlite:///{db_path}"

# Si DATABASE_URL n'est pas défini, on prend SQLite local
database_url = os.getenv('DATABASE_URL', sqlite_url)

# Normaliser pour psycopg v3
if database_url.startswith("postgres://"):
    # Cas Heroku / anciennes URLs
    database_url = database_url.replace("postgres://", "postgresql+psycopg://", 1)
elif database_url.startswith("postgresql://") and "+psycopg" not in database_url:
    # Force l'URL à utiliser psycopg v3
    database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False



# Configuration mail
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 25))  # attention à bien caster en int
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'False') == 'True'
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER')


# Initialisation des extensions
from models import db
db.init_app(app)
migrate = Migrate(app, db)
mail = Mail(app)

print("Base utilisée :", database_url)

# 📁 Modules internes

from models import Musicien, Concert, Participation, Operation, Cachet, Report
from mes_utils import (
    partage_benefices_concert, calculer_credit_actuel,
    calculer_gains_a_venir, calculer_credit_potentiel,
    concerts_groupes_par_mois, get_credits_concerts_from_db, get_musiciens_dict,
    get_cachets_par_mois, log_mail_envoye, annuler_operation,
    preparer_concerts_js, preparer_concerts_data, preparer_concerts_par_musicien,
    charger_musiciens_et_concerts_sqlite, separer_structures_et_musiciens,
    saison_from_date, saisons_from_dates, get_saison_actuelle,
    concerts_non_payes, charger_concerts, generer_tableau_comptes,
    enregistrer_participations, modifier_operation_en_db,
    musicien_to_dict, get_tous_musiciens_actifs, verifier_ou_creer_structures,
    ajouter_cachets, formulaire_to_data, enregistrer_operation_en_db,
    valider_concert_par_operation, concert_to_dict, get_debut_fin_saison,
    get_ordered_comptes_bis, get_reports_dict, extraire_infos_depuis_pdf,
    mois_fr, regrouper_cachets_par_mois, basculer_statut_paiement_concert,
)

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

# ------------ ROUTES DE BASE ------------

@app.route('/')
def index():
    # Option 1 : Afficher directement l'accueil
    return render_template('accueil.html')

    # Option 2 : Rediriger vers /accueil (décommenter la ligne ci-dessous si tu préfères)
    # return redirect(url_for('accueil'))

@app.route('/accueil')
def accueil():
    return render_template('accueil.html')


# ---------- ROUTES CRUD MUSICIEN ----------

# Lire/lister
@app.route('/musiciens')
def liste_musiciens():
    valeur = request.args.getlist('actifs_uniquement')
    actifs_uniquement = 'on' in valeur or valeur == []  # défaut : coché
    musiciens = Musicien.query.filter(or_(Musicien.type == 'personne', Musicien.type == 'musicien'))
    if actifs_uniquement:
        musiciens = musiciens.filter_by(actif=True)
    musiciens = musiciens.all()
    structures = Musicien.query.filter_by(type='structure').all()
    return render_template(
        'musiciens.html',
        musiciens=musiciens,
        structures=structures,
        actifs_uniquement=actifs_uniquement
    )




from sqlalchemy import func, or_, not_

# Créer/ajouter
@app.route('/ajouter_musicien', methods=['GET', 'POST'])
def ajouter_musicien():
    erreur = None
    # pour re-remplir le formulaire en cas d'erreur
    form_vals = {
        "prenom": (request.form.get('prenom') or '').strip(),
        "nom": (request.form.get('nom') or '').strip(),
        "type": (request.form.get('type') or '').strip(),
        "actif": request.form.get('actif')
    }

    if request.method == 'POST':
        prenom_raw = (request.form.get('prenom') or '').strip()
        nom_raw    = (request.form.get('nom') or '').strip()
        type_raw   = (request.form.get('type') or '').strip().lower()
        actif_raw  = (request.form.get('actif') or '').strip().lower()
        actif      = actif_raw in ('on', 'true', '1', 'yes')

        # --- Normalisations ---
        # mappe l'ancien "personne" vers "musicien"
        mapping_type = {
            "personne": "musicien",
            "musicien": "musicien",
            "musiciens": "musicien",
            "structure": "structure",
            "structures": "structure",
            "asso": "structure",
            "association": "structure",
        }
        type_val = mapping_type.get(type_raw, type_raw)

        # nettoyage basique
        def _clean(s):
            return " ".join((s or "").replace("\xa0", " ").split())

        prenom = _clean(prenom_raw)
        nom    = _clean(nom_raw)

        # Mise en forme d'affichage
        def _fmt_nom_personne(n):
            # NOM en majuscules
            return (n or "").upper()

        def _fmt_prenom(p):
            # Jérôme → Jérôme (title-case simple)
            return p.capitalize() if p else ""

        def _fmt_nom_structure(n):
            # Structures en MAJ (ASSO7, CB ASSO7…)
            return (n or "").upper()

        # --- Règles de validation ---
        if not nom:
            erreur = "Le nom est obligatoire."
        elif type_val not in ('musicien', 'structure'):
            erreur = "Type invalide. Choisissez 'musicien' ou 'structure'."
        elif type_val == 'musicien' and not prenom:
            erreur = "Le prénom est obligatoire pour un musicien."

        # --- Vérifs doublons + insertion ---
        if not erreur:
            if type_val == 'musicien':
                nom_fmt = _fmt_nom_personne(nom)
                prenom_fmt = _fmt_prenom(prenom)

                # doublon insensible à la casse/espaces
                exist = (
                    Musicien.query
                    .filter(
                        func.lower(func.trim(Musicien.nom)) == nom.lower(),
                        func.lower(func.trim(Musicien.prenom)) == prenom.lower()
                    )
                    .first()
                )
                if exist:
                    erreur = "Ce musicien existe déjà."
                else:
                    m = Musicien(
                        nom=nom_fmt,
                        prenom=prenom_fmt,
                        type='musicien',
                        actif=actif
                    )
                    db.session.add(m)
                    db.session.commit()
                    return redirect(url_for('liste_musiciens'))

            else:  # structure
                nom_fmt = _fmt_nom_structure(nom)
                # prenom forcé vide pour structure
                exist = (
                    Musicien.query
                    .filter(
                        func.lower(func.trim(Musicien.nom)) == nom.lower(),
                        or_(Musicien.prenom.is_(None), func.trim(Musicien.prenom) == "")
                    )
                    .first()
                )
                if exist:
                    erreur = "Cette structure existe déjà."
                else:
                    m = Musicien(
                        nom=nom_fmt,
                        prenom="",
                        type='structure',
                        actif=actif
                    )
                    db.session.add(m)
                    db.session.commit()
                    return redirect(url_for('liste_musiciens'))

    # GET ou POST avec erreur → on réaffiche le formulaire avec le message
    return render_template('ajouter_musicien.html', erreur=erreur, **form_vals)



# Mettre à jour/modifier
@app.route('/musicien/modifier/<int:musicien_id>', methods=['GET', 'POST'])
def modifier_musicien(musicien_id):
    musicien = Musicien.query.get_or_404(musicien_id)
    if request.method == 'POST':
        musicien.prenom = request.form['prenom']
        musicien.nom = request.form['nom']
        musicien.actif = 'actif' in request.form
        db.session.commit()
        return redirect(url_for('liste_musiciens'))
    return render_template('modifier_musicien.html', musicien=musicien)

# Supprimer
@app.route('/musicien/supprimer/<int:musicien_id>', methods=['POST'])
def supprimer_musicien(musicien_id):
    # Suppression participations
    Participation.query.filter_by(musicien_id=musicien_id).delete()
    # Suppression du musicien
    musicien = Musicien.query.get_or_404(musicien_id)
    db.session.delete(musicien)
    db.session.commit()
    flash("Musicien supprimé avec succès", "success")
    return redirect(url_for('liste_musiciens'))




# --------- CRUD CONCERTS ---------

# Lire/lister


@app.route('/concerts')
def liste_concerts():
    today = date.today()
    concerts = Concert.query.filter(Concert.date >= today).order_by(Concert.date).all()

    musiciens = Musicien.query.all()
    musiciens_dict = {m.id: m for m in musiciens}

    from mes_utils import get_credits_concerts_from_db
    credits_musiciens, credits_asso7, credits_jerome = get_credits_concerts_from_db(concerts)

    return render_template(
        'concerts.html',
        concerts=concerts,
        credits_musiciens=credits_musiciens,
        credits_asso7=credits_asso7,
        musiciens_dict=musiciens_dict
    )




@app.route('/concert/ajouter', methods=['GET', 'POST'])
def ajouter_concert():
    if request.method == 'POST':
        # Récupération des infos du formulaire
        date_str = request.form['date']
        lieu = request.form['lieu']
        recette_str = request.form.get('recette')
        recette = float(recette_str) if recette_str else None
        paye = 'paye' in request.form
        mode_paiement_prevu = request.form.get('mode_paiement_prevu', 'CB ASSO7')

        # Création du concert
        concert = Concert(
            date=datetime.strptime(date_str, '%Y-%m-%d').date(),
            lieu=lieu,
            paye=paye,
            mode_paiement_prevu=mode_paiement_prevu
        )

        # Affectation correcte selon le statut "payé"
        if paye:
            concert.recette = recette
        else:
            concert.recette_attendue = recette

        db.session.add(concert)
        db.session.commit()

        db.session.refresh(concert)  # <- forcer la mise à jour en base

        # Si payé, créer une opération de crédit
        if paye and mode_paiement_prevu and recette:
            from models import Musicien, Operation
            compte = Musicien.query.filter_by(nom=mode_paiement_prevu).first()
            if compte:
                op = Operation(
                    musicien_id=compte.id,
                    type='credit',
                    motif='Recette concert',
                    montant=recette,
                    date=datetime.strptime(date_str, '%Y-%m-%d').date(),
                    concert_id=concert.id
                )
                db.session.add(op)
                db.session.commit()

        from calcul_participations import mettre_a_jour_credit_calcule_potentiel
        mettre_a_jour_credit_calcule_potentiel()


        return redirect(url_for('liste_participations', concert_id=concert.id))

    return render_template('ajouter_concert.html')


@app.route('/concert/modifier/<int:concert_id>', methods=['GET', 'POST'])
def modifier_concert(concert_id):
    concert = Concert.query.get_or_404(concert_id)

    if request.method == 'POST':
        concert.date = date.fromisoformat(request.form['date'])
        concert.lieu = request.form['lieu']
        recette_input = request.form['recette']

        if recette_input:
            recette_float = float(recette_input)
            if concert.paye:
                concert.recette = recette_float
                concert.recette_attendue = None  # Nettoyage par sécurité
            else:
                concert.recette_attendue = recette_float
                concert.recette = None  # Nettoyage par sécurité
        else:
            concert.recette = None
            concert.recette_attendue = None

        db.session.commit()

        # 🔁 Mise à jour automatique des crédits potentiels
        from calcul_participations import mettre_a_jour_credit_calcule_potentiel
        mettre_a_jour_credit_calcule_potentiel()

        # Redirection logique
        concert_date = concert.date
        concert_paye = concert.paye
        today = date.today()

        if concert_date < today:
            if concert_paye:
                saison = saison_from_date(concert_date).replace('/', '-')
                return redirect(url_for('archives_concerts_saison', saison=saison))
            else:
                return redirect(url_for('concerts_non_payes_view'))
        else:
            return redirect(url_for('liste_concerts'))

    retour_url = url_for('liste_concerts')
    return render_template('modifier_concert.html', concert=concert, retour_url=retour_url)




@app.route('/concert/supprimer/<int:concert_id>', methods=['POST'])
def supprimer_concert(concert_id):
    concert = Concert.query.get_or_404(concert_id)

    # On garde les infos nécessaires avant la suppression
    concert_date = concert.date
    concert_paye = concert.paye

    # 🔥 Supprimer toutes les opérations associées à ce concert (recettes, frais, etc.)
    operations = Operation.query.filter_by(concert_id=concert_id).all()
    for op in operations:
        # Supprimer les opérations liées (commissions, débits automatiques...)
        liees = Operation.query.filter(
            (Operation.operation_liee_id == op.id) | (Operation.id == op.operation_liee_id)
        ).all()
        for op_liee in liees:
            db.session.delete(op_liee)

        db.session.delete(op)

    # 🔄 Supprimer aussi les participations liées au concert si pertinent
    participations = Participation.query.filter_by(concert_id=concert_id).all()
    for p in participations:
        db.session.delete(p)

    # Suppression du concert lui-même
    db.session.delete(concert)
    db.session.commit()

    # 🔁 Mise à jour automatique des crédits potentiels
    from calcul_participations import mettre_a_jour_credit_calcule_potentiel
    mettre_a_jour_credit_calcule_potentiel()

    # Redirection logique en fonction des infos conservées
    today = date.today()
    if concert_date < today:
        if concert_paye:
            saison = saison_from_date(concert_date).replace('/', '-')
            return redirect(url_for('archives_concerts_saison', saison=saison))
        else:
            return redirect(url_for('concerts_non_payes_view'))
    else:
        return redirect(url_for('liste_concerts'))


@app.route('/concerts_non_payes')
def concerts_non_payes_view():
    today = date.today()
    concerts = Concert.query.filter(
        Concert.paye.is_(False),
        Concert.date <= today
    ).order_by(Concert.date.desc()).all()

    musiciens = Musicien.query.all()
    musiciens_dict = {m.id: m for m in musiciens}

    from mes_utils import get_credits_concerts_from_db
    credits_musiciens, credits_asso7, credits_jerome = get_credits_concerts_from_db(concerts)

    return render_template(
        'concerts_non_payes.html',
        concerts=concerts,
        credits_musiciens=credits_musiciens,
        credits_asso7=credits_asso7,
        musiciens_dict=musiciens_dict
    )


from calcul_participations import mettre_a_jour_credit_calcule_potentiel_pour_concert

from sqlalchemy import func  # si pas déjà importé

@app.route('/concerts/<int:concert_id>/toggle_paye', methods=['POST'])
def toggle_concert_paye(concert_id):
    concert = Concert.query.get(concert_id)
    if not concert:
        return "Concert non trouvé", 404

    etat_cible = not concert.paye
    try:
        res = basculer_statut_paiement_concert(concert_id, paye=etat_cible)
        # même comportement qu'avant côté redirection
        return redirect(url_for('archives_concerts' if etat_cible else 'liste_concerts'))
    except Exception as e:
        print(f"❌ toggle_paye error concert {concert_id}: {e}")
        return "Erreur serveur", 500


from calcul_participations import mettre_a_jour_credit_calcule_potentiel_pour_concert

@app.route("/valider_paiement_concert", methods=["POST"])
def valider_paiement_concert():
    # import ici pour éviter les import cycles et s'assurer que la dernière version est utilisée
    from mes_utils import basculer_statut_paiement_concert

    data_json = request.get_json(silent=True) or {}
    data_form = request.form.to_dict() if request.form else {}
    data = {**data_form, **data_json}

    try:
        app.logger.info(f"[valider_paiement_concert] Payload reçu: {data}")
    except Exception:
        print(f"[valider_paiement_concert] Payload reçu: {data}")

    def _to_int(x):
        try:
            return int(str(x).strip())
        except Exception:
            return None

    def _to_float(x):
        if x is None:
            return None
        s = str(x).strip().replace(",", ".")
        if not s:
            return None
        try:
            return float(s)
        except Exception:
            return None

    concert_id = _to_int(data.get("concert_id") or data.get("concertId"))
    if concert_id is None:
        return jsonify(success=False, message="concert_id manquant ou invalide"), 422

    compte = (data.get("compte") or "").strip()
    recette_val = _to_float(data.get("recette"))

    concert = Concert.query.get(concert_id)
    if not concert:
        return jsonify(success=False, message=f"Concert introuvable (id={concert_id})"), 404

    try:
        res = basculer_statut_paiement_concert(
            concert_id=concert_id,
            paye=True,
            montant=recette_val,   # None => prendra recette_attendue
            mode=compte            # "CB ASSO7" / "CAISSE ASSO7" / "Compte" / "Espèces"
        )
        return jsonify(success=True, **res)
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify(success=False, message=f"Erreur: {e}"), 500




from calcul_participations import mettre_a_jour_credit_calcule_potentiel_pour_concert

@app.route("/annuler_paiement_concert", methods=["POST"])
def annuler_paiement_concert():
    data = request.get_json(silent=True) or {}
    concert_id = data.get("concert_id")
    try:
        res = basculer_statut_paiement_concert(int(concert_id), paye=False)
        return jsonify(success=True, **res)
    except Exception as e:
        return jsonify(success=False, message=str(e)), 500




# --------- CRUD PARTICIPATIONS ---------
@app.route('/concert/<int:concert_id>/participations', methods=['GET', 'POST'])
def liste_participations(concert_id):
    concert = Concert.query.get_or_404(concert_id)
    musiciens = Musicien.query.filter(
        Musicien.actif.is_(True),
        ~Musicien.nom.ilike('%ASSO7%'),
        ~Musicien.prenom.ilike('%ASSO7%')
    ).order_by(Musicien.nom).all()

    # Trouver Jérôme
    jerome = Musicien.query.filter(
        db.func.lower(Musicien.nom) == "arnould",
        db.func.lower(Musicien.prenom).like("jérôme%")
    ).first()
    jerome_id = jerome.id if jerome else None

    if request.method == 'POST':
        participants_ids = set(int(mid) for mid in request.form.getlist('participants'))
        enregistrer_participations(concert.id, participants_ids, jerome_id=jerome_id)

        # ✅ Appel du recalcul des participations après validation
        from calcul_participations import mettre_a_jour_credit_calcule_potentiel_pour_concert
        mettre_a_jour_credit_calcule_potentiel_pour_concert(concert.id)

        # Redirection logique identique à celle d’ajouter_concert
        concert_date = concert.date
        today = date.today()

        if concert_date < today:
            if concert.paye:
                saison = saison_from_date(concert_date).replace('/', '-')
                return redirect(url_for('archives_concerts_saison', saison=saison))
            else:
                return redirect(url_for('concerts_non_payes_view'))
        else:
            return redirect(url_for('liste_concerts'))

    participations = Participation.query.filter_by(concert_id=concert.id).all()
    participants_ids = set(p.musicien_id for p in participations)
    if jerome_id:
        participants_ids.add(jerome_id)

    return render_template(
        'participations.html',
        concert=concert,
        musiciens=musiciens,
        participants_ids=participants_ids
    )




@app.route('/concert/<int:concert_id>/participation/ajouter', methods=['GET', 'POST'])
def ajouter_participation(concert_id):
    concert = Concert.query.get_or_404(concert_id)
    musiciens = Musicien.query.order_by(Musicien.nom).all()
    
    if request.method == 'POST':
        musicien_id = int(request.form['musicien_id'])
        paye = 'paye' in request.form
        participation = Participation(concert_id=concert.id, musicien_id=musicien_id, paye=paye)
        db.session.add(participation)
        db.session.commit()

        # ✅ Recalcul des participations réelles si le concert est payé
        if concert.paye:
            from calcul_participations import mettre_a_jour_credit_calcule_reel_pour_concert
            mettre_a_jour_credit_calcule_reel_pour_concert(concert.id)

        return redirect(url_for('liste_participations', concert_id=concert.id))

    return render_template('ajouter_participation.html', concert=concert, musiciens=musiciens)


@app.route('/participation/modifier/<int:participation_id>', methods=['GET', 'POST'])
def modifier_participation(participation_id):
    participation = Participation.query.get_or_404(participation_id)
    concert = participation.concert
    musiciens = Musicien.query.order_by(Musicien.nom).all()

    if request.method == 'POST':
        participation.musicien_id = int(request.form['musicien_id'])
        participation.paye = 'paye' in request.form
        db.session.commit()

        concert_date = concert.date
        today = date.today()

        if concert_date < today:
            if concert.paye:
                saison = saison_from_date(concert_date).replace('/', '-')
                return redirect(url_for('archives_concerts_saison', saison=saison))
            else:
                return redirect(url_for('concerts_non_payes_view'))
        else:
            return redirect(url_for('liste_concerts'))

    return render_template('modifier_participation.html', participation=participation, musiciens=musiciens)

@app.route('/participation/supprimer/<int:participation_id>', methods=['POST'])
def supprimer_participation(participation_id):
    participation = Participation.query.get_or_404(participation_id)
    concert_id = participation.concert_id
    db.session.delete(participation)
    db.session.commit()
    return redirect(url_for('liste_participations', concert_id=concert_id))
    

# --------- CRUD OPERATIONS ---------
    
# Nouveau app.py (extrait avec route /operations refactorée)




from flask import request, render_template, redirect, url_for, flash
from datetime import date

@app.route('/operations', methods=['GET', 'POST'])
def operations():
    if request.method == 'POST':
        # -------- TRAITEMENT DU FORMULAIRE --------
        data = request.form.to_dict()
        # Conversion de la date en format ISO si besoin
        if "/" in data.get("date", ""):
            try:
                jour, mois, annee = data["date"].split("/")
                data["date"] = f"{annee}-{mois.zfill(2)}-{jour.zfill(2)}"
            except Exception as e:
                print("Erreur de conversion date :", data["date"], e)
                flash("Erreur de conversion de la date", "danger")
                return redirect(url_for('operations'))
        print("DATA POST:", data)
        enregistrer_operation_en_db(data)
        
        if data.get('concert_id'):
            from calcul_participations import mettre_a_jour_credit_calcule_potentiel_pour_concert
            mettre_a_jour_credit_calcule_potentiel_pour_concert(data['concert_id'])


        if data.get('motif') == 'Recette concert' and data.get('concert_id'):
            valider_concert_par_operation(data['concert_id'], data['montant'])

        flash("✅ Opération enregistrée", "success")
        return redirect(url_for('operations'))

    # -------- CHARGEMENT DE LA PAGE (GET) --------
    musiciens = Musicien.query.filter(
        (Musicien.actif.is_(True)) |
        (Musicien.nom.ilike('%ASSO7%')) |
        (Musicien.prenom.ilike('%ASSO7%'))
    ).order_by(Musicien.prenom, Musicien.nom).all()

    concerts = Concert.query.order_by(Concert.date).all()
    musiciens_dicts = [musicien_to_dict(m) for m in musiciens]
    musiciens_normaux, structures = separer_structures_et_musiciens(musiciens_dicts)

    concerts_js = preparer_concerts_js(concerts)
    concertsData = preparer_concerts_data()
    today = date.today()
    current_date = today.strftime("%d/%m/%Y")
    saison_en_cours = get_saison_actuelle()
    concerts_a_venir = Concert.query.filter(Concert.date >= date.today()).order_by(Concert.date).all()
    concerts_dicts_a_venir = [concert_to_dict(c) for c in concerts_a_venir]
    concerts_par_musicien = preparer_concerts_par_musicien()
    concerts_par_musicien["__Recette_concert__"] = concerts_dicts_a_venir

    return render_template(
        'operations.html',
        titre_formulaire="Nouvelle opération",
        operation=None,
        musiciens=musiciens_dicts,
        musiciens_normaux=musiciens_normaux,
        structures=structures,
        concerts_js=concerts_js,
        concertsData=concertsData,
        concerts_par_musicien=concerts_par_musicien,
        concertsParMusicien=concerts_par_musicien,
        current_date=current_date,
        saison_en_cours=saison_en_cours
    )



@app.route('/modifier_operation/<int:id>', methods=['GET', 'POST'])
def modifier_operation(id):
    operation = Operation.query.get_or_404(id)

    if request.method == 'POST':
        modifier_operation_en_db(id, request.form)
        concert_id = request.form.get('concert_id')

        flash("✅ Opération modifiée avec succès", "success")
        return redirect(url_for('archives_operations_saison', saison_url=saison_from_date(operation.date).replace("/", "-")))

    musiciens = Musicien.query.order_by(Musicien.prenom, Musicien.nom).all()
    concerts = Concert.query.order_by(Concert.date).all()

    # 🔧 Convertir en dictionnaires avant d'appeler la fonction de séparation
    musiciens_dicts = [musicien_to_dict(m) for m in musiciens]
    musiciens_normaux, structures = separer_structures_et_musiciens(musiciens_dicts)

    concerts_js = preparer_concerts_js(concerts)
    concertsData = preparer_concerts_data()
    today_str = date.today().isoformat()

    return render_template(
        'form_operations.html',
        titre_formulaire="Modifier une opération",
        operation=operation,
        musiciens=musiciens_dicts,  # ✔ pour template
        musiciens_normaux=musiciens_normaux,
        structures=structures,
        concerts_js=concerts_js,
        concertsData=concertsData,
        current_date=today_str,
        is_modification=True,
        concerts_par_musicien={},
    )




@app.route('/operations/supprimer', methods=['POST'])
def supprimer_operation():
    from mes_utils import supprimer_operation_en_db  # helper cascade
    data = request.get_json(silent=True) or {}
    operation_id = data.get('id')

    if not operation_id:
        return jsonify({'success': False, 'message': 'ID d’opération manquant'}), 400

    # Récupération de l’opération
    operation = db.session.get(Operation, int(operation_id))
    if not operation:
        return jsonify({'success': False, 'message': 'Opération introuvable'}), 404

    motif_norm = (operation.motif or '').strip().lower()
    # 🚫 Interdiction de supprimer une opération de Commission Lionel directement
    if motif_norm == "commission lionel":
        return jsonify({
            'success': False,
            'message': "Cette opération est générée automatiquement et ne peut être supprimée directement."
        }), 403

    # Sauvegarde du concert_id AVANT suppression
    concert_id = operation.concert_id

    try:
        # Cas 1 : suppression d'une opération principale "Salaire" -> cascade
        if motif_norm == "salaire":
            supprimer_operation_en_db(operation.id)
            success = True

        # Cas 2 : on tente de supprimer le débit auto salaire (CB/CAISSE)
        elif bool(getattr(operation, "auto_debit_salaire", False)):
            # On cherche l'opération racine (Salaire) via operation_liee_id
            racine = None
            if operation.operation_liee_id:
                racine = db.session.get(Operation, operation.operation_liee_id)
            # Si pas trouvé, on tente l'inverse (lien réciproque éventuel)
            if not racine:
                racine = Operation.query.filter_by(operation_liee_id=operation.id, motif="Salaire").first()

            if racine and (racine.motif or '').strip().lower() == "salaire":
                supprimer_operation_en_db(racine.id)
                success = True
            else:
                # À défaut, on supprime au moins l’opération demandée
                # (mais normalement on devrait trouver la racine)
                supprimer_operation_en_db(operation.id)
                success = True

        # Cas 3 : autre opération -> comportement existant
        else:
            success = annuler_operation(operation.id)

        # ✅ Recalcul des participations si concert concerné
        if concert_id:
            from calcul_participations import mettre_a_jour_credit_calcule_potentiel_pour_concert
            mettre_a_jour_credit_calcule_potentiel_pour_concert(concert_id)

        return jsonify({'success': bool(success)})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route("/operations_a_venir")
def operations_a_venir():
    today = date.today()
    operations = (
        db.session.query(Operation)
        .filter(
            Operation.date > today,
            or_(Operation.auto_cb_asso7.is_(None), Operation.auto_cb_asso7.is_(False))
        )
        .order_by(Operation.date)
        .all()
    )
    return render_template("operations_a_venir.html", operations=operations)

# --------- CRUD CACHETS ---------
    


@app.route("/cachets", methods=["GET", "POST"])
def declarer_cachet():
    musiciens = get_tous_musiciens_actifs()
    message = None
    erreur = None

    if request.method == "POST":
        try:
            data = request.form.to_dict()
            musicien_id = int(data.get("musicien"))
            montant = float(data.get("montant").replace(",", "."))
            dates_str = data.get("dates_hidden", "")
            dates = [datetime.strptime(d, "%Y-%m-%d").date() for d in dates_str.split(",") if d]

            # Vérification des doublons
            doublons = []
            dates_valides = []
            for d in dates:
                if Cachet.query.filter_by(musicien_id=musicien_id, date=d).first():
                    doublons.append(d)
                else:
                    dates_valides.append(d)

            if dates_valides:
                ajouter_cachets(musicien_id, dates_valides, montant, len(dates_valides))
                flash(f"✅ {len(dates_valides)} cachet(s) enregistré(s)", "success")

            if doublons:
                doublons_str = ", ".join([d.strftime("%d/%m/%Y") for d in doublons])
                flash(f"⚠️ Cachet(s) déjà existant(s) non enregistré(s) pour : {doublons_str}", "warning")
                
        except ValueError as ve:
            erreur = str(ve)
        except Exception as e:
            erreur = "Erreur lors de l’ajout des cachets."

    return render_template("cachets.html", musiciens=musiciens, message=message, erreur=erreur)



@app.route('/cachet/supprimer/<int:id>', methods=['POST'])
def supprimer_cachet(id):
    cachet = Cachet.query.get(id)
    if cachet:
        db.session.delete(cachet)
        db.session.commit()
    next_url = request.form.get('next')
    if next_url:
        return redirect(next_url)
    return redirect(url_for('cachets_a_venir'))


@app.route('/cachets_a_venir')
def cachets_a_venir():
    today = date.today()
    cachets = Cachet.query.filter(Cachet.date >= today).all()
    cachets_par_mois = regrouper_cachets_par_mois(cachets)
    return render_template(
        "cachets_a_venir.html",
        cachets_par_mois=cachets_par_mois,
        couleurs_mois=COULEURS_MOIS
    )


MOIS_FR2 = {
    1: "Janvier",
    2: "Février",
    3: "Mars",
    4: "Avril",
    5: "Mai",
    6: "Juin",
    7: "Juillet",
    8: "Août",
    9: "Septembre",
    10: "Octobre",
    11: "Novembre",
    12: "Décembre"
}

@app.route('/preview_mail_cachets', methods=['POST'])
def preview_mail_cachets():
    from datetime import date
    today = date.today()
    mois_1 = today.month
    mois_2 = (today.month % 12) + 1
    annee_m2 = today.year if mois_2 > mois_1 else today.year + 1

    cachets_m1 = get_cachets_par_mois(mois_1, today.year)
    cachets_m2 = get_cachets_par_mois(mois_2, annee_m2)

    def formater_cachets_html(cachets):
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

    import calendar
    mois_1_nom = MOIS_FR2[mois_1]
    mois_2_nom = MOIS_FR2[mois_2]
    titre = f"Déclaration des cachets MALO à venir : {mois_1_nom} et {mois_2_nom} {today.year}"

    message_html = f"""
    <p>Salut Lionel,</p>
    <p>Voici la liste des cachets à déclarer pour MALO prochainement :</p>
    <h2 style="font-size: 18px; font-weight: bold; margin-top: 20px;">{mois_1_nom}</h2>
    {formater_cachets_html(cachets_m1)}
    <h2 style="font-size: 18px; font-weight: bold; margin-top: 20px;">{mois_2_nom}</h2>
    {formater_cachets_html(cachets_m2)}
    <p>Merci.<br>@+<br><br>Jérôme</p>
    """

    # On passe sujet et message_html à un template de preview
    return render_template(
        "preview_mail_cachets.html",
        titre=titre,
        message_html=message_html
    )
    




@app.route('/envoyer_mail_cachets', methods=['POST'])
def envoyer_mail_cachets():
    titre = request.form.get("titre")
    message_html = request.form.get("message_html")
    print(f"Titre reçu : {titre}")
    print(f"HTML reçu (début) : {str(message_html)[:100]}...")
    if not titre or not message_html:
        print("Pas de titre ou de message_html reçu ! Fallback.")
        flash("Erreur : message non transmis depuis la preview.", "danger")
        return redirect(url_for('cachets_a_venir'))
    else:
        try:
            msg = Message(
                subject=titre,
                sender=current_app.config['MAIL_USERNAME'],
                recipients=["lionel@odradek78.fr"],
                cc=["jeromemalo1@gmail.com"],
                html=message_html
            )
            mail.send(msg)
            log_mail_envoye(titre, message_html)
            print("Après mail.send() — on va flasher success")
            flash("✅ Mail envoyé avec succès à Lionel", "success")
        except Exception as e:
            print(f"❌ Erreur lors de l'envoi du mail : {e}")
            flash("❌ Une erreur est survenue lors de l'envoi du mail.", "error")

    return redirect(url_for('cachets_a_venir'))


# --------- CRUD ARCHIVES ---------



@app.route('/archives')
def page_archives():
    saison = get_saison_actuelle()  # Renvoie '2024/2025' par exemple
    return render_template('archives.html', saison_en_cours=saison)





@app.route('/archives/concerts')
def archives_concerts():
    concerts = Concert.query.order_by(Concert.date.desc()).all()
    saisons = set()
    for concert in concerts:
        saisons.add(saison_from_date(concert.date))
    return render_template('archives_concerts.html', saisons=sorted(saisons, reverse=True))




@app.route('/archives/concerts/<saison>')
def archives_concerts_saison(saison):
    saison_affichee = saison.replace("-", "/")
    try:
        annee_debut, annee_fin = map(int, saison_affichee.split('/'))
    except Exception:
        return "Erreur de paramètre saison", 400

    debut_saison = date(annee_debut, 9, 1)
    fin_saison = date(annee_fin, 8, 31)

    concerts = Concert.query.filter(
        Concert.date >= debut_saison,
        Concert.date <= fin_saison,
        Concert.date <= date.today(),
        Concert.paye.is_(True)

    ).order_by(Concert.date).all()

    # Regroupement par mois
    concerts_par_mois = concerts_groupes_par_mois(concerts)

    # Préparation des crédits depuis la DB (sans recalcul)
    credits_musiciens = {}
    credits_asso7 = {}

    for concert in concerts:
        credits_musiciens[concert.id] = {}
        credits_asso7[concert.id] = 0.0

        for part in concert.participations:
            montant = part.credit_calcule or 0.0
            if part.musicien.nom == "ASSO7":
                credits_asso7[concert.id] = montant
            else:
                credits_musiciens[concert.id][part.musicien_id] = montant

    musiciens_dict = get_musiciens_dict()

    return render_template(
        "archives_concerts_saison.html",
        concerts=concerts,
        concerts_par_mois=concerts_par_mois,
        credits_musiciens=credits_musiciens,
        credits_asso7=credits_asso7,
        musiciens_dict=musiciens_dict,
        format_currency=format_currency,
        saison=saison_affichee,
        readonly_checkboxes=False  # ✅ permet de décocher
    )


    
@app.route("/archives_cachets")
def archives_cachets():
    toutes_les_dates = db.session.query(Cachet.date).distinct().all()
    saisons = set()

    for (dt,) in toutes_les_dates:
        if dt < date.today():  # uniquement passés
            annee = dt.year
            mois = dt.month
            if mois >= 9:
                debut = annee
                fin = annee + 1
            else:
                debut = annee - 1
                fin = annee
            saisons.add(f"{debut}/{str(fin)[-2:]}")

    saisons = sorted(saisons, reverse=True)
    return render_template("archives_cachets.html", saisons=saisons)

from sqlalchemy import and_
try:
    locale.setlocale(locale.LC_TIME, 'fr_FR.UTF-8')
except locale.Error:
    print("⚠️ Locale fr_FR.UTF-8 non disponible, fallback sur locale par défaut.")


@app.route('/archives_cachets/<saison>')
def archives_cachets_saison(saison):
    try:
        annee_debut = int(saison.split("-")[0])
        date_debut = datetime(annee_debut, 9, 1).date()
        date_fin = datetime(annee_debut + 1, 8, 31).date()
    except Exception:
        return "Format de saison invalide", 400

    cachets = Cachet.query.filter(Cachet.date >= date_debut, Cachet.date <= date_fin).all()

    # Organisation : mois → musicien → [cachets]
    data = defaultdict(lambda: defaultdict(list))
    for c in cachets:
        mois_str = MOIS_FR[c.date.month - 1]
        print(f"DEBUG Mois brut: {c.date.strftime('%B')} | Après mapping: {mois_str}")
        data[mois_str][c.musicien].append(c)



    # Tri des mois dans l’ordre (septembre à août)
    mois_ordre = ['septembre', 'octobre', 'novembre', 'décembre', 'janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet', 'août']
    cachets_par_mois = []
    for mois in mois_ordre:
        if mois in data:
            musiciens = sorted(data[mois].items(), key=lambda x: (x[0].nom.lower(), x[0].prenom.lower()))
            cachets_par_mois.append((mois.capitalize(), musiciens))
    # Couleurs par mois (adapté pour fond clair)
    couleurs_mois = {
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

    return render_template(
        "archives_cachets_saison.html",
        saison=saison.replace("-", "/"),
        cachets_par_mois=cachets_par_mois,
        couleurs_mois=couleurs_mois
    )




@app.route("/archives_operations")
def archives_operations():

    aujourd_hui = datetime.now().date()

    # On filtre les opérations passées
    operations_passees = Operation.query.filter(Operation.date < aujourd_hui).all()

    # On extrait les saisons à partir des dates
    saisons = set()
    for op in operations_passees:
        annee = op.date.year
        mois = op.date.month
        if mois >= 9:
            debut_saison = annee
            fin_saison = annee + 1
        else:
            debut_saison = annee - 1
            fin_saison = annee
        saison_str = f"{str(debut_saison)[-2:]}/{str(fin_saison)[-2:]}"
        saisons.add(saison_str)

    saisons = sorted(saisons, reverse=True)

    return render_template("archives_operations.html", saisons=saisons)
    
    

@app.route("/archives_operations_saison/<saison_url>")
def archives_operations_saison(saison_url):
    saison = saison_url.replace("-", "/")
    debut_saison, fin_saison = get_debut_fin_saison(saison)
    print(f"🔍 Début saison : {debut_saison}, Fin saison : {fin_saison}")

    # ➡️ Requête : on enlève TOUT filtre sur les flags "techniques"
    operations = Operation.query.join(Musicien).filter(
        Operation.date >= debut_saison,
        Operation.date <= fin_saison,
        Operation.date <= date.today()
    ).order_by(Operation.date.desc()).all()

    # Diagnostic
    for op in operations:
        try:
            print(f"✅ {op.date} - {op.type} - {op.musicien.nom} - {op.montant}")
        except Exception as e:
            print(f"⚠️ Problème avec une opération : {op.id} - {e}")
            print("------ DEBUG ARCHIVES ------")
            for op in operations:
                print(op.id, op.date, op.motif, op.type, op.montant, op.auto_cb_asso7, op.auto_debit_salaire)
            print("----------------------------")
    return render_template("archives_operations_saison.html", saison=saison, operations=operations)

from mes_utils import get_etat_comptes

@app.route('/comptes')
def comptes():
    tableau_comptes = get_etat_comptes()
    return render_template(
        'comptes.html',
        tableau_comptes=tableau_comptes,
        format_currency=format_currency
    )


# --------- REPORTS ---------


@app.route('/reports', methods=['GET', 'POST'])
def reports():
    musiciens = Musicien.query.order_by(Musicien.prenom, Musicien.nom).all()
    reports_dict = get_reports_dict(musiciens)

    if request.method == 'POST':
        musicien_id = int(request.form['musicien'])  # ← on récupère directement l'id
        montant = float(request.form['montant'])

        cible = Musicien.query.get(musicien_id)
        if cible:
            r = Report.query.filter_by(musicien_id=cible.id).first()
            if r:
                r.montant = montant
            else:
                r = Report(musicien_id=cible.id, montant=montant)
                db.session.add(r)
            db.session.commit()

        return redirect(url_for('comptes'))

    return render_template('reports.html',
                           musiciens=musiciens,
                           reports=reports_dict)


# --------- LIONEL ---------


@app.route('/lionel')
def lionel():
    # Mets ce que tu veux ici. Par exemple, une page temporaire :
    return render_template('lionel.html')
    # ou juste du texte :
    # return "<h1>Page Lionel à venir…</h1>"



# --- AUTRES ROUTES A CRÉER : Participations, Operations, Cachets, Reports... ---


from models import Musicien, db  # adapte l'import selon ton arborescence

UPLOAD_FOLDER = "static/pdf_temp"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route('/upload_pdf', methods=['POST'])
def upload_pdf():
    print("[DEBUG] Appel route /upload_pdf")
    if 'file' not in request.files:
        print("[DEBUG] Aucun fichier reçu.")
        return Response(
            json.dumps({"success": False, "message": "Aucun fichier reçu."}, ensure_ascii=False),
            content_type='application/json; charset=utf-8'
        )

    file = request.files['file']
    print("[DEBUG] Nom du fichier reçu :", file.filename)
    if file.filename == '':
        print("[DEBUG] Fichier vide")
        return Response(
            json.dumps({"success": False, "message": "Fichier vide."}, ensure_ascii=False),
            content_type='application/json; charset=utf-8'
        )

    if not file.filename.lower().endswith('.pdf'):
        print("[DEBUG] Mauvais format :", file.filename)
        return Response(
            json.dumps({"success": False, "message": "Format non supporté."}, ensure_ascii=False),
            content_type='application/json; charset=utf-8'
        )

    filename = secure_filename(file.filename)
    file_path = os.path.join(UPLOAD_FOLDER, filename)
    print("[DEBUG] Chemin de sauvegarde du fichier :", file_path)
    file.save(file_path)
    print("[DEBUG] Fichier sauvé. Lancement de l'extraction...")

    try:
        infos = extraire_infos_depuis_pdf(file_path)
        print("[DEBUG] Extraction réussie, infos :", infos)
        print("[DEBUG] Encodage des infos JSON :", json.dumps({"success": True, **infos}, ensure_ascii=False))
        return Response(
            json.dumps({"success": True, **infos}, ensure_ascii=False),
            content_type='application/json; charset=utf-8'
        )
    except Exception as e:
        print("[DEBUG][ERREUR extraction]:", str(e))
        return Response(
            json.dumps({"success": False, "message": "Erreur d’analyse du PDF.", "error": str(e)}, ensure_ascii=False),
            content_type='application/json; charset=utf-8'
        )

@app.route('/test_flash')
def test_flash():
    flash("Ceci est un test FLASH !", "success")
    return redirect(url_for('cachets_a_venir'))
    
@app.route("/test")
def test_page():
    return render_template("test.html")


from flask import send_file
from exports import generer_export_excel

@app.route('/export_general')
def export_general():
    chemin = generer_export_excel()
    return send_file(chemin, as_attachment=True)

# Enregistrement du filtre global Jinja (au cas où import plus haut serait ignoré)
from mes_utils import format_currency as fc
app.jinja_env.filters['format_currency'] = fc


# ------------ LANCEMENT ------------
if __name__ == "__main__":
    app.run(debug=True)







