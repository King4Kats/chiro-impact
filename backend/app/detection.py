"""
Pont vers BatDetect2 : charge le modèle une seule fois, analyse un WAV, renvoie les cris.

Rôle du fichier
---------------
BatDetect2 = réseau de neurones (CNN) entraîné par Mac Aodha et al. (2022). Un CNN (réseau de
neurones « convolutif ») est un modèle d'apprentissage profond, ici exécuté avec la bibliothèque
PyTorch. Il regarde le son sous forme d'image temps × fréquence et y repère les cris.
Entrée : un fichier WAV ultrason. Sortie : une liste de « boîtes » (temps × fréquence),
une par cri, avec une espèce proposée et deux scores (de 0 à 1, ce ne sont pas des probabilités).

Pourquoi on n'appelle pas simplement `api.process_file` ?
BatDetect2 charge TOUT le fichier en mémoire avant de le découper. Une heure à 384 kHz,
c'est ~5,5 Go de RAM : une nuit entière ferait tomber la machine. Ici on lit le fichier
par blocs de 60 s et on reproduit exactement le découpage de BatDetect2 (tranches de 3 s
sans chevauchement), donc les résultats sont les mêmes, avec une mémoire constante.
tests/test_detection.py compare nos résultats à ceux de `process_file` pour le prouver.

Qui l'utilise ?
- worker.py : la file d'analyse appelle detect() pour chaque fichier déposé, puis counted().
- main.py : utilise audio_info() au dépôt, et les seuils ANALYSIS_THRESHOLD / DEFAULT_THRESHOLD.
- Il appelle lui-même analysis.group_of() et lit config.THREADS.

Sommaire
- ANALYSIS_THRESHOLD, DEFAULT_THRESHOLD, counted() : les deux seuils de score
- CHUNK_S, TARGET_SR, BLOCK_S : tailles de découpage (3 s, 256 kHz, 60 s)
- audio_info()   : durée et fréquence d'échantillonnage d'un WAV
- detect()       : analyse complète d'un fichier, bloc par bloc
- _detect_block(): envoie un bloc au modèle, tranche de 3 s par tranche de 3 s

Notions utiles
- Fréquence d'échantillonnage (sample rate, « sr ») : nombre de mesures du son par seconde.
  Un fichier à 384 kHz contient 384 000 nombres par seconde de son.
- Théorème de Nyquist : un fichier échantillonné à F ne peut contenir que des sons jusqu'à F / 2.
  À 384 kHz on voit jusqu'à 192 kHz ; à 192 kHz, rien au-dessus de 96 kHz.
- Tableau numpy (np.ndarray) : une liste de nombres stockée de façon compacte, sur laquelle on fait
  des calculs « vectorisés » (une opération s'applique à tous les éléments d'un coup, très vite).
  Ici, le son est un tableau numpy de nombres à virgule (float32) entre -1 et 1.
"""
# Imports
# - typing : annotations de type (Callable = une fonction qu'on peut appeler).
# - librosa : traitement du son, utilisé ici pour le rééchantillonnage.
# - numpy (np) : tableaux de nombres.
# - soundfile (sf) : lecture des WAV, y compris par morceaux sans tout charger.
# - torch : PyTorch, le moteur qui fait tourner le réseau de neurones.
# - batdetect2.api : l'interface publique de BatDetect2 (modèle + fonctions d'analyse).
from typing import Callable, Optional

import librosa
import numpy as np
import soundfile as sf
import torch
from batdetect2 import api

# Imports internes au projet (le point « . » = « dans le même dossier app/ »).
from .analysis import group_of
from .config import THREADS

# Deux seuils sur le score du modèle (det_prob, de 0 à 1) :
# - ANALYSIS_THRESHOLD : en dessous, le cri n'est pas gardé du tout. On garde dès 0,1 pour pouvoir
#   VOIR les cris faibles dans l'interface (vérifier si le modèle a raté des passages ou s'il s'agit
#   de bruit). Le défaut de l'API BatDetect2 est 0,01 : bien trop bas, il garde surtout du bruit.
# - DEFAULT_THRESHOLD : seuil utilisé pour TOUS les chiffres (cris comptés, contacts, groupes,
#   synthèse). 0,3 est la valeur utilisée dans les exemples de la documentation de BatDetect2 ;
#   c'est un choix de notre part, pas un réglage d'origine du modèle.
# Garder deux seuils permet de régler l'affichage dans l'interface sans relancer l'analyse.
ANALYSIS_THRESHOLD = 0.1
DEFAULT_THRESHOLD = 0.3


def counted(det_prob: float, threshold: float = DEFAULT_THRESHOLD) -> bool:
    """
    Un cri compte s'il dépasse STRICTEMENT le seuil, comme dans BatDetect2.

    Pourquoi « > » et pas « >= » : BatDetect2 arrondit les scores à 3 décimales. Un score brut de
    0,2996 (sous le seuil) nous arrive sous la forme 0,300. Avec « >= » on le compterait à tort.
    """
    return det_prob > threshold

# Configuration de BatDetect2.
# Le modèle est chargé par batdetect2 à l'import (api.MODEL) : on le réutilise à chaque fichier.
# get_config() renvoie un dictionnaire de réglages. On y fixe notre seuil de 0,1 (en dessous,
# BatDetect2 ne renvoie pas le cri) et quiet=True pour qu'il n'écrive rien dans la console.
# Cette ligne s'exécute UNE fois, au premier import de detection.py.
_config = api.get_config(detection_threshold=ANALYSIS_THRESHOLD, quiet=True)

# On limite le nombre de cœurs du processeur utilisés par PyTorch : le serveur doit rester
# utilisable pendant une analyse. THREADS se règle avec la variable d'environnement CHIRO_THREADS.
torch.set_num_threads(THREADS)

# Tailles de découpage, lues dans la configuration de BatDetect2 pour rester alignées sur lui.
# Rééchantillonner = recalculer le son à une autre fréquence d'échantillonnage. Le modèle a été
# entraîné à 256 kHz : tout fichier est donc converti à 256 kHz avant de lui être donné.
CHUNK_S = float(_config["chunk_size"])      # 3 s : taille des tranches vues par le modèle
TARGET_SR = int(_config["target_samp_rate"])  # 256 kHz : le modèle travaille à cette fréquence
BLOCK_S = CHUNK_S * 20                        # 60 s lues sur le disque à la fois (multiple de 3 s)
# BLOCK_S DOIT être un multiple de CHUNK_S : ainsi les tranches de 3 s tombent aux mêmes instants
# que si le fichier était lu d'un seul coup (0-3 s, 3-6 s, …), et les résultats sont identiques.


def audio_info(path: str) -> tuple[float, int]:
    """
    Durée (s) et fréquence d'échantillonnage (Hz) d'un WAV, sans le charger en entier.

    sf.info() lit seulement l'en-tête du fichier : c'est instantané, même pour une nuit entière.
    """
    info = sf.info(path)
    return float(info.duration), int(info.samplerate)


def detect(path: str, on_progress: Optional[Callable[[float], None]] = None) -> list[dict]:
    """
    Lance BatDetect2 sur un fichier et renvoie une liste de dicts prêts pour la table `calls`.
    Chaque cri : start_time, end_time (s), low_freq, high_freq (Hz), species, grp, det_prob, class_prob.
    `on_progress(fraction)` est appelé après chaque bloc (0 → 1).

    on_progress est un « callback » : une fonction qu'on nous passe et qu'on rappelle pour
    signaler l'avancement (worker.py s'en sert pour remplir la barre de progression).
    """
    calls: list[dict] = []
    # « with » ouvre le fichier et garantit qu'il sera refermé à la fin, même en cas d'erreur.
    # sf.SoundFile permet de lire le son morceau par morceau (contrairement à sf.read qui lit tout).
    with sf.SoundFile(path) as f:
        # Informations de base. Une « frame » = un instant échantillonné (une mesure par voie).
        # total = nombre de frames du fichier ; block_frames = nombre de frames dans 60 s.
        sr = f.samplerate
        total = f.frames
        block_frames = int(round(BLOCK_S * sr))
        done = 0
        # Boucle principale : on lit 60 s, on analyse, on passe aux 60 s suivantes.
        # La mémoire utilisée reste celle d'un seul bloc, quelle que soit la durée du fichier.
        while done < total:
            # read() renvoie un tableau numpy de forme (frames, voies). always_2d=True force cette
            # forme à 2 dimensions même pour un fichier mono, pour traiter les deux cas pareil.
            data = f.read(block_frames, dtype="float32", always_2d=True)
            # Sécurité : si plus rien n'est lu (fichier plus court qu'annoncé), on s'arrête.
            if len(data) == 0:
                break
            # data[:, 0] = « toutes les lignes, colonne 0 » : la première voie seulement.
            audio = data[:, 0]  # stéréo : on garde la 1re voie (BatDetect2 ne gère que le mono)
            # Heure (en secondes depuis le début du fichier) où commence ce bloc.
            # Elle sert à recaler les cris : le modèle donne des temps relatifs au bloc.
            block_start = done / sr
            # Mise à 256 kHz, comme le fait BatDetect2 (même méthode « polyphase »).
            # Le rééchantillonnage « polyphase » est une méthode classique pour changer de fréquence
            # d'un rapport fractionnaire (ex. 384 → 256 = × 2/3) : on filtre puis on garde les bons
            # échantillons. Utiliser la même méthode que BatDetect2 donne les mêmes résultats que lui.
            if sr != TARGET_SR:
                audio = librosa.resample(audio, orig_sr=sr, target_sr=TARGET_SR, res_type="polyphase")
            # Analyse du bloc. nyquist = moitié de la fréquence D'ORIGINE (avant passage à 256 kHz) :
            # c'est la fréquence la plus haute que le fichier peut réellement contenir.
            calls.extend(_detect_block(audio, block_start, nyquist=sr / 2))
            # Avancement : on compte les frames réellement lues (le dernier bloc est souvent plus court).
            done += len(data)
            if on_progress:
                on_progress(min(done / total, 1.0))
    # Tri final par heure de début : l'interface et les tests attendent les cris dans l'ordre.
    # key=lambda c: c["start_time"] dit « trier selon la valeur start_time de chaque cri ».
    calls.sort(key=lambda c: c["start_time"])
    return calls


def _detect_block(audio: np.ndarray, block_start: float, nyquist: float) -> list[dict]:
    """
    Passe un bloc (déjà à 256 kHz) au modèle, tranche de 3 s par tranche de 3 s.

    Le « _ » au début du nom est une convention Python : fonction interne au module,
    à ne pas appeler depuis ailleurs.
    """
    out = []
    # n = nombre d'échantillons dans une tranche de 3 s à 256 kHz (768 000).
    n = int(CHUNK_S * TARGET_SR)
    # range(0, len(audio), n) donne 0, n, 2n, … : le début de chaque tranche.
    for i in range(0, len(audio), n):
        # audio[i:i + n] = « tranche » (slice) du tableau, de l'indice i inclus à i + n exclu.
        # La dernière tranche peut être plus courte : numpy s'arrête simplement à la fin.
        piece = audio[i:i + n]
        # Heure de début de cette tranche dans le fichier = début du bloc + position dans le bloc.
        offset = block_start + i / TARGET_SR
        # Appel du modèle. process_audio renvoie 3 valeurs ; seule la 1re (les détections) nous sert,
        # les deux autres sont ignorées avec « _ ».
        annotations, _, _ = api.process_audio(piece, samp_rate=TARGET_SR, config=_config)
        for a in annotations:
            # Comme `process_file` de BatDetect2 : on jette les détections au-dessus de la moitié de
            # l'échantillonnage d'origine. Un fichier à 192 kHz ne peut rien contenir au-dessus de
            # 96 kHz ; une telle « détection » est un artefact du passage à 256 kHz (ticket #22).
            if a["high_freq"] > nyquist:
                continue
            # On convertit chaque détection au format de notre table `calls` :
            # - temps recalés sur le début du fichier (+ offset), arrondis à 0,1 ms
            # - float(...) transforme les nombres numpy en nombres Python ordinaires
            #   (plus simples à ranger dans SQLite et à envoyer en JSON)
            # - grp = groupe d'espèces calculé tout de suite (analysis.group_of)
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
                # det_prob = score « c'est une chauve-souris » ; class_prob = score de l'espèce proposée.
                "det_prob": float(a["det_prob"]),
                "class_prob": float(a["class_prob"]),
            })
    return out
