"""
Préparation commune aux tests.

- Les tests utilisent un dossier de données TEMPORAIRE (jamais backend/data) : on peut les lancer
  sans abîmer ses vraies campagnes.
- Les 3 WAV de démo (docs/demo_wav) servent de vrais enregistrements de chauves-souris.
- D'autres WAV sont fabriqués à la volée : long, stéréo, basse fréquence, abîmé.

Lancer :  cd backend  puis  .venv\\Scripts\\python -m pytest -v
"""
import os
import shutil
import tempfile
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

# Doit être fait AVANT d'importer l'application (la config est lue à l'import)
_TMP = Path(tempfile.mkdtemp(prefix="chiro-tests-"))
os.environ["CHIRO_DATA_DIR"] = str(_TMP / "data")
os.environ["CHIRO_FRONT_DIST"] = str(_TMP / "pas-de-frontend")

DEMO = Path(__file__).resolve().parents[2] / "docs" / "demo_wav"
MYOMYS = DEMO / "20170701_213954-MYOMYS-LR_0_0.5.wav"   # Murin à moustaches (Myotis) — 15 cris
EPTSER = DEMO / "20180530_213516-EPTSER-LR_0_0.5.wav"   # Sérotine commune — 20 cris
RHIFER = DEMO / "20180627_215323-RHIFER-LR_0_0.5.wav"   # Grand rhinolophe — 9 cris


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_TMP, ignore_errors=True)


@pytest.fixture(scope="session")
def wav_dir() -> Path:
    d = _TMP / "wav"
    d.mkdir(exist_ok=True)
    return d


@pytest.fixture(scope="session")
def long_wav(wav_dir) -> Path:
    """12 s : 6 fois l'extrait EPTSER séparé par 1,5 s de silence. Date dans le nom : nuit du 12/07/2024."""
    y, sr = sf.read(EPTSER, dtype="float32")
    sil = np.zeros(int(sr * 1.5), dtype="float32")
    p = wav_dir / "20240712_223000.WAV"
    sf.write(p, np.concatenate([np.concatenate([y, sil]) for _ in range(6)]), sr)
    return p


@pytest.fixture(scope="session")
def very_long_wav(wav_dir) -> Path:
    """2 min 30 s (plusieurs blocs de 60 s) : un extrait RHIFER toutes les 10 s, sur fond de silence."""
    y, sr = sf.read(RHIFER, dtype="float32")
    total = np.zeros(int(sr * 150), dtype="float32")
    for t in range(2, 150, 10):
        i = int(t * sr)
        total[i:i + len(y)] = y
    p = wav_dir / "20240713_010000.WAV"
    sf.write(p, total, sr)
    return p


@pytest.fixture(scope="session")
def stereo_wav(wav_dir) -> Path:
    y, sr = sf.read(MYOMYS, dtype="float32")
    p = wav_dir / "20240714_220000_stereo.wav"
    sf.write(p, np.stack([y, np.zeros_like(y)], axis=1), sr)
    return p


@pytest.fixture(scope="session")
def lowrate_wav(wav_dir) -> Path:
    """Un enregistrement « normal » à 44,1 kHz : ne peut pas contenir d'ultrasons, doit être refusé."""
    p = wav_dir / "20240712_230000_telephone.wav"
    sf.write(p, np.zeros(44_100, dtype="float32"), 44_100)
    return p


@pytest.fixture(scope="session")
def broken_wav(wav_dir) -> Path:
    p = wav_dir / "20240712_231500_casse.wav"
    p.write_bytes(b"RIFF....ceci n'est pas un wav")
    return p
