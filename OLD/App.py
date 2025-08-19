from flask import Flask, render_template, request, redirect, url_for, flash
from flask_migrate import Migrate
from models import db, Musicien, Concert, Participation, Operation, Cachet, Report
from datetime import date, datetime
from mes_utils import partage_benefices_concert, format_currency, get_credits_concerts, get_musiciens_dict, enregistrer_participations, get_reports_dict
from mes_utils import concerts_groupes_par_mois
from collections import OrderedDict
from mes_utils import (
    partage_benefices_concert,
    format_currency,
    calculer_credit_actuel,
    calculer_gains_a_venir,
    calculer_credit_potentiel
)
from mes_utils import saisons_from_dates
from mes_utils import concerts_non_payes
from mes_utils import charger_concerts
from mes_utils import get_saison_actuelle
from mes_utils import recalculer_frais_concert
from mes_utils import generer_tableau_comptes
from mes_utils import enregistrer_participations
import json
import os
import sqlite3


app = Flask(__name__)
app.jinja_env.globals.update(format_currency=format_currency)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///musiciens.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = "votre_clef_ultra_secrete_ici"

db.init_app(app)
migrate = Migrate(app, db)

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
from mes_utils import get_credits_concerts, get_musiciens_dict

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



# Modifier
@app.route('/concert/modifier/<int:concert_id>', methods=['GET', 'POST'])
def modifier_concert(concert_id):
    concert = Concert.query.get_or_404(concert_id)
    if request.method == 'POST':
        concert.date = date.fromisoformat(request.form['date'])
        concert.lieu = request.form['lieu']
        concert.recette = float(request.form['recette']) if request.form['recette'] else None
        concert.frais = float(request.form['frais']) if request.form['frais'] else None
        concert.paye = 'paye' in request.form
        db.session.commit()
        return redirect(url_for('liste_concerts'))

    # *** AJOUT ici ***
    retour_url = url_for('liste_concerts')
    return render_template('modifier_concert.html', concert=concert, retour_url=retour_url)

# Supprimer
@app.route('/concert/supprimer/<int:concert_id>', methods=['POST'])
def supprimer_concert(concert_id):
    concert = Concert.query.get_or_404(concert_id)
    db.session.delete(concert)
    db.session.commit()
    return redirect(url_for('liste_concerts'))
    

from datetime import date

from datetime import date
from flask import render_template
from mes_utils import get_credits_concerts  # ou adapte selon l'emplacement

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


from flask import request, jsonify
from models import Concert, db  # adapte ce chemin si besoin

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
        Musicien.actif == True,
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
    musiciens = Musicien.query.order_by(Musicien.nom).all()
    if request.method == 'POST':
        participation.musicien_id = int(request.form['musicien_id'])
        participation.paye = 'paye' in request.form
        db.session.commit()
        return redirect(url_for('liste_participations', concert_id=participation.concert_id))
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

from flask import Flask, render_template, request
import os
from datetime import date

from mes_utils import (
    formulaire_to_data,
    enregistrer_operation_en_db,
    charger_musiciens_et_concerts_sqlite,
    separer_structures_et_musiciens,
    preparer_concerts_js,
    preparer_concerts_data
)

@app.route('/operations', methods=['GET', 'POST'])
def operations():
    chemin_ops = os.path.join("data", "operations.json")
    chemin_db = os.path.join("instance", "musiciens.db")

    if request.method == 'POST':
        try:
            data = formulaire_to_data(request.form)
            enregistrer_operation_en_db(data)
            print("✅ Opération enregistrée en base :", data)
        except Exception as e:
            print("❌ Erreur lors de l’enregistrement :", e)

    musiciens, concerts = charger_musiciens_et_concerts_sqlite(chemin_db)
    musiciens_normaux, structures = separer_structures_et_musiciens(musiciens)
    concerts_js = preparer_concerts_js(concerts)
    concertsData = preparer_concerts_data()
    today_str = date.today().isoformat()

    return render_template(
        "operations.html",
        musiciens=[dict(m) for m in musiciens],
        musiciens_normaux=musiciens_normaux,
        structures=structures,
        concerts_js=concerts_js,
        concertsData=concertsData,
        current_date=today_str
    )

@app.route('/modifier_operation/<int:id>', methods=['GET', 'POST'])
def modifier_operation(id):
    operation = Operation.query.get_or_404(id)
    
    if request.method == 'POST':
        # Logic to handle form submission
        data = request.form
        # Effectuer la mise à jour de l'opération dans la base de données
        operation.montant = float(data['montant'])
        operation.precision = data['precision']
        # Ajouter d'autres champs à modifier ici

        db.session.commit()
        return redirect(url_for('archives_operations_saison', saison='2024-25'))  # Rediriger vers la saison appropriée après la modification

    # Pour la méthode GET, afficher le formulaire de modification
    return render_template('modifier_operation.html', operation=operation)


from mes_utils import annuler_operation

@app.route('/operations/supprimer', methods=['POST'])
def supprimer_operation():
    from mes_utils import annuler_operation
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
            (Operation.auto_cb_asso7.is_(None)) | (Operation.auto_cb_asso7 == False)
        )
        .order_by(Operation.date)
        .all()
    )
    return render_template("operations_a_venir.html", operations=operations)

# --------- CRUD CACHETS ---------
    
@app.route('/cachets')
def cachets():
    # Ici tu pourras charger les données cachets plus tard
    return render_template('cachets.html')


# --------- CRUD ARCHIVES ---------

@app.route('/archives')
def page_archives():
    # Tu pourras charger ici toutes les données d’archives plus tard
    return render_template('archives.html')


from flask import render_template
from models import Concert
from mes_utils import saison_from_date
from datetime import date

@app.route('/archives/concerts')
def archives_concerts():
    concerts = Concert.query.order_by(Concert.date.desc()).all()
    saisons = set()
    for concert in concerts:
        saisons.add(saison_from_date(concert.date))
    return render_template('archives_concerts.html', saisons=sorted(saisons, reverse=True))


from mes_utils import partage_benefices_concert, concerts_groupes_par_mois, format_currency
from collections import OrderedDict

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
        Concert.paye == True
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
    
@app.route('/archives/cachets')
def archives_cachets():
    chemin_cachets = os.path.join("data", "cachets.json")
    dates = get_all_dates_from_json(chemin_cachets, "details_dates")
    saisons_triees = saisons_from_dates(dates)
    return render_template("archives_cachets.html", saisons=saisons_triees)



@app.route("/archives_operations")
def archives_operations():
    from models import Operation
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

@app.route("/archives_operations_saison/<saison>")
def archives_operations_saison(saison):
    from mes_utils import get_debut_fin_saison
    from models import Operation, Musicien
    from sqlalchemy import or_, and_

    # Récupération des dates de début et de fin de saison
    debut_saison, fin_saison = get_debut_fin_saison(saison)
    print(f"🔍 Début saison : {debut_saison}, Fin saison : {fin_saison}")

    # Requête SQL : exclure les opérations CB ASSO7 auto-générées
    operations = Operation.query.join(Musicien).filter(
        Operation.date >= debut_saison,
        Operation.date <= fin_saison,
        or_(
            Musicien.nom != "CB ASSO7",
            Operation.auto_cb_asso7.is_(None),
            Operation.auto_cb_asso7 == False
        )
    ).order_by(Operation.date.desc()).all()

    # Diagnostic : affichage des opérations trouvées
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


from flask import redirect, url_for
from mes_utils import get_reports_dict

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

# ------------ LANCEMENT ------------
if __name__ == "__main__":
    app.run(debug=True)
