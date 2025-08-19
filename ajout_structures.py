from extensions import db
from App import app
from models import Musicien

with app.app_context():
    structures = ["ASSO7", "CB ASSO7", "CAISSE ASSO7", "TRESO ASSO7"]

    for nom in structures:
        if not Musicien.query.filter_by(nom=nom, type="structure").first():
            nouvelle_structure = Musicien(prenom="", nom=nom, actif=True, type="structure")
            db.session.add(nouvelle_structure)

    db.session.commit()
    print("Structures ajoutées avec succès.")
