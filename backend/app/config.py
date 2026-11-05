"""
Réglages de l'application, lus dans les variables d'environnement (avec des valeurs par défaut).

- CHIRO_DATA_DIR : dossier où vivent la base SQLite et les WAV déposés (défaut : backend/data)
- CHIRO_THREADS  : nombre de cœurs que BatDetect2 a le droit d'utiliser (défaut : la moitié de la machine)
- CHIRO_MIN_SAMPLERATE : en dessous, un fichier est refusé car il ne peut pas contenir d'ultrasons
"""
import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = Path(os.getenv("CHIRO_DATA_DIR", BACKEND_DIR / "data"))
UPLOAD_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "chiro.db"

# Interface compilée (npm run build) servie par le même serveur
FRONT_DIST = Path(os.getenv("CHIRO_FRONT_DIST", BACKEND_DIR.parent / "frontend" / "dist"))

THREADS = int(os.getenv("CHIRO_THREADS", max(1, (os.cpu_count() or 2) // 2)))

# Les cris de chauves-souris montent jusqu'à ~120 kHz. Il faut un échantillonnage d'au moins
# 2 × la fréquence la plus haute qu'on veut voir (théorème de Nyquist). À 96 kHz on voit jusqu'à 48 kHz :
# c'est le strict minimum (Pipistrelles, Noctules, Sérotines). Pour les chauves-souris, l'AudioMoth
# s'utilise à 250 ou 384 kHz (il ne propose pas 256 kHz) ; à 192 kHz, rien au-dessus de 96 kHz (Petit rhinolophe perdu).
MIN_SAMPLERATE = int(os.getenv("CHIRO_MIN_SAMPLERATE", 96_000))

# Fuseau horaire dans lequel on affiche les heures et on découpe les nuits
LOCAL_TZ = os.getenv("CHIRO_TZ", "Europe/Paris")
