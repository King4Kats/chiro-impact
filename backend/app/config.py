"""
Réglages de l'application (config.py).

RÔLE DANS L'APPLI
Ce fichier rassemble en un seul endroit tous les réglages : où ranger les fichiers,
combien de cœurs donner à l'analyse, quel échantillonnage minimum accepter, etc.
Les autres fichiers ne « devinent » rien : ils importent ces valeurs d'ici
(ex. `from .config import DB_PATH`). Pour changer un réglage, on change un seul endroit.

VARIABLES D'ENVIRONNEMENT
Une variable d'environnement est une valeur donnée au programme par le système au moment
du lancement (ex. `CHIRO_THREADS=4 uvicorn app.main:app`). Elle permet de changer un réglage
sans modifier le code. Si elle n'est pas définie, on prend la valeur par défaut écrite ici.

- CHIRO_DATA_DIR       : dossier où vivent la base SQLite et les WAV déposés (défaut : backend/data)
- CHIRO_FRONT_DIST     : dossier de l'interface compilée (défaut : frontend/dist)
- CHIRO_THREADS        : nombre de cœurs que BatDetect2 a le droit d'utiliser (défaut : la moitié de la machine)
- CHIRO_MIN_SAMPLERATE : en dessous, un fichier est refusé car il ne peut pas contenir d'ultrasons
- CHIRO_TZ             : fuseau horaire utilisé pour afficher les heures et découper les nuits

QUI L'UTILISE
- db.py     : DB_PATH (emplacement du fichier de base de données)
- main.py   : UPLOAD_DIR, FRONT_DIST, MIN_SAMPLERATE
- d'autres modules (détection, métadonnées…) peuvent lire THREADS ou LOCAL_TZ.

SOMMAIRE
1. Dossiers et chemins (BACKEND_DIR, DATA_DIR, UPLOAD_DIR, DB_PATH, FRONT_DIST)
2. Nombre de cœurs pour l'analyse (THREADS)
3. Échantillonnage minimum (MIN_SAMPLERATE)
4. Fuseau horaire (LOCAL_TZ)
"""
# `os` donne accès au système : variables d'environnement, nombre de cœurs…
import os
# `Path` représente un chemin de fichier. On peut l'assembler avec « / » :
# Path("a") / "b" donne a/b, sur Windows comme sur Linux.
from pathlib import Path

# ---------- 1. Dossiers et chemins ----------
# Dossier « backend/ ». `__file__` est le chemin de ce fichier (backend/app/config.py).
# `.resolve()` le rend absolu, `.parent` remonte d'un dossier (app/), puis encore (backend/).
BACKEND_DIR = Path(__file__).resolve().parent.parent

# Dossier des données. `os.getenv(nom, défaut)` lit la variable d'environnement,
# ou renvoie la valeur par défaut si elle n'existe pas. On enveloppe dans Path() pour
# obtenir un vrai chemin même quand la valeur vient du système (elle arrive alors en texte).
DATA_DIR = Path(os.getenv("CHIRO_DATA_DIR", BACKEND_DIR / "data"))
# Sous-dossier où l'on copie les WAV déposés depuis l'interface
UPLOAD_DIR = DATA_DIR / "uploads"
# Le fichier unique qui contient toute la base SQLite
DB_PATH = DATA_DIR / "chiro.db"

# Interface compilée (npm run build) servie par le même serveur.
# `BACKEND_DIR.parent` = racine du projet, puis frontend/dist.
FRONT_DIST = Path(os.getenv("CHIRO_FRONT_DIST", BACKEND_DIR.parent / "frontend" / "dist"))

# ---------- 2. Nombre de cœurs pour l'analyse ----------
# Par défaut : la moitié des cœurs de la machine, pour laisser de la place au reste.
# - `os.cpu_count()` peut renvoyer None (nombre inconnu) : `or 2` prend alors 2.
# - `// 2` est la division entière (7 // 2 = 3).
# - `max(1, ...)` garantit au moins 1 cœur.
# - `int(...)` convertit en nombre, car une variable d'environnement arrive toujours en texte.
THREADS = int(os.getenv("CHIRO_THREADS", max(1, (os.cpu_count() or 2) // 2)))

# ---------- 3. Échantillonnage minimum ----------
# L'échantillonnage (en Hz) = nombre de mesures du son par seconde.
# Les cris de chauves-souris montent jusqu'à ~120 kHz. Il faut un échantillonnage d'au moins
# 2 × la fréquence la plus haute qu'on veut voir (théorème de Nyquist). À 96 kHz on voit jusqu'à 48 kHz :
# c'est le strict minimum (Pipistrelles, Noctules, Sérotines). Pour les chauves-souris, l'AudioMoth
# s'utilise à 250 ou 384 kHz (il ne propose pas 256 kHz) ; à 192 kHz, rien au-dessus de 96 kHz (Petit rhinolophe perdu).
# `96_000` s'écrit avec un tiret bas pour la lisibilité : Python le lit comme 96000.
MIN_SAMPLERATE = int(os.getenv("CHIRO_MIN_SAMPLERATE", 96_000))

# ---------- 4. Fuseau horaire ----------
# Fuseau horaire dans lequel on affiche les heures et on découpe les nuits
# (nom au format standard « Continent/Ville », ex. "Europe/Paris")
LOCAL_TZ = os.getenv("CHIRO_TZ", "Europe/Paris")
