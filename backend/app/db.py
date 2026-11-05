"""
Base de données SQLite (un simple fichier sur le disque, zéro serveur à installer).

On stocke 4 choses :
- campaigns  : une campagne = un festival + une année (ex. "Dub Camp 2027"), avec les dates du festival
- sites      : un emplacement d'enregistreur dans la campagne (avec un drapeau "témoin")
- recordings : un fichier WAV déposé, rattaché à un site et une phase (avant / pendant / apres)
- calls      : chaque cri détecté par BatDetect2 dans un enregistrement
"""
import sqlite3
from contextlib import contextmanager

from .config import DB_PATH


@contextmanager
def get_conn():
    """
    Ouvre une connexion, la valide (commit) si tout s'est bien passé, et la ferme toujours.
    S'utilise avec : `with get_conn() as c: ...`
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row  # lire les colonnes par nom : row["name"]
    conn.execute("PRAGMA foreign_keys = ON")  # suppression en cascade (campagne → sites → enregistrements → cris)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _add_column(c: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    """Ajoute une colonne si elle manque : permet de faire évoluer une base existante sans la recréer."""
    cols = {r["name"] for r in c.execute(f"PRAGMA table_info({table})")}
    if column not in cols:
        c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def init_db() -> None:
    """Crée les tables si elles n'existent pas et ajoute les colonnes récentes. Appelé au démarrage."""
    with get_conn() as c:
        # WAL : la page web peut lire pendant que l'analyse écrit, sans se bloquer
        c.execute("PRAGMA journal_mode = WAL")
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS campaigns (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                description TEXT DEFAULT '',
                created_at  TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS sites (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id INTEGER NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
                name        TEXT NOT NULL,
                is_control  INTEGER DEFAULT 0,   -- 1 = site témoin (hors festival)
                notes       TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS recordings (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id INTEGER NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
                site_id     INTEGER NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
                phase       TEXT NOT NULL,        -- 'avant' | 'pendant' | 'apres'
                filename    TEXT NOT NULL,        -- nom d'origine du fichier
                path        TEXT NOT NULL,        -- chemin sur le disque
                recorded_at TEXT,                 -- date/heure déduite du nom de fichier (ISO)
                duration    REAL,                 -- secondes
                samplerate  INTEGER,
                status      TEXT DEFAULT 'pending',  -- pending | processing | done | error
                error       TEXT DEFAULT '',
                n_calls     INTEGER DEFAULT 0,
                n_contacts  INTEGER DEFAULT 0,
                created_at  TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS calls (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                recording_id INTEGER NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
                start_time   REAL, end_time REAL,
                low_freq     REAL, high_freq REAL,
                species      TEXT,
                grp          TEXT,                -- groupe d'espèces (Pipistrelles, Myotis, ...)
                det_prob     REAL, class_prob REAL
            );
            CREATE INDEX IF NOT EXISTS idx_calls_rec ON calls(recording_id);
            CREATE INDEX IF NOT EXISTS idx_rec_campaign ON recordings(campaign_id);
            """
        )
        # --- Colonnes ajoutées après la v0.1 (les bases existantes sont mises à niveau ici) ---
        # Dates du festival : première et dernière NUIT du festival (format AAAA-MM-JJ)
        _add_column(c, "campaigns", "festival_start", "TEXT")
        _add_column(c, "campaigns", "festival_end", "TEXT")
        # Nuit d'enregistrement : un fichier de 2 h du matin appartient à la nuit qui a commencé la veille
        _add_column(c, "recordings", "night", "TEXT")
        # 'auto' = phase calculée depuis la date + les dates du festival ; 'manuel' = choisie à la main
        _add_column(c, "recordings", "phase_source", "TEXT DEFAULT 'manuel'")
        # Avancement de l'analyse, de 0 à 1 (utile pour les fichiers de plusieurs heures)
        _add_column(c, "recordings", "progress", "REAL DEFAULT 0")
        # D'où vient l'heure : 'GUANO' / 'commentaire AudioMoth' (fuseau connu, convertie en heure
        # française) ou 'nom du fichier' (fuseau inconnu : l'AudioMoth nomme en UTC par défaut)
        _add_column(c, "recordings", "time_source", "TEXT")
