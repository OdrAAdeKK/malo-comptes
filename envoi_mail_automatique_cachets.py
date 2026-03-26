from App import app, mail
from flask_mail import Message
from mes_utils import get_cachets_par_mois, formater_cachets_html, mois_nom_fr, log_mail_envoye
from datetime import date
import calendar

with app.app_context():
    today = date.today()
    if today.day != calendar.monthrange(today.year, today.month)[1]:
        print("🟡 Ce n'est pas le dernier jour du mois. Aucun envoi.")
    else:
        mois_suivant = (today.month % 12) + 1
        annee_suivante = today.year + 1 if mois_suivant == 1 else today.year
        cachets = get_cachets_par_mois(mois_suivant, annee_suivante)

        mois_nom = mois_nom_fr(mois_suivant, capitalize=True)
        titre = f"Dates MALO à déclarer pour {mois_nom} {annee_suivante}"
        message_html = f"""
        <p>Salut Lionel,</p>
        <p>Voici les cachets MALO à déclarer pour {mois_nom} :</p>
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
            print("✅ Mail envoyé avec succès à Lionel.")
            log_mail_envoye(titre, message_html)
        except Exception as e:
            print(f"❌ Erreur lors de l'envoi du mail : {e}")
