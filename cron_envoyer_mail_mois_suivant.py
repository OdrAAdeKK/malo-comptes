# cron_envoyer_mail_mois_suivant.py
#
# Envoi (manuel ou planifié) à Lionel de la liste des cachets MALO à déclarer
# pour le MOIS SUIVANT.
#
# IMPORTANT : on passe par l'API HTTP Brevo via send_transactional_email() et NON par
# mail.send() (SMTP), car le SMTP sortant est bloqué sur Render -> les mails ne partaient pas.
#
# Pour planifier : créer un service `type: cron` sur Render (ou une tâche planifiée locale)
# qui lance `python cron_envoyer_mail_mois_suivant.py`.

from datetime import datetime
from App import app, send_transactional_email
from mes_utils import (
    get_cachets_par_mois, formater_cachets_html, mois_nom_fr, log_mail_envoye, today_paris,
)

DESTINATAIRES = ["lionel@odradek78.fr"]
COPIE = ["jeromemalo1@gmail.com"]


def envoyer_mail_cachets_mois_suivant():
    with app.app_context():
        today = today_paris()
        mois_suivant = (today.month % 12) + 1
        annee_suivante = today.year if mois_suivant > today.month else today.year + 1
        mois_nom = mois_nom_fr(mois_suivant, capitalize=True)
        titre = f"Déclaration des cachets MALO à venir : {mois_nom} {annee_suivante}"

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
            send_transactional_email(titre, message_html, to_list=DESTINATAIRES, cc_list=COPIE)
            print("✅ Mail automatique envoyé à Lionel (via Brevo).")
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
