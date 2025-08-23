# 📦 Standard Python
import os
import json
import locale
import sqlite3
from datetime import date, datetime
from collections import OrderedDict
from urllib.parse import quote

# 🌐 Flask & extensions
from flask import Flask, render_template, request, redirect, url_for, flash, current_app, jsonify
from flask_migrate import Migrate
from flask_mail import Mail, Message
from dotenv import load_dotenv
from sqlalchemy.orm import joinedload

# Chargement des variables d’environnement
load_dotenv()

# Création de l'application Flask
app = Flask(__name__)
app.secret_key = "votre_clef_ultra_secrete_ici"

# Configuration de la base de données
database_url = os.getenv('DATABASE_URL')
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Configuration mail
app.config['MAIL_SERVER'] = 'mail.malomusic.fr'
app.config['MAIL_PORT'] = int(os.getenv("MAIL_PORT", 587))
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv("MAIL_USERNAME")
app.config['MAIL_PASSWORD'] = os.getenv("MAIL_PASSWORD")
app.config['MAIL_DEFAULT_SENDER'] = os.getenv("MAIL_USERNAME")

# Initialisation des extensions
from models import db
db.init_app(app)
migrate = Migrate(app, db)
mail = Mail(app)

# 📁 Modules internes
from db import db  # depuis db.py si séparé, sinon adapte
from models import Musicien, Concert, Participation, Operation, Cachet, Report
from mes_utils import (
    format_currency, partage_benefices_concert, calculer_credit_actuel,
    calculer_gains_a_venir, calculer_credit_potentiel,
    concerts_groupes_par_mois, get_credits_concerts, get_musiciens_dict,
    get_cachets_par_mois, log_mail_envoye, annuler_operation,
    preparer_concerts_js, preparer_concerts_data, preparer_concerts_par_musicien,
    charger_musiciens_et_concerts_sqlite, separer_structures_et_musiciens,
    saison_from_date, saisons_from_dates, get_saison_actuelle,
    concerts_non_payes, charger_concerts, generer_tableau_comptes,
    enregistrer_participations, modifier_operation_en_db,
    musicien_to_dict, get_tous_musiciens_actifs, verifier_ou_creer_structures,
    ajouter_cachets, formulaire_to_data, enregistrer_operation_en_db,
    valider_concert_par_operation
)

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
    musiciens = Musicien.query.filter_by(type='musicien')
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
        prenom = request.form.get('prenom', '').strip()
        nom = request.form.get('nom', '').strip()
        actif = bool(request.form.get('actif'))
        if not prenom or not nom:
            erreur = "Tous les champs sont obligatoires."
        else:
            # Vérifie si le musicien existe déjà par exemple
            exist = Musicien.query.filter_by(prenom=prenom, nom=nom).first()
            if exist:
                erreur = "Ce musicien existe déjà."
            else:
                m = Musicien(prenom=prenom, nom=nom, actif=actif)
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


@app.route('/concerts')
def liste_concerts():
    aujourd_hui = date.today()

    concerts = Concert.query.filter(
        Concert.date > aujourd_hui
    ).order_by(Concert.date).all()

    credits_musiciens, credits_asso7, credits_jerome = get_credits_concerts(concerts)
    musiciens_dict = get_musiciens_dict()
    return render_template(
        'concerts.html',
        concerts=concerts,
        credits_musiciens=credits_musiciens,
        credits_asso7=credits_asso7,
        credits_jerome=credits_jerome,
        musiciens_dict=musiciens_dict,
        format_currency=format_currency
    )




# Créer/ajouter
@app.route('/concert/ajouter', methods=['GET', 'POST'])
def ajouter_concert():
    if request.method == 'POST':
        # Récupération des infos du formulaire
        date_str = request.form['date']
        lieu = request.form['lieu']
        recette_str = request.form.get('recette')
        recette = float(recette_str) if recette_str else None
        paye = 'paye' in request.form
        # Création concert en DB
        concert = Concert(date=datetime.strptime(date_str, '%Y-%m-%d'), lieu=lieu, recette=recette, paye=paye)
        db.session.add(concert)
        db.session.commit()
        # Redirection vers participations
        return redirect(url_for('liste_participations', concert_id=concert.id))
    return render_template('ajouter_concert.html')



@app.route('/concert/modifier/<int:concert_id>', methods=['GET', 'POST'])
def modifier_concert(concert_id):
    concert = Concert.query.get_or_404(concert_id)

    if request.method == 'POST':
        concert.date = date.fromisoformat(request.form['date'])
        concert.lieu = request.form['lieu']
        concert.recette = float(request.form['recette']) if request.form['recette'] else None
        concert.paye = 'paye' in request.form
        db.session.commit()

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

    # Suppression
    db.session.delete(concert)
    db.session.commit()

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

    




@app.route('/concerts/non_payes')
def concerts_non_payes_view():
    from mes_utils import concerts_non_payes  # pour s'assurer que la bonne fonction est utilisée

    concerts = Concert.query.order_by(Concert.date.desc()).all()
    concerts_non_payes_list = concerts_non_payes(concerts)  # filtre par date < aujourd'hui ET paye=False

    credits_musiciens, credits_asso7, credits_jerome = get_credits_concerts(concerts_non_payes_list)
    musiciens_dict = get_musiciens_dict()
    saison = get_saison_actuelle()

    return render_template(
        "concerts_non_payes.html",
        concerts=concerts_non_payes_list,
        credits_musiciens=credits_musiciens,
        credits_asso7=credits_asso7,
        credits_jerome=credits_jerome,
        musiciens_dict=musiciens_dict,
        format_currency=format_currency,
        saison=saison
    )



@app.route('/concerts/<int:concert_id>/toggle_paye', methods=['POST'])
def toggle_concert_paye(concert_id):
    concert = Concert.query.get(concert_id)  # ou autre système si JSON
    if concert:
        concert.paye = not concert.paye
        db.session.commit()  # ou sauvegarde dans le fichier
        return redirect(url_for('archives_concerts' if concert.paye else 'liste_concerts'))
    return "Concert non trouvé", 404




@app.route('/concerts/payer', methods=['POST'])

def marquer_concert_paye():
    data = request.get_json()
    concert_id = int(data['id'])
    paye = bool(data['paye'])

    concert = db.session.get(Concert, concert_id)
    if concert:
        concert.paye = paye
        db.session.commit()
        return jsonify(success=True)
    else:
        return jsonify(success=False, error="Concert non trouvé"), 404



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




@app.route('/operations', methods=['GET', 'POST'])
def operations():
    # 👉 On récupère les musiciens actifs ou liés à ASSO7
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
    today_str = date.today().isoformat()
    saison_en_cours = get_saison_actuelle()

    # ✅ Partie modifiée ici
    concerts_a_venir = Concert.query.filter(Concert.date >= date.today()).order_by(Concert.date).all()
    concerts_dicts_a_venir = [concert_to_dict(c) for c in concerts_a_venir]
    concerts_par_musicien = preparer_concerts_par_musicien()
    concerts_par_musicien["__Recette_concert__"] = concerts_dicts_a_venir

    print("\n=== DEBUG : concerts_par_musicien ===")
    for k, v in concerts_par_musicien.items():
        print(f"{k} → {len(v)} concerts : {[c['date'] for c in v]}")
    print("=== FIN DEBUG ===\n")

    if request.method == 'POST':
        data = request.form
        enregistrer_operation_en_db(data)

        if data.get('motif') == 'Recette concert' and data.get('concert_id'):
            valider_concert_par_operation(data['concert_id'], data['montant'])  # ✅ MAJ concert

        flash("✅ Opération enregistrée", "success")
        return redirect(url_for('operations'))
        
    print("musiciens_normaux:")
    for m in musiciens_normaux:
        print((m["prenom"], m["nom"]))

    print("structures:")
    for s in structures:
        print((s["prenom"], s["nom"]))
    

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
        concertsParMusicien=concerts_par_musicien,  # utilisé côté JS
        current_date=today_str,
        saison_en_cours=saison_en_cours
    )




@app.route('/modifier_operation/<int:id>', methods=['GET', 'POST'])
def modifier_operation(id):
    operation = Operation.query.get_or_404(id)

    if request.method == 'POST':
        modifier_operation_en_db(id, request.form)
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
        is_modification=True  # ✔ important pour le template
    )




@app.route('/operations/supprimer', methods=['POST'])
def supprimer_operation():

    data = request.get_json()
    operation_id = data['id']
    operation = Operation.query.get(operation_id)

    if not operation:
        return jsonify({'success': False, 'message': 'Opération introuvable'}), 404

    # 🚫 Interdiction de supprimer une opération de Commission Lionel directement
    if (operation.motif or '').strip().lower() == "commission lionel":
        return jsonify({
            'success': False,
            'message': "Cette opération est générée automatiquement et ne peut être supprimée directement."
        }), 403

    success = annuler_operation(operation_id)
    return jsonify({'success': success})

@app.route("/operations_a_venir")
def operations_a_venir():
    today = date.today()
    operations = (
        db.session.query(Operation)
        .filter(
            Operation.date > today,
            (Operation.auto_cb_asso7.is_(None)) | (Operation.auto_cb_asso7.is_(False))
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

            # Insertion seulement des dates valides
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


@app.route("/supprimer_cachet/<int:id>")
def supprimer_cachet(id):
    cachet = db.session.get(Cachet, id)
    if not cachet:
        abort(404)

    db.session.delete(cachet)
    db.session.commit()
    flash("Cachet supprimé avec succès.", "success")
    return redirect(url_for("cachets_a_venir"))




@app.route("/cachets_a_venir")
def cachets_a_venir():
    today = date.today()
    cachets = Cachet.query.filter(Cachet.date >= today).all()

    # Regroupement par mois
    def mois_fr(dt):
        return dt.strftime('%B').lower()

    cachets_par_mois = {}
    for c in cachets:
        mois = mois_fr(c.date)
        if mois not in cachets_par_mois:
            cachets_par_mois[mois] = {}
        cle_musicien = f"{c.musicien.prenom} {c.musicien.nom}"
        if cle_musicien not in cachets_par_mois[mois]:
            cachets_par_mois[mois][cle_musicien] = []
        cachets_par_mois[mois][cle_musicien].append(c)


    # Couleurs par mois
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
        "cachets_a_venir.html",
        cachets_par_mois=cachets_par_mois,
        couleurs_mois=couleurs_mois
    )


@app.route('/envoyer_mail_cachets', methods=['POST'])
def envoyer_mail_cachets():


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

    mois_1_nom = calendar.month_name[mois_1].capitalize()
    mois_2_nom = calendar.month_name[mois_2].capitalize()
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

    try:
        msg = Message(
            subject=titre,
            sender=current_app.config['MAIL_USERNAME'],
            recipients=["lionel@odradek78.fr"],
            cc=["jeromemalo1@gmail.com"],
            html=message_html
        )
        mail.send(msg)
        print("✅ Mail envoyé avec succès à Lionel.")
        log_mail_envoye(titre, message_html)
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
    # Accepte '2023-2024' ou '2023/2024'
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
        Concert.paye.is True
    ).order_by(Concert.date).all()

    # Regroupement par mois pour affichage (si besoin)
    concerts_par_mois = concerts_groupes_par_mois(concerts)

    # Calcul des crédits pour affichage participants
    credits_musiciens, credits_asso7, credits_jerome = get_credits_concerts(concerts)
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
        readonly_checkboxes=True  # Optionnel, si utilisé dans _concerts_table.html
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
        mois_str = c.date.strftime('%B')  # ex : 'septembre'
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
    # Normaliser : 2024-2025 → 2024/2025
    saison = saison_url.replace("-", "/")



    # Récupération des dates de début et de fin de saison
    debut_saison, fin_saison = get_debut_fin_saison(saison)
    print(f"🔍 Début saison : {debut_saison}, Fin saison : {fin_saison}")

    # Requête SQL : opérations passées de la saison (hors auto CB ASSO7)
    operations = Operation.query.join(Musicien).filter(
        Operation.date >= debut_saison,
        Operation.date <= fin_saison,
        Operation.date < date.today(),  # ⬅️ C’est cette ligne qui filtre les futures
        or_(
            Musicien.nom != "CB ASSO7",
            Operation.auto_cb_asso7.is_(None),
            Operation.auto_cb_asso7.is_(False)
        )
    ).order_by(Operation.date.desc()).all()

    # Diagnostic
    for op in operations:
        try:
            print(f"✅ {op.date} - {op.type} - {op.musicien.nom} - {op.montant}")
        except Exception as e:
            print(f"⚠️ Problème avec une opération : {op.id} - {e}")

    return render_template("archives_operations_saison.html", saison=saison, operations=operations)


# --------- COMPTES ---------

@app.route('/comptes')
def comptes():
    tableau_comptes, musiciens_length = generer_tableau_comptes()
    return render_template(
        'comptes.html',
        tableau_comptes=tableau_comptes,
        musiciens_length=musiciens_length,
        format_currency=format_currency
    )

# --------- REPORTS ---------


from models import Concert

@app.route('/reports', methods=['GET', 'POST'])
def reports():
    musiciens = Musicien.query.order_by(Musicien.prenom, Musicien.nom).all()
    reports_dict = get_reports_dict(musiciens)

    if request.method == 'POST':
        nom = request.form['musicien']
        montant = float(request.form['montant'])
        cible = next((m for m in musiciens if f"{(m.prenom or '').strip()} {(m.nom or '').strip()}" == nom), None)
        if cible:
            r = Report.query.filter_by(musicien_id=cible.id).first()
            if r:
                r.montant = montant
            else:
                r = Report(musicien_id=cible.id, montant=montant)
                db.session.add(r)
            db.session.commit()
        # Redirection directe (quel que soit le cas, succès ou non)
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
    if 'file' not in request.files:
        return jsonify(success=False, message="Aucun fichier reçu.")

    file = request.files['file']
    if file.filename == '':
        return jsonify(success=False, message="Fichier vide.")

    if not file.filename.lower().endswith('.pdf'):
        return jsonify(success=False, message="Format non supporté.")

    filename = secure_filename(file.filename)
    file_path = os.path.join(UPLOAD_FOLDER, filename)
    file.save(file_path)

    # Extraire les infos du PDF
    try:
        infos = extraire_infos_depuis_pdf(file_path)
        return jsonify(success=True, **infos)
    except Exception as e:
        return jsonify(success=False, message="Erreur d’analyse du PDF.", error=str(e))

@app.route('/ajouter_structures_asso7')
def ajouter_structures_asso7():
    nouvelles_structures = ['CAISSE ASSO7', 'TRESO ASSO7']
    for nom in nouvelles_structures:
        existe_deja = Musicien.query.filter_by(nom=nom, type="Structure").first()
        if not existe_deja:
            nouvelle_structure = Musicien(nom=nom, prenom='', type="Structure")
            db.session.add(nouvelle_structure)
    db.session.commit()
    return "Structures ajoutées avec succès !"


# ------------ LANCEMENT ------------
if __name__ == "__main__":
    app.run(debug=True)







