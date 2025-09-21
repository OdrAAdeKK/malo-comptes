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
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True,      # ping avant chaque checkout pour éviter une connexion morte
    "pool_recycle": 300,        # recycle les connexions > 5 min (évite timeouts/load balancer)
    "pool_timeout": 30,
    "pool_size": 5,
    "max_overflow": 5,
    "connect_args": {
        "sslmode": "require",
        # keepalives côté libpq (psycopg3) : aide à garder la connexion vivante
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 5,
    },
}




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
    get_ordered_comptes_bis, get_reports_dict, extraire_infos_depuis_pdf, regrouper_cachets_par_mois,
    ensure_op_frais_previsionnels, detach_prevision_if_needed,
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



uri = os.environ.get("DATABASE_URL", "")
if uri.startswith("postgres://"):
    # SQLAlchemy 2.x + psycopg3 préfèrent 'postgresql+psycopg://'
    uri = uri.replace("postgres://", "postgresql+psycopg://", 1)

# Ajoute sslmode=require si absent (Render Postgres le supporte)
if uri and "sslmode=" not in uri:
    uri += ("&" if "?" in uri else "?") + "sslmode=require"

app.config["SQLALCHEMY_DATABASE_URI"] = uri or "sqlite:///local.db"

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




# Créer/ajouter
@app.route('/ajouter_musicien', methods=['GET', 'POST'])
def ajouter_musicien():
    erreur = None
    if request.method == 'POST':
        prenom   = (request.form.get('prenom') or '').strip()
        nom      = (request.form.get('nom') or '').strip()
        type_val = (request.form.get('type') or 'personne').strip().lower()
        actif    = bool(request.form.get('actif'))

        # règles de validation
        if not nom:
            erreur = "Le nom est obligatoire."
        elif type_val not in ('personne', 'structure'):
            erreur = "Type invalide."
        elif type_val == 'personne' and not prenom:
            erreur = "Le prénom est obligatoire pour un musicien de type 'personne'."

        if not erreur:
            # éviter les doublons (on tient compte du type)
            exist = Musicien.query.filter_by(nom=nom, prenom=(prenom if type_val != 'structure' else ''), type=type_val).first()
            if exist:
                erreur = "Cet(te) musicien(ne)/structure existe déjà."
            else:
                m = Musicien(
                    nom=nom,
                    prenom=(prenom if type_val != 'structure' else ''),  # prénom vide si structure
                    type=type_val,
                    actif=actif
                )
                db.session.add(m)
                db.session.commit()
                return redirect(url_for('liste_musiciens'))

    return render_template('ajouter_musicien.html', erreur=erreur)


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


from sqlalchemy import func  # en haut si pas déjà importé
from mes_utils import grouper_par_mois, get_credits_concerts_from_db
from collections import defaultdict                 # ← NEW
from models import Operation                         # ← NEW

@app.route('/concerts')
def liste_concerts():
    # 🔁 Laisse la base comparer à CURRENT_DATE (évite décalages/locale)
    concerts = (
        Concert.query
        .filter(Concert.date >= func.current_date())
        .order_by(Concert.date.asc())
        .all()
    )

    musiciens = Musicien.query.all()
    musiciens_dict = {m.id: m for m in musiciens}

    credits_musiciens, credits_asso7, credits_jerome = get_credits_concerts_from_db(concerts)

    # Regroupement par mois pour le template
    groupes = grouper_par_mois(concerts, "date", descending=False)

    # --- NEW: frais par musicien et par concert (hors prévisionnels globaux CB/CAISSE) ---
    concert_ids = [c.id for c in concerts]
    frais_par_musicien = defaultdict(dict)
    if concert_ids:
        rows = (
            db.session.query(
                Operation.concert_id,
                Operation.musicien_id,
                func.sum(Operation.montant).label("total"),
            )
            .filter(
                Operation.concert_id.in_(concert_ids),
                func.lower(Operation.motif) == "frais",
                Operation.previsionnel.is_(False),          # on ignore les frais prévisionnels globaux
                Operation.musicien_id.isnot(None)           # seulement des frais rattachés à un musicien
            )
            .group_by(Operation.concert_id, Operation.musicien_id)
            .all()
        )
        for cid, mid, total in rows:
            frais_par_musicien[cid][mid] = float(total or 0.0)

    # (optionnel) petit log de diag :
    try:
        app.logger.info(f"[concerts] {len(concerts)} à venir – ids/dates: " +
                        ", ".join(f"{c.id}:{c.date}" for c in concerts))
    except Exception:
        pass

    return render_template(
        'concerts.html',
        concerts=concerts,          # encore envoyé si ton template l’utilise
        groupes=groupes,            # ← à utiliser pour l’affichage par mois
        credits_musiciens=credits_musiciens,
        credits_asso7=credits_asso7,
        musiciens_dict=musiciens_dict,
        frais_par_musicien=frais_par_musicien   # ← NEW
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

        # (NEW) Frais prévisionnels saisis (peut être vide)
        frais_prev_str = (request.form.get('frais_previsionnels') or '').strip()

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
        db.session.refresh(concert)  # garantir concert.id

        # (NEW) Si NON payé → créer/mettre à jour l'opération "Frais (prévisionnels)" liée
        if not paye:
            # import local pour être 100% sûr même si l'import global a été oublié
            from mes_utils import ensure_op_frais_previsionnels
            ensure_op_frais_previsionnels(concert.id, frais_prev_str)

        # Si payé, créer une opération de crédit (recette réelle)
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

        # Recalcul des crédits potentiels / à venir (si tu l'utilises)
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

        # Tolérant aux virgules
        recette_input = (request.form.get('recette') or '').strip()
        recette_input = recette_input.replace(',', '.') if recette_input else ''

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

        # --- NEW: Frais prévisionnels ---
        from mes_utils import ensure_op_frais_previsionnels
        frais_prev_str = (request.form.get('frais_previsionnels') or '').strip()
        if not concert.paye:
            # Si le concert n'est PAS payé -> on crée/MAJ/supprime l'opé prévisionnelle selon la saisie
            ensure_op_frais_previsionnels(concert.id, frais_prev_str)
        else:
            # Si le concert est payé -> aucune prévision ne doit subsister
            ensure_op_frais_previsionnels(concert.id, None)

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

    # ---- GET : pré-remplir la valeur du champ "Recette"
    def _fmt_fr(x):
        if x is None:
            return ""
        try:
            return f"{float(x):.2f}".replace(".", ",")  # ex: 550,00
        except Exception:
            return str(x)

    # priorité à la recette_attendue si présente, sinon la recette réelle
    recette_init_val = concert.recette_attendue if concert.recette_attendue is not None else concert.recette

    retour_url = url_for('liste_concerts')
    return render_template(
        'modifier_concert.html',
        concert=concert,
        retour_url=retour_url,
        recette_initiale=_fmt_fr(recette_init_val),   # 👈 envoyé au template
    )





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


from sqlalchemy import func
from mes_utils import grouper_par_mois, get_credits_concerts_from_db

@app.route('/concerts_non_payes')
def concerts_non_payes_view():
    from collections import defaultdict  # local pour éviter les effets de bord

    # passés et non payés
    concerts = (
        Concert.query
        .filter(
            Concert.paye.is_(False),
            Concert.date <= func.current_date()
        )
        .order_by(Concert.date.asc())
        .all()
    )

    musiciens = Musicien.query.all()
    musiciens_dict = {m.id: m for m in musiciens}

    credits_musiciens, credits_asso7, credits_jerome = get_credits_concerts_from_db(concerts)

    groupes = grouper_par_mois(concerts, "date", descending=False)

    # --- frais par musicien et par concert (on ignore les prévisionnels globaux) ---
    concert_ids = [c.id for c in concerts]
    frais_par_musicien = defaultdict(dict)
    if concert_ids:
        rows = (
            db.session.query(
                Operation.concert_id,
                Operation.musicien_id,
                func.sum(Operation.montant).label("total"),
            )
            .filter(
                Operation.concert_id.in_(concert_ids),
                func.lower(Operation.motif) == "frais",
                Operation.previsionnel.is_(False),     # exclut les frais « prévisionnels »
                Operation.musicien_id.isnot(None)      # uniquement des frais rattachés à un musicien
            )
            .group_by(Operation.concert_id, Operation.musicien_id)
            .all()
        )
        for cid, mid, total in rows:
            frais_par_musicien[cid][mid] = float(total or 0.0)

    return render_template(
        "concerts_non_payes.html",
        groupes=groupes,
        credits_musiciens=credits_musiciens,
        credits_asso7=credits_asso7,
        musiciens_dict=musiciens_dict,
        frais_par_musicien=frais_par_musicien  # ← NEW
    )



from calcul_participations import mettre_a_jour_credit_calcule_potentiel_pour_concert

from sqlalchemy import func  # si pas déjà importé

@app.route('/concerts/<int:concert_id>/toggle_paye', methods=['POST'])
def toggle_concert_paye(concert_id):
    from mes_utils import creer_recette_concert_si_absente, supprimer_recette_concert_pour_concert
    from models import Operation

    concert = Concert.query.get(concert_id)
    if not concert:
        return "Concert non trouvé", 404

    # etat_cible = True  -> on passe en PAYÉ
    # etat_cible = False -> on repasse en NON PAYÉ
    etat_cible = not concert.paye

    if etat_cible:
        # ===== NON PAYÉ -> PAYÉ =====
        try:
            # 1) recette finale = recette existante, sinon recette_attendue, sinon 0
            if concert.recette is None:
                if concert.recette_attendue is not None:
                    concert.recette = float(concert.recette_attendue or 0.0)
                else:
                    concert.recette = float(concert.recette or 0.0)

            # 2) marquer payé & nettoyer l'attendu
            concert.paye = True
            concert.recette_attendue = None

            # 3) créer l’opération "Recette concert" si absente
            mode_final = (getattr(concert, "mode_paiement_prevu", "") or "CB ASSO7").strip()
            creer_recette_concert_si_absente(
                concert_id=concert.id,
                montant=float(concert.recette or 0.0),
                date_op=None,
                mode=mode_final
            )

            # 4) 🔥 purge des opérations PRÉVISIONNELLES + reset du champ prévisionnel
            removed = 0

            # 4.a) si on a mémorisé une op spécifique
            if getattr(concert, "op_prevision_frais_id", None):
                op_prev = Operation.query.get(concert.op_prevision_frais_id)
                if op_prev:
                    db.session.delete(op_prev)
                    removed += 1
                concert.op_prevision_frais_id = None

            # 4.b) ceinture et bretelles : supprimer toute op prévisionnelle pour ce concert
            ops_prev = Operation.query.filter_by(concert_id=concert.id, previsionnel=True).all()
            for op in ops_prev:
                db.session.delete(op)
                removed += 1

            # 4.c) remettre le champ à None (ou 0.0 si tu préfères)
            concert.frais_previsionnels = None

            db.session.add(concert)
            db.session.commit()
            db.session.refresh(concert)

            if removed:
                print(f"[i] toggle_paye: {removed} opération(s) prévisionnelle(s) supprimée(s) (concert_id={concert.id})")

            # 5) Recalcul (réel) + (optionnel) potentiel global
            from calcul_participations import mettre_a_jour_credit_calcule_reel_pour_concert
            mettre_a_jour_credit_calcule_reel_pour_concert(concert.id)
            try:
                from calcul_participations import mettre_a_jour_credit_calcule_potentiel
                mettre_a_jour_credit_calcule_potentiel()
            except Exception:
                pass

            return redirect(url_for('archives_concerts'))

        except Exception as e:
            db.session.rollback()
            print(f"❌ Erreur lors du passage NON PAYÉ -> PAYÉ pour concert {concert.id}: {e}")
            return "Erreur serveur", 500

    else:
        # ===== PAYÉ -> NON PAYÉ =====
        try:
            # 1) Restaurer recette_attendue si absente, depuis la recette réelle
            if (concert.recette_attendue is None) and (concert.recette is not None):
                try:
                    concert.recette_attendue = float(concert.recette) or 0.0
                except Exception:
                    concert.recette_attendue = 0.0

            # 2) Supprimer l'opération 'Recette concert' liée (idempotent)
            nb_suppr = supprimer_recette_concert_pour_concert(concert.id)
            print(f"[INFO] toggle_paye: {nb_suppr} 'Recette concert' supprimée(s) pour concert_id={concert.id}")

            # 3) Réinitialiser l'état "non payé"
            concert.recette = None
            concert.paye = False

            db.session.commit()
            db.session.refresh(concert)

            # 4) Recalcul : crédit POTENTIEL pour CE concert (avec frais prévisionnels pris en compte par l'étape 10)
            from calcul_participations import mettre_a_jour_credit_calcule_potentiel_pour_concert
            print(f"[✓] Recalcul crédit POTENTIEL pour concert non payé id={concert.id}")
            mettre_a_jour_credit_calcule_potentiel_pour_concert(concert.id)

            return redirect(url_for('liste_concerts'))

        except Exception as e:
            db.session.rollback()
            print(f"❌ Erreur lors du passage PAYÉ -> NON PAYÉ pour concert {concert.id}: {e}")
            return "Erreur serveur", 500



from calcul_participations import mettre_a_jour_credit_calcule_potentiel_pour_concert

@app.route("/valider_paiement_concert", methods=["POST"])
def valider_paiement_concert():
    from mes_utils import creer_recette_concert_si_absente
    from calcul_participations import mettre_a_jour_credit_calcule_reel_pour_concert
    from models import Operation  # 👈 pour supprimer les prévisionnels

    data = request.get_json(silent=True) or {}
    concert_id = data.get("concert_id")
    compte = (data.get("compte") or "").strip()
    recette_raw = data.get("recette")

    concert = Concert.query.get(concert_id)
    if not concert:
        return jsonify(success=False, message="Concert introuvable"), 404

    try:
        def _to_float(x):
            if x is None:
                return None
            s = str(x).strip().replace(",", ".")
            return float(s) if s else None

        # 1) recette finale
        recette_post = _to_float(recette_raw)
        if recette_post is not None:
            concert.recette = recette_post
        elif concert.recette_attendue is not None:
            concert.recette = float(concert.recette_attendue)
        else:
            concert.recette = float(concert.recette or 0.0)

        # 2) marquer payé
        concert.paye = True
        concert.recette_attendue = None

        # 3) mode de paiement
        mode_final = (compte or getattr(concert, "mode_paiement_prevu", "") or "Compte").strip()

        # 4) créer l’opération recette si absente
        creer_recette_concert_si_absente(
            concert_id=concert.id,
            montant=concert.recette,
            date_op=None,
            mode=mode_final
        )

        # 5) 🔥 PURGE des opérations PRÉVISIONNELLES liées + reset des frais prévisionnels
        ops_prev = Operation.query.filter_by(concert_id=concert.id, previsionnel=True).all()
        removed = 0
        for op in ops_prev:
            db.session.delete(op)
            removed += 1
        concert.frais_previsionnels = 0.0

        db.session.commit()
        if removed:
            print(f"[i] {removed} opération(s) prévisionnelle(s) supprimée(s) pour concert {concert.id}")

        # 6) recalculs (crédit RÉEL)
        try:
            db.session.expire_all()
            mettre_a_jour_credit_calcule_reel_pour_concert(concert.id)
            db.session.commit()
        except Exception as e:
            print(f"⚠️ Recalcul crédit réel échoué pour concert {concert.id} : {e}")

        # 7) Redirection vers l’archive de la saison
        d = (concert.date or datetime.utcnow().date())
        start_year = d.year if d.month >= 9 else d.year - 1
        season_label = f"{start_year}-{start_year+1}"
        try:
            redirect_url = url_for("archives_concerts_saison", saison=season_label)
        except Exception:
            try:
                redirect_url = url_for("archives_concerts") + f"#saison-{season_label}"
            except Exception:
                redirect_url = url_for("archives_concerts")

        return jsonify(success=True, redirect_url=redirect_url, season_label=season_label)

    except Exception as e:
        db.session.rollback()
        return jsonify(success=False, message=str(e)), 400



from calcul_participations import mettre_a_jour_credit_calcule_potentiel_pour_concert

@app.route("/annuler_paiement_concert", methods=["POST"])
def annuler_paiement_concert():
    from mes_utils import supprimer_recette_concert_pour_concert
    from calcul_participations import mettre_a_jour_credit_calcule_potentiel_pour_concert

    data = request.get_json(silent=True) or {}
    concert_id = data.get("concert_id")
    concert = Concert.query.get(concert_id)
    if not concert:
        return jsonify(success=False, message="Concert introuvable."), 404

    try:
        # 1) Restaurer une prévision si besoin
        if concert.recette is not None and (concert.recette_attendue is None):
            concert.recette_attendue = float(concert.recette) or 0.0

        # 2) Supprimer toutes les opérations "Recette concert" du concert
        nb_suppr = supprimer_recette_concert_pour_concert(concert.id)

        # 3) Repasse en non-payé
        concert.recette = None
        concert.paye = False
        db.session.add(concert)
        db.session.commit()

        # 4) Recalcul des crédits potentiels
        mettre_a_jour_credit_calcule_potentiel_pour_concert(concert.id)
        db.session.commit()

        return jsonify(success=True, deleted=nb_suppr)
    except Exception as e:
        db.session.rollback()
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

        # ✅ Recalcul des participations potentielles après validation
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


# ─────────────────────────────────────────────────────────────────────────────
#  AJOUT : routes pour l'ajustement (gains "fixés" par musicien)
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/participants_concert/<int:concert_id>")
def participants_concert(concert_id):
    """Renvoie (JSON) la liste des participants du concert avec montants potentiel/réel et gain_fixe."""
    concert = Concert.query.get_or_404(concert_id)

    parts = []
    participations = (
        db.session.query(Participation, Musicien)
        .join(Musicien, Musicien.id == Participation.musicien_id)
        .filter(Participation.concert_id == concert_id)
        .all()
    )
    for p, m in participations:
        parts.append({
            "participation_id": p.id,
            "musicien_id": m.id,
            "nom": f"{m.prenom} {m.nom}",
            "potentiel": float(p.credit_calcule_potentiel or 0),
            "reel": float(p.credit_calcule or 0),
            "fixe": (None if p.gain_fixe is None else float(p.gain_fixe)),
        })

    return jsonify(success=True, concert_id=concert_id, items=parts, paye=bool(concert.paye))


@app.route("/ajuster_gains", methods=["POST"])
def ajuster_gains():
    """
    JSON attendu :
    {
      "concert_id": 123,  # <-- nombre !
      "overrides": { "<participation_id>": <montant_ou_null>, ... }
    }
    """
    from calcul_participations import (
        mettre_a_jour_credit_calcule_potentiel_pour_concert,
        mettre_a_jour_credit_calcule_reel_pour_concert,
    )

    data = request.get_json(silent=True) or {}
    concert_id_raw = data.get("concert_id")

    # ✅ cast robuste en int (corrige l'erreur integer = varchar)
    try:
        concert_id = int(concert_id_raw)
    except (TypeError, ValueError):
        return jsonify(success=False, message="concert_id invalide"), 400

    overrides = data.get("overrides") or {}

    concert = Concert.query.get_or_404(concert_id)

    # 1) enregistrer les overrides (tolère "1 200,50")
    try:
        for pid_str, val in overrides.items():
            p = Participation.query.get(int(pid_str))
            if not p or p.concert_id != concert_id:  # ici concert_id est bien un int
                continue
            raw = "" if val is None else str(val).strip()
            raw = (raw.replace("\xa0", "").replace(" ", "").replace(",", "."))
            if raw == "":
                p.gain_fixe = None
            else:
                num = round(float(raw), 2)
                if num < 0:
                    return jsonify(success=False, message="Un gain fixé ne peut pas être négatif."), 400
                p.gain_fixe = num
            db.session.add(p)
        db.session.commit()

        # 🔎 DEBUG : ce qui est effectivement en DB après sauvegarde
        saved = {
            p.id: (p.musicien_id, (float(p.gain_fixe) if p.gain_fixe is not None else None))
            for p in Participation.query.filter_by(concert_id=concert_id).all()  # ✅ int ici
        }
        print(f"[DEBUG] gain_fixe en DB pour concert {concert_id} :", saved)

    except Exception as e:
        db.session.rollback()
        return jsonify(success=False, message=f"Erreur d'enregistrement des ajustements : {e}"), 400

    # 2) recalculs après ajustements
    try:
        if concert.paye:
            mettre_a_jour_credit_calcule_reel_pour_concert(concert_id)
        else:
            mettre_a_jour_credit_calcule_potentiel_pour_concert(concert_id)
        db.session.commit()
        return jsonify(success=True)
    except Exception as e:
        db.session.rollback()
        return jsonify(success=False, message=f"Erreur de recalcul : {e}"), 400



# --------- CRUD OPERATIONS ---------
    

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
                print("Erreur de conversion date :", data.get("date"), e)
                flash("Erreur de conversion de la date", "danger")
                return redirect(url_for('operations'))

        # --- Règle spéciale : "Remboursement frais divers" pour un MUSICIEN ---
        motif_norm = (data.get("motif") or "").strip().lower()

        # id du "Qui" (nom du champ selon ton formulaire)
        qui_raw = data.get("musicien_id") or data.get("musicien") or data.get("qui") or ""
        try:
            mid = int(str(qui_raw).strip()) if qui_raw else None
        except Exception:
            mid = None

        m = Musicien.query.get(mid) if mid else None
        is_musicien = bool(m and (m.type != "structure"))

        if is_musicien and motif_norm == "remboursement frais divers":
            # type / nature / montant
            data["type"] = "debit"
            data.setdefault("nature", "frais")
            if "montant" in data and data["montant"] is not None:
                try:
                    data["montant"] = str(abs(float(str(data["montant"]).replace(",", "."))))
                except Exception:
                    pass

            # concert obligatoire
            cid_raw = data.get("concert_id")
            try:
                cid = int(str(cid_raw).strip()) if cid_raw else None
            except Exception:
                cid = None

            if not cid:
                flash("Choisis un concert pour un remboursement de frais divers.", "warning")
                return redirect(url_for('operations'))

            concert = Concert.query.get(cid)
            if not concert:
                flash("Concert introuvable pour l'opération.", "danger")
                return redirect(url_for('operations'))

            # Date : si vide -> date du concert
            if not (data.get("date") and str(data["date"]).strip()):
                data["date"] = concert.date.isoformat()

            # Pas de brut pour ce motif
            data.pop("brut", None)

        print("DATA POST (après normalisation):", data)
        enregistrer_operation_en_db(data)

        # Recalcul potentiel si lié à un concert
        if data.get('concert_id'):
            try:
                cid = int(str(data['concert_id']).strip())
                from calcul_participations import mettre_a_jour_credit_calcule_potentiel_pour_concert
                mettre_a_jour_credit_calcule_potentiel_pour_concert(cid)
            except Exception as e:
                print("⚠️ Recalcul potentiel ignoré (concert_id invalide) :", e)

        # Validation éventuelle des recettes
        if (data.get('motif') == 'Recette concert') and data.get('concert_id'):
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
    # ✅ Importer ici (une seule fois) pour éviter les UnboundLocalError
    from models import Concert, Musicien, Operation
    from calcul_participations import mettre_a_jour_credit_calcule_potentiel_pour_concert

    operation = Operation.query.get_or_404(id)

    if request.method == 'POST':
        data = request.form.to_dict()

        # 1) Date "JJ/MM/AAAA" → "YYYY-MM-DD"
        if "/" in data.get("date", ""):
            try:
                j, m, a = data["date"].split("/")
                data["date"] = f"{a}-{m.zfill(2)}-{j.zfill(2)}"
            except Exception as e:
                app.logger.warning(f"[modifier_operation] Conversion date échouée: {data.get('date')} ({e})")
                flash("Erreur de conversion de la date", "danger")
                return redirect(url_for('modifier_operation', id=id))

        # 2) Règles métier
        motif_norm = (data.get("motif") or "").strip().lower()

        # Radios → hidden "type"
        tv = (data.get("type_visible") or "").strip().lower()
        if tv in ("credit", "debit"):
            data["type"] = tv

        # “musicien” est un libellé ("Prénom Nom" ou une structure)
        qui_raw = (data.get("musicien") or "").strip()
        is_structure = qui_raw in ("ASSO7", "CB ASSO7", "CAISSE ASSO7", "TRESO ASSO7")

        # — Remboursement frais divers (toujours DEBIT, concert requis, brut ignoré) —
        if (not is_structure) and motif_norm == "remboursement frais divers":
            data["type"] = "debit"
            data.setdefault("nature", "frais")

            if "montant" in data and data["montant"] is not None:
                try:
                    data["montant"] = str(abs(float(str(data["montant"]).replace(",", "."))))
                except Exception:
                    pass

            cid_raw = data.get("concert_id")
            try:
                cid = int(str(cid_raw).strip()) if cid_raw else None
            except Exception:
                cid = None

            if not cid:
                flash("Choisis un concert pour un remboursement de frais divers.", "warning")
                return redirect(url_for('modifier_operation', id=id))

            # Si date vide → date du concert
            if not (data.get("date") and str(data["date"]).strip()):
                c = Concert.query.get(cid)
                if c:
                    data["date"] = c.date.isoformat()

            data.pop("brut", None)  # non pertinent ici

        # 3) Mise à jour en base
        modifier_operation_en_db(id, data)

        # 4) Recalcul du potentiel pour le concert lié (nouveau ou inchangé)
        try:
            cid_for_recalc = data.get("concert_id") or (operation.concert_id if operation else None)
            if cid_for_recalc:
                mettre_a_jour_credit_calcule_potentiel_pour_concert(int(str(cid_for_recalc)))
        except Exception as e:
            app.logger.warning(f"[modifier_operation] Recalcul potentiel ignoré: {e}")

        flash("✅ Opération modifiée avec succès", "success")
        return redirect(url_for(
            'archives_operations_saison',
            saison_url=saison_from_date(operation.date).replace("/", "-")
        ))

    # ------------ GET : chargement du formulaire ------------
    musiciens = Musicien.query.order_by(Musicien.prenom, Musicien.nom).all()
    concerts = Concert.query.order_by(Concert.date).all()

    musiciens_dicts = [musicien_to_dict(m) for m in musiciens]
    musiciens_normaux, structures = separer_structures_et_musiciens(musiciens_dicts)

    concerts_js = preparer_concerts_js(concerts)
    concerts_par_musicien = preparer_concerts_par_musicien()

    today_str = date.today().isoformat()

    return render_template(
        'form_operations.html',
        titre_formulaire="Modifier une opération",
        operation=operation,
        musiciens=musiciens_dicts,
        musiciens_normaux=musiciens_normaux,
        structures=structures,
        concerts_js=concerts_js,
        current_date=today_str,
        is_modification=True,
        concerts_par_musicien=concerts_par_musicien,
        concertsParMusicien=concerts_par_musicien,
    )



@app.route('/operations/supprimer', methods=['POST'])
def supprimer_operation():
    from mes_utils import supprimer_operation_en_db, detach_prevision_if_needed  # helper cascade + détachage prévision
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
            # Détacher la prévision si jamais c'en était une (sécurisant et idempotent)
            detach_prevision_if_needed(operation)
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
                # Détacher (au cas où) puis suppression en cascade depuis la racine
                detach_prevision_if_needed(racine)
                supprimer_operation_en_db(racine.id)
                success = True
            else:
                # À défaut, on supprime au moins l’opération demandée
                detach_prevision_if_needed(operation)
                supprimer_operation_en_db(operation.id)
                success = True

        # Cas 3 : autre opération -> comportement existant
        else:
            # Avant la suppression, si c'est une op prévisionnelle liée à un concert, on nettoie le concert
            detach_prevision_if_needed(operation)
            success = annuler_operation(operation.id)

        # ✅ Recalcul des participations si concert concerné
        # ✅ Recalcule le champ concerts.frais_previsionnels (puis les potentiels)
        if concert_id:
            from mes_utils import recompute_frais_previsionnels
            recompute_frais_previsionnels(concert_id)  # met à jour le champ en DB

            from calcul_participations import mettre_a_jour_credit_calcule_potentiel_pour_concert
            mettre_a_jour_credit_calcule_potentiel_pour_concert(concert_id)


        return jsonify({'success': bool(success)})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


from mes_utils import grouper_par_mois
from sqlalchemy import or_
from datetime import date

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

    # 🔹 Regroupement par mois avec labels FR
    groupes = grouper_par_mois(operations, "date")

    return render_template("operations_a_venir.html", groupes=groupes)


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


# en haut du fichier, avec tes autres imports utilitaires
from mes_utils import collecter_frais_par_musicien


@app.route('/archives/concerts/<saison>')
def archives_concerts_saison(saison):
    saison_affichee = saison.replace("-", "/")
    try:
        annee_debut, annee_fin = map(int, saison_affichee.split('/'))
    except Exception:
        return "Erreur de paramètre saison", 400

    debut_saison = date(annee_debut, 9, 1)
    fin_saison = date(annee_fin, 8, 31)

    concerts = (
        Concert.query.filter(
            Concert.date >= debut_saison,
            Concert.date <= fin_saison,
            Concert.date <= date.today(),
            Concert.paye.is_(True)
        )
        .order_by(Concert.date)
        .all()
    )

    # NEW: agrège les frais (débits 'Frais*' non prévisionnels) par musicien et par concert
    from mes_utils import collecter_frais_par_musicien
    frais_par_musicien = collecter_frais_par_musicien(concerts)

    # Groupement par mois (ordre chronologique dans la saison)
    from mes_utils import grouper_par_mois
    groupes = grouper_par_mois(concerts, "date", descending=False)

    # Crédits (inchangé)
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
        saison=saison_affichee,
        groupes=groupes,
        credits_musiciens=credits_musiciens,
        credits_asso7=credits_asso7,
        musiciens_dict=musiciens_dict,
        frais_par_musicien=frais_par_musicien,  # <-- NEW: on l’envoie au template
        format_currency=format_currency,
        readonly_checkboxes=False
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


from mes_utils import regrouper_cachets_par_mois  # en haut du fichier si pas déjà importé

@app.route('/archives_cachets/<saison>')
def archives_cachets_saison(saison):
    try:
        annee_debut = int(saison.split("-")[0])
        date_debut = datetime(annee_debut, 9, 1).date()
        date_fin = datetime(annee_debut + 1, 8, 31).date()
    except Exception:
        return "Format de saison invalide", 400

    cachets = Cachet.query.filter(
        Cachet.date >= date_debut,
        Cachet.date <= date_fin
    ).all()

    # ✅ même structure que pour “À venir” : [( 'Septembre', [(musicien, [cachets]), ...] ), ...]
    cachets_par_mois = regrouper_cachets_par_mois(cachets, ordre_scolaire=True)

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

    # Opérations passées de la saison (on garde tout, même auto_debit/auto_cb)
    operations = (
        Operation.query.join(Musicien)
        .filter(
            Operation.date >= debut_saison,
            Operation.date <= fin_saison,
            Operation.date <= date.today()
        )
        .order_by(Operation.date.desc())
        .all()
    )

    # ✅ Groupement par mois (descendant pour archives)
    from mes_utils import grouper_par_mois
    groupes = grouper_par_mois(operations, "date", descending=True)

    return render_template(
        "archives_operations_saison.html",
        saison=saison,
        groupes=groupes,
    )


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







