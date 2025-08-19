from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Musicien(db.Model):
    __tablename__ = 'musiciens'

    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(100), nullable=False)
    prenom = db.Column(db.String(100), nullable=True)
    actif = db.Column(db.Boolean, default=True)
    type = db.Column(db.String(20), default='musicien')

    @property
    def credit_actuel(self):
        return sum([c.montant for c in self.cachets])

    @property
    def gains_a_venir(self):
        return sum([c.montant for c in self.cachets]) if hasattr(self, 'cachets') else 0


    @property
    def credit_potentiel(self):
        return self.credit_actuel + self.gains_a_venir


class Concert(db.Model):
    __tablename__ = 'concerts'

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    lieu = db.Column(db.String(100), nullable=False)
    recette = db.Column(db.Float, nullable=True)  # Recette réelle une fois payé
    recette_attendue = db.Column(db.Float, nullable=True)  # 💡 Nouveau champ pour la prévision
    frais = db.Column(db.Float, nullable=True)
    paye = db.Column(db.Boolean, default=False)
    participations = db.relationship('Participation', backref='concert', cascade="all, delete-orphan")
    operations = db.relationship('Operation', backref='concert', lazy=True)
    mode_paiement_prevu = db.Column(db.String(32), default='CB ASSO7')


class Participation(db.Model):
    __tablename__ = 'participations'

    id = db.Column(db.Integer, primary_key=True)
    concert_id = db.Column(db.Integer, db.ForeignKey('concerts.id'), nullable=False)
    musicien_id = db.Column(db.Integer, db.ForeignKey('musiciens.id', ondelete="CASCADE"), nullable=False)
    paye = db.Column(db.Boolean, default=False)
    credit_calcule = db.Column(db.Float, nullable=True)
    credit_calcule_potentiel = db.Column(db.Float, default=0.0)
    musicien = db.relationship('Musicien', backref=db.backref('participations', lazy=True))

class Operation(db.Model):
    __tablename__ = 'operations'

    id = db.Column(db.Integer, primary_key=True)
    musicien_id = db.Column(db.Integer, db.ForeignKey('musiciens.id'), nullable=True)
    type = db.Column(db.String(20), nullable=False)  # 'credit', 'debit'
    motif = db.Column(db.String(100))
    nature = db.Column(db.String(50), nullable=True)  # ex : 'recette', 'frais', 'salaire'
    precision = db.Column(db.String(255))
    montant = db.Column(db.Float, nullable=False)
    date = db.Column(db.Date, nullable=False)
    brut = db.Column(db.Float, nullable=True)
    concert_id = db.Column(db.Integer, db.ForeignKey('concerts.id'), nullable=True)
    musicien = db.relationship('Musicien', backref=db.backref('operations', lazy=True))
    auto_cb_asso7 = db.Column(db.Boolean, default=False, nullable=False)
    operation_liee_id = db.Column(db.Integer, db.ForeignKey('operations.id'), nullable=True)
    auto_debit_salaire = db.Column(db.Boolean, default=False, nullable=False)



class Cachet(db.Model):
    __tablename__ = 'cachets'

    id = db.Column(db.Integer, primary_key=True)
    musicien_id = db.Column(db.Integer, db.ForeignKey('musiciens.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    montant = db.Column(db.Float, nullable=False)
    nombre = db.Column(db.Integer, nullable=False, default=1)

    musicien = db.relationship("Musicien", backref=db.backref("cachets", lazy=True))

    def __repr__(self):
        return f"<Cachet {self.musicien.nom} - {self.date} - {self.montant}€ x{self.nombre}>"


class Report(db.Model):
    __tablename__ = 'reports'

    id = db.Column(db.Integer, primary_key=True)
    musicien_id = db.Column(db.Integer, db.ForeignKey('musiciens.id'), nullable=False)
    montant = db.Column(db.Float, nullable=False)
    musicien = db.relationship('Musicien', backref=db.backref('reports', lazy=True))
