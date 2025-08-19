from App import app, mail
from flask_mail import Message
from mes_utils import get_cachets_par_mois, log_mail_envoye
from datetime import date
import calendar

with app.app_context():
    # 📌 Forcer un mois cible pour la simulation :
    mois_suivant = 7  # Juillet
    annee_suivante = 2025

    cachets = get_cachets_par_mois(mois_suivant, annee_suivante)

    def formater_cachets_html(cachets):
        musiciens = {}
        for c in sorted(cachets, key=lambda x: (x.musicien.nom, x.date)):
            nom = f"{c.musicien.prenom} {c.musicien.nom}"
            musiciens.setdefault(nom, []).append(
                f"{c.date.strftime('%d/%m/%Y')} – {c.montant:.2f} €"
            )
        return "\n".join([
            f"<p style='margin-left: 20px;'><strong>{nom}</strong><br>" + "<br>".join(lignes) + "</p>"
            for nom, lignes in musiciens.items()
        ])

    mois_nom = calendar.month_name[mois_suivant].capitalize()
    titre = f"[TEST] Dates MALO à déclarer pour {mois_nom} {annee_suivante}"

    message_html = f"""
    <p>Salut Lionel,</p>
    <p>Voici les cachets MALO à déclarer pour {mois_nom} (test) :</p>
    {formater_cachets_html(cachets)}
    <p>Merci.<br>@+<br><br>Jérôme</p>
    """

    try:
        msg = Message(
            subject=titre,
            sender=app.config['MAIL_USERNAME'],
            recipients=["lionel@odradek78.fr"],  # 👈 Test envoi vers toi uniquement
            cc=[],  # 👈 Vide pour le test
            html=message_html
        )
        mail.send(msg)
        print("✅ TEST : Mail envoyé à jeromemalo1@gmail.com")
        log_mail_envoye(titre, message_html)
    except Exception as e:
        print(f"❌ Erreur lors du test d’envoi : {e}")
