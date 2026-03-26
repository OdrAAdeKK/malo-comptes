# cron_envoyer_mail_mois_suivant.py

from datetime import date, datetime
from App import mail, db, app
from flask_mail import Message
from mes_utils import get_cachets_par_mois, formater_cachets_html, mois_nom_fr, log_mail_envoye


def envoyer_mail_cachets_mois_suivant():
    today = date.today()
    mois_suivant = (today.month % 12) + 1
    annee_suivante = today.year if mois_suivant > today.month else today.year + 1
    mois_nom = mois_nom_fr(mois_suivant, capitalize=True)
    titre = f"Déclaration des cachets MALO à venir : {mois_nom} {annee_suivante}"

    with app.app_context():
        cachets = get_cachets_par_mois(mois_suivant, annee_suivante)
        if not cachets:
            print("Aucun cachet à envoyer pour le mois suivant.")
            _log(titre, "AUCUN_CACHET")
            return

        message_html = f"""
        <p>Salut Lionel,</p>
        <p>Voici la liste des cachets à déclarer pour MALO en {mois_nom} :</p>
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
            log_mail_envoye(titre, message_html)
            _log(titre, "SUCCÈS")
        except Exception as e:
            print(f"❌ Erreur lors de l'envoi automatique : {e}")
            _log(titre, f"ERREUR : {e}")


def _log(titre, statut):
    log_path = "log_envoi_mail_cachets.txt"
    horodatage = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"[{horodatage}] {statut} — {titre}\n")


if __name__ == "__main__":
    envoyer_mail_cachets_mois_suivant()
