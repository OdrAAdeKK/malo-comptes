import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Musicien, Concert, Participation, Operation  # adapte selon tes modèles
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

# Chemin local de la base SQLite
sqlite_url = 'sqlite:///instance/musiciens.db'  # adapte si le chemin est différent

# URL de ta base PostgreSQL (depuis le fichier .env)
postgres_url = os.getenv("DATABASE_URL")

# Connexions aux deux bases
engine_sqlite = create_engine(sqlite_url)
engine_postgres = create_engine(postgres_url)

SessionSqlite = sessionmaker(bind=engine_sqlite)
SessionPostgres = sessionmaker(bind=engine_postgres)

session_sqlite = SessionSqlite()
session_postgres = SessionPostgres()

def migrer_table(modele):
    print(f"Migration de {modele.__tablename__}...")
    rows = session_sqlite.query(modele).all()
    for row in rows:
        session_postgres.merge(row)
    session_postgres.commit()
    print(f"{len(rows)} lignes migrées.")

def main():
    print("📦 Démarrage de la migration...")
    for modele in [Musicien, Concert, Participation, Operation]:  # adapte si d'autres modèles
        migrer_table(modele)
    print("✅ Migration terminée.")

if __name__ == "__main__":
    main()
