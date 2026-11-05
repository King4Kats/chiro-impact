"""
Pont vers BatDetect2 : charge le modèle une seule fois, analyse un WAV, renvoie les cris.

BatDetect2 = réseau de neurones (CNN) entraîné par Mac Aodha et al. (2022).
Entrée : un fichier WAV ultrason. Sortie : une liste de "boîtes" (temps × fréquence),
une par cri, avec une espèce proposée et deux probabilités.

Pourquoi on n'appelle pas simplement `api.process_file` ?
BatDetect2 charge TOUT le fichier en mémoire avant de le découper. Une heure à 384 kHz,
c'est ~5,5 Go de RAM : une nuit entière ferait tomber la machine. Ici on lit le fichier
par blocs de 60 s et on reproduit exactement le découpage de BatDetect2 (tranches de 3 s
sans chevauchement), donc les résultats sont les mêmes, avec une mémoire constante.
"""
from typing import Callable, Optional

import librosa
import numpy as np
import soundfile as sf
import torch
from batdetect2 import api

from .analysis import group_of
from .config import THREADS

# Deux seuils sur le score du modèle (det_prob, de 0 à 1) :
# - ANALYSIS_THRESHOLD : en dessous, le cri n'est pas gardé du tout. On garde dès 0,1 pour pouvoir
#   VOIR les cris faibles dans l'interface (vérifier si le modèle a raté des passages ou s'il s'agit
#   de bruit). Le défaut de l'API BatDetect2 est 0,01 : bien trop bas, il garde surtout du bruit.
# - DEFAULT_THRESHOLD : seuil utilisé pour TOUS les chiffres (cris comptés, contacts, groupes,
#   synthèse). 0,3 est la valeur utilisée dans les exemples de la documentation de BatDetect2 ;
#   c'est un choix de notre part, pas un réglage d'origine du modèle.
ANALYSIS_THRESHOLD = 0.1
DEFAULT_THRESHOLD = 0.3


def counted(det_prob: float, threshold: float = DEFAULT_THRESHOLD) -> bool:
    """Un cri compte s'il dépasse STRICTEMENT le seuil, comme dans BatDetect2."""
    return det_prob > threshold

# Le modèle est chargé par batdetect2 à l'import (api.MODEL) : on le réutilise à chaque fichier.
_config = api.get_config(detection_threshold=ANALYSIS_THRESHOLD, quiet=True)

# On limite le nombre de cœurs : le serveur doit rester utilisable pendant une analyse
torch.set_num_threads(THREADS)

CHUNK_S = float(_config["chunk_size"])      # 3 s : taille des tranches vues par le modèle
TARGET_SR = int(_config["target_samp_rate"])  # 256 kHz : le modèle travaille à cette fréquence
BLOCK_S = CHUNK_S * 20                        # 60 s lues sur le disque à la fois (multiple de 3 s)


def audio_info(path: str) -> tuple[float, int]:
    """Durée (s) et fréquence d'échantillonnage (Hz) d'un WAV, sans le charger en entier."""
    info = sf.info(path)
    return float(info.duration), int(info.samplerate)


def detect(path: str, on_progress: Optional[Callable[[float], None]] = None) -> list[dict]:
    """
    Lance BatDetect2 sur un fichier et renvoie une liste de dicts prêts pour la table `calls`.
    Chaque cri : start_time, end_time (s), low_freq, high_freq (Hz), species, grp, det_prob, class_prob.
    `on_progress(fraction)` est appelé après chaque bloc (0 → 1).
    """
    calls: list[dict] = []
    with sf.SoundFile(path) as f:
        sr = f.samplerate
        total = f.frames
        block_frames = int(round(BLOCK_S * sr))
        done = 0
        while done < total:
            data = f.read(block_frames, dtype="float32", always_2d=True)
            if len(data) == 0:
                break
            audio = data[:, 0]  # stéréo : on garde la 1re voie (BatDetect2 ne gère que le mono)
            block_start = done / sr
            # Mise à 256 kHz, comme le fait BatDetect2 (même méthode « polyphase »)
            if sr != TARGET_SR:
                audio = librosa.resample(audio, orig_sr=sr, target_sr=TARGET_SR, res_type="polyphase")
            calls.extend(_detect_block(audio, block_start, nyquist=sr / 2))
            done += len(data)
            if on_progress:
                on_progress(min(done / total, 1.0))
    calls.sort(key=lambda c: c["start_time"])
    return calls


def _detect_block(audio: np.ndarray, block_start: float, nyquist: float) -> list[dict]:
    """Passe un bloc (déjà à 256 kHz) au modèle, tranche de 3 s par tranche de 3 s."""
    out = []
    n = int(CHUNK_S * TARGET_SR)
    for i in range(0, len(audio), n):
        piece = audio[i:i + n]
        offset = block_start + i / TARGET_SR
        annotations, _, _ = api.process_audio(piece, samp_rate=TARGET_SR, config=_config)
        for a in annotations:
            # Comme `process_file` de BatDetect2 : on jette les détections au-dessus de la moitié de
            # l'échantillonnage d'origine. Un fichier à 192 kHz ne peut rien contenir au-dessus de
            # 96 kHz ; une telle « détection » est un artefact du passage à 256 kHz (ticket #22).
            if a["high_freq"] > nyquist:
                continue
            out.append({
                "start_time": round(a["start_time"] + offset, 4),
                "end_time": round(a["end_time"] + offset, 4),
                "low_freq": float(a["low_freq"]),
                "high_freq": float(a["high_freq"]),
                "species": a["class"],
                "grp": group_of(a["class"]),
                # BatDetect2 renvoie des scores déjà arrondis à 3 décimales. Il garde un cri si son
                # score BRUT est strictement supérieur au seuil : un score brut de 0,2996 arrive ici
                # sous la forme 0,3. On compte donc avec « > seuil » (voir counted()).
                "det_prob": float(a["det_prob"]),
                "class_prob": float(a["class_prob"]),
            })
    return out
