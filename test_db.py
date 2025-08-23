import os
from dotenv import load_dotenv
import psycopg2

# Charger le fichier env.txt
load_dotenv("env.txt")

# Récupérer l'URL
database_url = os.getenv("DATABASE_URL")

if not database_url:
    print("❌ DATABASE_URL introuvable. Vérifie ton env.txt")
else:
    print("✅ DATABASE_URL trouvé :", database_url)

    # Tester la connexion
    try:
        conn = psycopg2.connect(database_url)
        print("✅ Connexion réussie à la base Neon !")
        conn.close()
    except Exception as e:
        print("❌ Erreur de connexion :", e)
