"""
Base de données SQLite (db.py).

RÔLE DANS L'APPLI
SQLite est une base de données qui tient dans un simple fichier sur le disque
(backend/data/chiro.db par défaut) : zéro serveur à installer. Ce fichier-ci sait
ouvrir une connexion à cette base et créer les tables au démarrage.

AVEC QUI IL PARLE
- config.py : lui donne le chemin du fichier de base (DB_PATH).
- main.py   : appelle init_db() au démarrage, puis get_conn() dans chaque route de l'API.
- worker.py : appelle get_conn() pour lire un enregistrement et écrire les cris détectés.

CE QU'ON STOCKE (4 tables)
- campaigns  : une campagne = un festival + une année (ex. "Dub Camp 2027"), avec les dates du festival
- sites      : un emplacement d'enregistreur dans la campagne (avec un drapeau "témoin")
- recordings : un fichier WAV déposé, rattaché à un site et une phase (avant / pendant / apres)
- calls      : chaque cri détecté par BatDetect2 dans un enregistrement

Les tables sont emboîtées : une campagne a des sites, un site a des enregistrements,
un enregistrement a des cris.

SOMMAIRE
1. get_conn()    : ouvrir une connexion (à utiliser avec `with`)
2. _add_column() : ajouter une colonne manquante à une base existante
3. init_db()     : créer les tables et les mettre à niveau au démarrage
"""
# Module standard de Python pour parler à SQLite (rien à installer)
import sqlite3
# Outil pour fabriquer facilement un « context manager » (voir get_conn ci-dessous)
from contextlib import contextmanager

# Le point devant `config` veut dire « le fichier config.py du même dossier (app/) »
from .config import DB_PATH


# ---------- 1. Ouvrir une connexion ----------
# `@contextmanager` est un DÉCORATEUR : une ligne commençant par @ posée au-dessus d'une
# fonction, qui la transforme. Ici, il transforme la fonction en « context manager »,
# c'est-à-dire un objet utilisable avec `with` :
#     with get_conn() as c:
#         ...   # on utilise c
# Le `with` garantit qu'un code de « rangement » s'exécute à la sortie du bloc,
# même si une erreur se produit au milieu. Ici, ce rangement = valider ou annuler, puis fermer.
@contextmanager
def get_conn():
    """
    Ouvre une connexion, la valide (commit) si tout s'est bien passé, et la ferme toujours.
    S'utilise avec : `with get_conn() as c: ...`

    Vocabulaire :
    - commit   : rend définitives toutes les modifications faites depuis l'ouverture.
    - rollback : annule toutes ces modifications, comme si rien n'avait été fait.
    Grâce à ça, une suite de modifications est « tout ou rien » : si une erreur arrive
    au milieu, la base ne reste pas à moitié modifiée.
    """
    # Crée le dossier de données s'il n'existe pas encore (premier lancement).
    # parents=True : crée aussi les dossiers parents manquants ;
    # exist_ok=True : pas d'erreur si le dossier existe déjà.
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Ouvre (ou crée) le fichier de base. timeout=30 : si la base est momentanément
    # occupée par une autre écriture (ex. le thread d'analyse), on patiente jusqu'à
    # 30 secondes au lieu d'échouer tout de suite.
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row  # lire les colonnes par nom : row["name"]
    # Une PRAGMA est une commande de réglage propre à SQLite. Celle-ci active le respect
    # des clés étrangères (REFERENCES … ON DELETE CASCADE plus bas). SQLite ne le fait pas
    # par défaut, et le réglage vaut pour une seule connexion : on le refait donc à chaque ouverture.
    conn.execute("PRAGMA foreign_keys = ON")  # suppression en cascade (campagne → sites → enregistrements → cris)

    # `yield` met la fonction en pause et « prête » la connexion au bloc `with`.
    # Quand le bloc `with` se termine, la fonction reprend juste après le `yield` :
    # - si tout s'est bien passé : commit (on valide) ;
    # - si une erreur est survenue : rollback (on annule), puis `raise` relance l'erreur
    #   pour que l'appelant soit prévenu (on ne la cache pas) ;
    # - dans tous les cas (`finally`) : on ferme la connexion.
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------- 2. Ajouter une colonne manquante ----------
# Le tiret bas au début du nom (`_add_column`) est une convention : fonction « interne »,
# prévue pour être utilisée seulement dans ce fichier.
# Les annotations (`c: sqlite3.Connection`, `-> None`) sont du TYPAGE : elles indiquent
# le type attendu de chaque paramètre et du résultat (None = ne renvoie rien).
# Python ne les vérifie pas à l'exécution ; elles servent à la lecture et aux éditeurs de code.
def _add_column(c: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    """
    Ajoute une colonne si elle manque : permet de faire évoluer une base existante sans la recréer.

    `ddl` est la définition SQL de la colonne (son type et sa valeur par défaut, ex. "TEXT DEFAULT 'manuel'").
    """
    # `PRAGMA table_info(table)` renvoie une ligne par colonne existante de la table.
    # On en fait un ensemble (set) de noms grâce à une « compréhension » : une écriture
    # compacte qui construit une collection en une ligne ({... for r in ...}).
    # Le f"..." est une f-string : le texte entre accolades {table} est remplacé par la valeur
    # de la variable. On l'utilise ici (et pas un `?`) car SQLite n'accepte pas de `?` pour un
    # nom de table ou de colonne. Ce n'est pas dangereux ici : les noms viennent du code
    # (init_db ci-dessous), jamais d'un utilisateur.
    cols = {r["name"] for r in c.execute(f"PRAGMA table_info({table})")}
    # Si la colonne n'existe pas encore, on l'ajoute. Sinon on ne fait rien :
    # on peut donc appeler cette fonction à chaque démarrage sans risque.
    if column not in cols:
        c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


# ---------- 3. Créer / mettre à niveau la base ----------
def init_db() -> None:
    """Crée les tables si elles n'existent pas et ajoute les colonnes récentes. Appelé au démarrage (voir main.py)."""
    with get_conn() as c:
        # Mode WAL (Write-Ahead Logging, « journal écrit d'avance ») : les écritures vont d'abord
        # dans un fichier journal à côté de la base. Conséquence pratique :
        # la page web peut lire pendant que l'analyse écrit, sans se bloquer.
        # Ce réglage est enregistré dans le fichier de base : le faire une fois au démarrage suffit.
        c.execute("PRAGMA journal_mode = WAL")

        # Création des 4 tables. `executescript` exécute plusieurs commandes SQL d'un coup.
        # `IF NOT EXISTS` : si la table existe déjà (base d'un lancement précédent), on n'y touche pas.
        # Repères de lecture :
        # - INTEGER PRIMARY KEY AUTOINCREMENT : identifiant unique donné automatiquement (1, 2, 3…).
        # - REFERENCES x(id) : clé étrangère, la ligne pointe vers une ligne d'une autre table.
        # - ON DELETE CASCADE : si la ligne pointée est supprimée, celle-ci l'est aussi.
        #   Ex. supprimer une campagne supprime ses sites, ses enregistrements et leurs cris.
        # - DEFAULT : valeur mise automatiquement si on n'en donne pas.
        # - Les lignes `-- ...` sont des commentaires SQL.
        # - Les deux CREATE INDEX créent des index : comme l'index d'un livre, ils accélèrent
        #   les recherches « tous les cris d'un enregistrement » et « tous les enregistrements d'une campagne ».
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
        # Pourquoi pas directement dans les CREATE TABLE ci-dessus ? Parce que `CREATE TABLE IF NOT EXISTS`
        # ne touche pas une table qui existe déjà : une base créée avec une ancienne version
        # n'aurait jamais ces colonnes. _add_column les ajoute seulement si elles manquent.

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
