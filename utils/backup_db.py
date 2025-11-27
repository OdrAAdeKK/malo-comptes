# tools/backup_db.py
import os
import sys
import gzip
import shutil
import time
import subprocess
from pathlib import Path
from urllib.parse import urlparse
from datetime import datetime

# ---- configuration via env (avec valeurs par défaut sûres) ----
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
BACKUP_LOCAL_DIR = Path(os.getenv("BACKUP_LOCAL_DIR", "backups"))
RETENTION_DAYS = int(os.getenv("BACKUP_RETENTION_DAYS", "30"))

# S3 (optionnel) — si tu ne renseignes pas BUCKET, l’upload cloud est ignoré
S3_BUCKET = os.getenv("BACKUP_S3_BUCKET", "").strip()
S3_PREFIX = os.getenv("BACKUP_S3_PREFIX", "db/").strip().rstrip("/") + "/"

# Chemin vers pg_dump si PostgreSQL (laisse vide si il est dans le PATH)
PG_DUMP_PATH = os.getenv("PG_DUMP_PATH", "").strip() or "pg_dump"

def ts() -> str:
    return datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

def ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)

def is_sqlite(url: str) -> bool:
    return url.startswith("sqlite:///") or url.endswith(".sqlite") or url.endswith(".db")

def run(cmd: list[str]):
    print("→", " ".join(cmd))
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if res.returncode != 0:
        print(res.stdout)
        raise RuntimeError(f"Command failed: {' '.join(cmd)}")
    if res.stdout:
        print(res.stdout)

def backup_sqlite() -> Path:
    """
    Copie du fichier sqlite puis compression .gz
    """
    # formats types:
    # sqlite:///absolute/path/to/db.sqlite
    # sqlite:///data/app.db
    if DATABASE_URL.startswith("sqlite:///"):
        sqlite_path = DATABASE_URL.replace("sqlite:///", "", 1)
    else:
        # dernier recours: extraire après 'sqlite://'
        sqlite_path = DATABASE_URL.split("sqlite://")[-1]

    src = Path(sqlite_path).resolve()
    if not src.exists():
        raise FileNotFoundError(f"Fichier SQLite introuvable: {src}")

    ensure_dir(BACKUP_LOCAL_DIR)
    dest_raw = BACKUP_LOCAL_DIR / f"sqlite-{ts()}.db"
    print(f"Copie: {src} → {dest_raw}")
    shutil.copy2(src, dest_raw)

    gz_path = dest_raw.with_suffix(dest_raw.suffix + ".gz")
    print(f"Compression: {dest_raw} → {gz_path}")
    with open(dest_raw, "rb") as f_in, gzip.open(gz_path, "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)
    dest_raw.unlink(missing_ok=True)
    return gz_path

def backup_postgres() -> Path:
    """
    pg_dump au format custom (-Fc), déjà compressé.
    """
    ensure_dir(BACKUP_LOCAL_DIR)
    out = BACKUP_LOCAL_DIR / f"pg-{ts()}.dump"
    cmd = [PG_DUMP_PATH, "-Fc", "-f", str(out), DATABASE_URL]
    run(cmd)
    return out

def upload_s3(path: Path):
    if not S3_BUCKET:
        print("S3: ignoré (BACKUP_S3_BUCKET non défini)")
        return
    # lazy import
    import boto3
    key = S3_PREFIX + path.name
    print(f"S3 upload → s3://{S3_BUCKET}/{key}")
    s3 = boto3.client("s3")
    s3.upload_file(str(path), S3_BUCKET, key)
    print("S3: OK")

def gc_retention():
    if RETENTION_DAYS <= 0:
        return
    cutoff = time.time() - (RETENTION_DAYS * 86400)
    for p in BACKUP_LOCAL_DIR.glob("*"):
        try:
            if p.stat().st_mtime < cutoff:
                print(f"Retention: suppression {p.name}")
                p.unlink()
        except Exception as e:
            print(f"Retention: erreur sur {p}: {e}")

def main():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL manquant")

    print(f"[backup] Database URL: {DATABASE_URL.split('@')[0]}@…")
    if is_sqlite(DATABASE_URL):
        artifact = backup_sqlite()
    else:
        # suppose PostgreSQL
        artifact = backup_postgres()

    print(f"Backup local prêt: {artifact}")
    try:
        upload_s3(artifact)
    except Exception as e:
        print(f"⚠️ Upload S3 échoué: {e}")

    try:
        gc_retention()
    except Exception as e:
        print(f"⚠️ Retention GC: {e}")

if __name__ == "__main__":
    try:
        main()
        print("✅ Backup terminé.")
    except Exception as e:
        print(f"❌ Backup failed: {e}")
        sys.exit(1)
