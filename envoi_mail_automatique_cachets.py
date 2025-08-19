from App import app, mail  # 🔁 on importe l'app Flask déjà configurée
from flask_mail import Message
from mes_utils import get_cachets_par_mois, log_mail_envoye
from datetime import datetime, date
import calendar

with app.app_context():  # 📦 indispensable pour l'accès aux extensions Flask
    today = date.today()
    if today.day != calendar.monthrange(today.year, today.month)[1]:
        print("🟡 Ce n’est pas le dernier jour du mois. Aucun envoi.")
    else:
        mois_suivant = (today.month % 12) + 1
        annee_suivante = today.year + 1 if mois_suivant == 1 else today.year
        cachets = get_cachets_par_mois(mois_suivant, annee_suivante)

        def formater_cachets_html(cachets):
            musiciens = {}
            for c in sorted(cachets, key=lambda x: (c.musicien.nom, c.date)):
                nom = f"{c.musicien.prenom} {c.musicien.nom}"
                musiciens.setdefault(nom, []).append(
                    f"{c.date.strftime('%d/%m/%Y')} – {c.montant:.2f} €"
                )
            return "\n".join([
                f"<p style='margin-left: 20px;'><strong>{nom}</strong><br>" + "<br>".join(lignes) + "</p>"
                for nom, lignes in musiciens.items()
            ])

        mois_nom = calendar.month_name[mois_suivant].capitalize()
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
