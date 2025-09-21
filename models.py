from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from sqlalchemy import Index


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

    # Tri/filtre fréquents
    date = db.Column(db.Date, nullable=False, index=True)
    paye = db.Column(db.Boolean, default=False, index=True)

    # ⚠️ Texte libre historique (on le garde mais NON obligatoire)
    #    On l’alimente souvent avec lieu_obj.nom pour l’affichage retro-compat.
    lieu = db.Column(db.String(160), nullable=True)

    # ✅ Nouveau lien structuré vers la fiche Lieu
    lieu_id = db.Column(
        db.Integer,
        db.ForeignKey('lieux.id', ondelete='SET NULL'),
        nullable=True,
        index=True
    )
    lieu_obj = db.relationship(
        'Lieu',
        backref=db.backref('concerts', lazy=True)
    )

    # Montants
    recette = db.Column(db.Float, nullable=True)
    recette_attendue = db.Column(db.Float, nullable=True)
    frais = db.Column(db.Float, nullable=True)

    # Participations
    participations = db.relationship(
        'Participation',
        backref='concert',
        cascade="all, delete-orphan"
    )

    # Lien explicite Opérations -> Concert
    operations = db.relationship(
        'Operation',
        back_populates='concert',
        foreign_keys='Operation.concert_id',
        lazy=True
    )

    # Prévisions / mode de paiement
    mode_paiement_prevu = db.Column(db.String(32), default='CB ASSO7')
    frais_previsionnels = db.Column(db.Float, nullable=True)

    # Opération de frais prévisionnels (liée, optionnelle)
    op_prevision_frais_id = db.Column(db.Integer, db.ForeignKey('operations.id'), nullable=True)
    op_prevision_frais = db.relationship(
        'Operation',
        foreign_keys=[op_prevision_frais_id],
        uselist=False
    )

    def __repr__(self):
        who = self.lieu_obj.nom if self.lieu_obj else (self.lieu or '—')
        return f"<Concert #{self.id} {self.date} @ {who}>"



class Participation(db.Model):
    __tablename__ = 'participations'

    id = db.Column(db.Integer, primary_key=True)
    concert_id = db.Column(db.Integer, db.ForeignKey('concerts.id'), nullable=False)
    musicien_id = db.Column(db.Integer, db.ForeignKey('musiciens.id', ondelete="CASCADE"), nullable=False)
    paye = db.Column(db.Boolean, default=False)
    credit_calcule = db.Column(db.Float, nullable=True)
    credit_calcule_potentiel = db.Column(db.Float, default=0.0)
    musicien = db.relationship('Musicien', backref=db.backref('participations', lazy=True))
    gain_fixe = db.Column(db.Numeric(10, 2), nullable=True)  # None = non fixé, sinon montant absolu


class Operation(db.Model):
    __tablename__ = 'operations'

    id = db.Column(db.Integer, primary_key=True)
    musicien_id = db.Column(db.Integer, db.ForeignKey('musiciens.id'), nullable=True)
    type = db.Column(db.String(20), nullable=False)  # 'credit', 'debit'
    motif = db.Column(db.String(100))
    nature = db.Column(db.String(50), nullable=True)
    precision = db.Column(db.String(255))
    montant = db.Column(db.Float, nullable=False)
    date = db.Column(db.Date, nullable=False)
    brut = db.Column(db.Float, nullable=True)

    # ⬇️ FK standard vers concerts
    concert_id = db.Column(db.Integer, db.ForeignKey('concerts.id'), nullable=True)
    concert = db.relationship(
        'Concert',
        back_populates='operations',
        foreign_keys=[concert_id]
    )

    musicien = db.relationship('Musicien', backref=db.backref('operations', lazy=True))

    auto_cb_asso7 = db.Column(db.Boolean, default=False, nullable=False)

    # auto-liens entre opérations (salaire / débit auto / commission, etc.)
    operation_liee_id = db.Column(db.Integer, db.ForeignKey('operations.id'), nullable=True)
    operation_liee = db.relationship('Operation', remote_side=[id], backref='operations_liees')

    auto_debit_salaire = db.Column(db.Boolean, default=False, nullable=False)

    # utilisé pour “Frais (prévisionnels)”
    previsionnel = db.Column(db.Boolean, nullable=False, default=False)


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

# --- NOUVEAUX MODÈLES ---

class Lieu(db.Model):
    __tablename__ = 'lieux'

    id = db.Column(db.Integer, primary_key=True)

    # Identification du lieu
    nom = db.Column(db.String(160), nullable=False, index=True)
    organisme = db.Column(db.String(160), nullable=True)  # ← NEW/présent
    ville = db.Column(db.String(120), nullable=True, index=True)
    code_postal = db.Column(db.String(10), nullable=True, index=True)
    adresse = db.Column(db.String(255), nullable=True)

    # Contacts
    telephone = db.Column(db.String(80), nullable=True)
    email = db.Column(db.String(255), nullable=True)
    contacts = db.Column(db.Text, nullable=True)

    # Notes
    note = db.Column(db.Text, nullable=True)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<Lieu #{self.id} {self.nom} ({self.ville or '—'})>"

    @property
    def label(self) -> str:
        return f"{self.nom} — {self.ville}" if self.ville else self.nom

    @property
    def region(self) -> str:
        try:
            from mes_utils import region_from_cp
            if self.code_postal:
                return region_from_cp(self.code_postal)
        except Exception:
            pass
        return "DIVERS"




# Optionnel : index composite pour éviter trop de doublons (nom, ville)
Index('uq_lieux_nom_ville_unique_soft', Lieu.nom, Lieu.ville)

class Programmateur(db.Model):
    __tablename__ = 'programmateurs'

    id = db.Column(db.Integer, primary_key=True)
    lieu_id = db.Column(
        db.Integer,
        db.ForeignKey('lieux.id', ondelete="CASCADE"),
        nullable=False
    )
    nom = db.Column(db.String(120), nullable=False)
    telephone = db.Column(db.String(50), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    notes = db.Column(db.Text, nullable=True)

    def __repr__(self) -> str:
        return f"<Programmateur {self.nom} (lieu_id={self.lieu_id})>"
