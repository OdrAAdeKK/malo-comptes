# utils/partage.py

from models import Concert, Participation, Musicien

def partage_benefices_concert(concert):
    if concert.recette is None or concert.frais is None:
        return {}, 0, 0

    total = concert.recette - concert.frais
    parts = [p for p in concert.participations if p.musicien.nom.upper() != "ASSO7"]

    if not parts:
        return {}, 0, total  # tout pour ASSO7

    montant_par_personne = total / len(parts)
    credits = {p.musicien_id: montant_par_personne for p in parts}
    credit_asso7 = 0
    reste = total - montant_par_personne * len(parts)
    return credits, credit_asso7 + reste, total
