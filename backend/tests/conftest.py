"""
Préparation commune aux tests.

- Les tests utilisent un dossier de données TEMPORAIRE (jamais backend/data) : on peut les lancer
  sans abîmer ses vraies campagnes.
- Les 3 WAV de démo (docs/demo_wav) servent de vrais enregistrements de chauves-souris.
- D'autres WAV sont fabriqués à la volée : long, stéréo, basse fréquence, abîmé.

Lancer :  cd backend  puis  .venv\\Scripts\\python -m pytest -v

Comment pytest utilise ce fichier
---------------------------------
pytest est l'outil qui lance les tests. Il trouve tout seul les fichiers test_*.py et, dans chacun,
les fonctions dont le nom commence par test_. Un test réussit si aucune erreur n'est levée ; il
échoue dès qu'un `assert` est faux (« assert x == 3 » = « je vérifie que x vaut 3, sinon j'arrête »).

Le fichier conftest.py est spécial : pytest le charge AVANT les tests du même dossier. On y met ce
qui est partagé :
- des réglages faits très tôt (variables d'environnement) ;
- des « fixtures » : des fonctions décorées par @pytest.fixture qui PRÉPARENT quelque chose
  (ici un fichier WAV). Un test qui a un paramètre du même nom que la fixture la reçoit
  automatiquement : def test_x(long_wav) reçoit le chemin du WAV fabriqué par long_wav().
  scope="session" = la fixture n'est exécutée qu'une fois pour toute la séance de tests,
  puis son résultat est réutilisé (on ne refabrique pas le même WAV pour chaque test).

Sommaire
- Réglages d'environnement (dossier temporaire)
- MYOMYS, EPTSER, RHIFER : chemins des 3 extraits réels
- pytest_sessionfinish : nettoyage à la fin
- Fixtures : wav_dir, long_wav, very_long_wav, stereo_wav, lowrate_wav, broken_wav
"""
import os
import shutil
import tempfile
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

# Doit être fait AVANT d'importer l'application (la config est lue à l'import)
# - mkdtemp crée un dossier temporaire neuf, au nom unique (ex. chiro-tests-abc123).
# - CHIRO_DATA_DIR : la base SQLite et les WAV déposés des tests iront dans ce dossier.
# - CHIRO_FRONT_DIST : on pointe vers un dossier qui n'existe pas : les tests tournent
#   sans l'interface compilée.
_TMP = Path(tempfile.mkdtemp(prefix="chiro-tests-"))
os.environ["CHIRO_DATA_DIR"] = str(_TMP / "data")
os.environ["CHIRO_FRONT_DIST"] = str(_TMP / "pas-de-frontend")

# Les 3 extraits réels. Le nombre de cris indiqué est celui compté au seuil 0,3 par BatDetect2 ;
# les tests de test_detection.py et test_api.py s'appuient sur ces nombres.
DEMO = Path(__file__).resolve().parents[2] / "docs" / "demo_wav"
MYOMYS = DEMO / "20170701_213954-MYOMYS-LR_0_0.5.wav"   # Murin à moustaches (Myotis) — 15 cris
EPTSER = DEMO / "20180530_213516-EPTSER-LR_0_0.5.wav"   # Sérotine commune — 20 cris
RHIFER = DEMO / "20180627_215323-RHIFER-LR_0_0.5.wav"   # Grand rhinolophe — 9 cris


def pytest_sessionfinish(session, exitstatus):
    """
    « Crochet » (hook) de pytest : appelé automatiquement une fois tous les tests terminés.
    On efface le dossier temporaire. ignore_errors=True : pas d'erreur si un fichier résiste.
    """
    shutil.rmtree(_TMP, ignore_errors=True)


@pytest.fixture(scope="session")
def wav_dir() -> Path:
    """Dossier où sont rangés les WAV fabriqués pour les tests (utilisé par les fixtures suivantes)."""
    d = _TMP / "wav"
    d.mkdir(exist_ok=True)
    return d


@pytest.fixture(scope="session")
def long_wav(wav_dir) -> Path:
    """12 s : 6 fois l'extrait EPTSER séparé par 1,5 s de silence. Date dans le nom : nuit du 12/07/2024."""
    # sf.read renvoie le son (tableau numpy) et sa fréquence d'échantillonnage.
    y, sr = sf.read(EPTSER, dtype="float32")
    # 1,5 s de silence = un tableau de zéros de la bonne longueur.
    sil = np.zeros(int(sr * 1.5), dtype="float32")
    p = wav_dir / "20240712_223000.WAV"
    # np.concatenate met des tableaux bout à bout : [extrait, silence] répété 6 fois.
    # 12 s dépasse 3 s : le fichier est découpé en plusieurs tranches par detection.py.
    sf.write(p, np.concatenate([np.concatenate([y, sil]) for _ in range(6)]), sr)
    return p


@pytest.fixture(scope="session")
def very_long_wav(wav_dir) -> Path:
    """2 min 30 s (plusieurs blocs de 60 s) : un extrait RHIFER toutes les 10 s, sur fond de silence."""
    y, sr = sf.read(RHIFER, dtype="float32")
    # 150 s de silence, puis un extrait collé à 2 s, 12 s, 22 s, …, 142 s (15 extraits).
    # 150 s = 3 blocs de lecture (60 + 60 + 30) : vérifie le recalage du temps entre les blocs.
    total = np.zeros(int(sr * 150), dtype="float32")
    for t in range(2, 150, 10):
        i = int(t * sr)
        total[i:i + len(y)] = y
    # Date dans le nom : 13/07 à 1 h du matin, donc nuit du 12 (voir analysis.night_of).
    p = wav_dir / "20240713_010000.WAV"
    sf.write(p, total, sr)
    return p


@pytest.fixture(scope="session")
def stereo_wav(wav_dir) -> Path:
    """
    WAV stéréo : extrait MYOMYS sur la voie 1, silence sur la voie 2.
    Sert à vérifier que l'analyse lit bien la PREMIÈRE voie.
    """
    y, sr = sf.read(MYOMYS, dtype="float32")
    p = wav_dir / "20240714_220000_stereo.wav"
    # np.stack(..., axis=1) assemble les deux voies côte à côte : tableau (échantillons, 2).
    sf.write(p, np.stack([y, np.zeros_like(y)], axis=1), sr)
    return p


@pytest.fixture(scope="session")
def lowrate_wav(wav_dir) -> Path:
    """Un enregistrement « normal » à 44,1 kHz : ne peut pas contenir d'ultrasons, doit être refusé."""
    # 1 s de silence (44 100 échantillons) à 44,1 kHz, la fréquence des CD audio.
    p = wav_dir / "20240712_230000_telephone.wav"
    sf.write(p, np.zeros(44_100, dtype="float32"), 44_100)
    return p


@pytest.fixture(scope="session")
def broken_wav(wav_dir) -> Path:
    """Faux WAV : commence par « RIFF » mais la suite n'a rien d'un WAV. Doit être refusé comme illisible."""
    p = wav_dir / "20240712_231500_casse.wav"
    p.write_bytes(b"RIFF....ceci n'est pas un wav")
    return p
