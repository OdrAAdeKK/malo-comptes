import os
import shutil
from datetime import datetime, timedelta

# Config
DB_PATH = "G:/Malo_App/instance/musiciens.db"
BACKUP_DIR = "BACKUPS"
DAYS_TO_KEEP = 90

# Créer dossier de sauvegarde si inexistant
os.makedirs(BACKUP_DIR, exist_ok=True)

# Nom de fichier avec date
today_str = datetime.now().strftime("%Y-%m-%d_%H-%M")
backup_file = os.path.join(BACKUP_DIR, f"musiciens_backup_{today_str}.db")

# Sauvegarde
shutil.copy2(DB_PATH, backup_file)
print(f"Sauvegarde créée : {backup_file}")

# Suppression des sauvegardes de +90 jours
for file in os.listdir(BACKUP_DIR):
    path = os.path.join(BACKUP_DIR, file)
    if os.path.isfile(path):
        creation_time = datetime.fromtimestamp(os.path.getmtime(path))
        if datetime.now() - creation_time > timedelta(days=DAYS_TO_KEEP):
            os.remove(path)
            print(f"Ancienne sauvegarde supprimée : {file}")
