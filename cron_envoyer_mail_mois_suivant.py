# cron_envoyer_mail_mois_suivant.py

from datetime import date
from flask import Flask
from App import mail, db, app  # on réutilise ton app Flask
from models import Cachet, Musicien
from flask_mail import Message

MOIS_FR2 = {
    1: "Janvier", 2: "Février", 3: "Mars", 4: "Avril",
    5: "Mai", 6: "Juin", 7: "Juillet", 8: "Août",
    9: "Septembre", 10: "Octobre", 11: "Novembre", 12: "Décembre"
}


def get_cachets_par_mois(mois, annee):
    return (
        db.session.query(Cachet)
        .join(Musicien)  # jointure explicite
        .filter(
            db.extract("month", Cachet.date) == mois,
            db.extract("year", Cachet.date) == annee
        )
        .order_by(Musicien.nom, Cachet.date)  # on trie avec la table jointe
        .all()
    )


def formater_cachets_html(cachets):
    musiciens = {}
    for c in cachets:
        nom_complet = f"{c.musicien.prenom} {c.musicien.nom}"
        musiciens.setdefault(nom_complet, []).append(
            f"{c.date.strftime('%d/%m/%Y')} – {c.montant:.2f} €"
        )
    blocs = []
    for nom, lignes in musiciens.items():
        bloc = f"<p style='margin-left: 20px;'><strong>{nom}</strong><br>" + "<br>".join(lignes) + "</p>"
        blocs.append(bloc)
    return "\n".join(blocs)

def envoyer_mail_cachets_mois_suivant():
    today = date.today()
    mois_suivant = (today.month % 12) + 1
    annee_suivante = today.year if mois_suivant > today.month else today.year + 1
    titre = f"Déclaration des cachets MALO à venir : {MOIS_FR2[mois_suivant]} {annee_suivante}"

    with app.app_context():
        cachets = get_cachets_par_mois(mois_suivant, annee_suivante)
        if not cachets:
            print("Aucun cachet à envoyer pour le mois suivant.")
            log_envoi_mail(titre, "AUCUN_CACHET")
            return

        message_html = f"""
        <p>Salut Lionel,</p>
        <p>Voici la liste des cachets à déclarer pour MALO en {MOIS_FR2[mois_suivant]} :</p>
        {formater_cachets_html(cachets)}
        <p>Merci.<br>@+<br><br>Jérôme</p>
        """

        try:
            msg = Message(
                subject=titre,
                sender=app.config['MAIL_USERNAME'],
                recipients=["lionel@odradek78.fr"],
                cc=["jeromemalo1@gmail.com"],
                html=message_html
            )
            mail.send(msg)
            print("✅ Mail automatique envoyé à Lionel.")
            log_envoi_mail(titre, "SUCCÈS")
        except Exception as e:
            print(f"❌ Erreur lors de l’envoi automatique : {e}")
            log_envoi_mail(titre, f"ERREUR : {e}")



from datetime import datetime

def log_envoi_mail(titre, statut):
    log_path = "log_envoi_mail_cachets.txt"
    horodatage = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"[{horodatage}] {statut} — {titre}\n")


if __name__ == "__main__":
    envoyer_mail_cachets_mois_suivant()
