"""
Heure et fuseau lus dans les fichiers AudioMoth (commentaire ICMT en tête, bloc GUANO en fin de fichier).
Les faux fichiers ci-dessous reproduisent le format écrit par le firmware AudioMoth (main.c).

Ces tests visent app/metadata.py (et un peu analysis.parse_date / night_of).
Enjeu : l'AudioMoth nomme ses fichiers en UTC par défaut. Lire l'heure du nom comme une heure
française décalerait tout de 1 ou 2 h, et pourrait changer la nuit ou la phase d'un fichier.

Sommaire
- _chunk(), faux_audiomoth() : fabrication de faux fichiers AudioMoth
- tests GUANO, commentaire ICMT, heure d'hiver, fichier sans métadonnées, fichier non WAV
- mode déclenché (T.WAV) et date dans un nom avec numéro d'appareil

pytest fournit la fixture `tmp_path` : un dossier temporaire neuf pour chaque test, effacé ensuite.
"""
import struct

import numpy as np
import soundfile as sf

from app import analysis, metadata


def _chunk(cid: bytes, data: bytes) -> bytes:
    """
    Fabrique un bloc RIFF : identifiant (4 octets) + taille sur 4 octets (« <I » : entier non signé,
    petit-boutiste) + contenu + un octet nul de remplissage si la taille est impaire (règle RIFF).
    """
    return cid + struct.pack("<I", len(data)) + data + (b"\x00" if len(data) % 2 else b"")


def faux_audiomoth(path, icmt=None, guano=None, sr=384_000):
    """WAV mono silencieux de 0,1 s, avec les blocs AudioMoth demandés."""
    # 1. On écrit un WAV ordinaire avec soundfile (blocs « fmt » et « data » seulement).
    sf.write(path, np.zeros(sr // 10, dtype="float32"), sr, subtype="PCM_16")
    raw = path.read_bytes()
    # 2. On retire l'en-tête « RIFF + taille + WAVE » (12 octets) pour garder les blocs.
    body = raw[12:]  # blocs fmt + data
    # 3. On prépare les blocs à ajouter, s'ils sont demandés :
    #    - en tête : LIST contenant « INFO » puis un sous-bloc ICMT (texte terminé par un octet nul)
    #    - en fin  : guan contenant le texte GUANO
    extra_head = _chunk(b"LIST", b"INFO" + _chunk(b"ICMT", icmt.encode() + b"\x00")) if icmt else b""
    extra_tail = _chunk(b"guan", guano.encode()) if guano else b""
    # fmt (8 + 16 octets) puis LIST, puis data, puis guan (comme l'AudioMoth)
    # 4. Longueur du bloc fmt = 8 octets d'en-tête + sa taille (lue dans les octets 4 à 8).
    fmt_len = 8 + struct.unpack("<I", body[4:8])[0]
    # 5. On réassemble dans l'ordre AudioMoth, puis on réécrit l'en-tête RIFF avec la nouvelle taille.
    content = b"WAVE" + body[:fmt_len] + extra_head + body[fmt_len:] + extra_tail
    path.write_bytes(b"RIFF" + struct.pack("<I", len(content)) + content)
    return path


# Vérifie qu'une heure GUANO en UTC (« Z ») est lue en priorité et convertie en heure française
# d'été (+2 h), et que les blocs ajoutés ne rendent pas le WAV illisible.
# Empêche de reprendre l'heure UTC du nom de fichier pour une heure française.
def test_guano_utc_converti_en_heure_francaise(tmp_path):
    p = faux_audiomoth(tmp_path / "20240712_213000.WAV",
                       icmt="Recorded at 21:30:00 12/07/2024 (UTC) by AudioMoth 24F3190361CAB2E8 at medium gain.",
                       guano="GUANO|Version:1.0\nMake:Open Acoustic Devices\nTimestamp:2024-07-12T21:30:00Z\n")
    dt, src = metadata.recording_time(str(p))
    assert src == "GUANO"
    assert metadata.to_local(dt) == "2024-07-12T23:30:00"   # été : UTC+2
    # Le fichier reste lisible normalement
    assert sf.info(str(p)).samplerate == 384_000


# Vérifie la lecture du commentaire ICMT avec un fuseau « UTC+2 » (pas de bloc GUANO) :
# l'heure est déjà française, rien à décaler, et 1 h 30 du matin appartient à la nuit de la veille.
def test_commentaire_avec_fuseau(tmp_path):
    p = faux_audiomoth(tmp_path / "20240713_013000.WAV",
                       icmt="Recorded at 01:30:00 13/07/2024 (UTC+2) by AudioMoth 24F3190361CAB2E8 at medium gain.")
    dt, src = metadata.recording_time(str(p))
    assert src == "commentaire AudioMoth"
    assert metadata.to_local(dt) == "2024-07-13T01:30:00"
    assert analysis.night_of(metadata.to_local(dt)) == "2024-07-12"


# Vérifie qu'en hiver la conversion ajoute 1 h (UTC+1) et non 2 h.
# Empêche un décalage d'été « codé en dur ».
def test_hiver_utc_plus_1(tmp_path):
    p = faux_audiomoth(tmp_path / "x.wav", guano="Timestamp:2024-12-01T20:00:00Z\n")
    # « dt, _ = … » : on ignore la 2e valeur renvoyée (la source), inutile ici.
    dt, _ = metadata.recording_time(str(p))
    assert metadata.to_local(dt) == "2024-12-01T21:00:00"


# Vérifie qu'un WAV sans bloc d'heure renvoie (None, None) : l'API se rabat alors sur le nom
# du fichier et signale que le fuseau n'est pas vérifié. Empêche d'inventer une heure.
def test_sans_metadonnees(tmp_path):
    p = tmp_path / "20240712_213000.WAV"
    sf.write(p, np.zeros(1000, dtype="float32"), 384_000)
    assert metadata.recording_time(str(p)) == (None, None)


# Vérifie qu'un fichier qui n'est pas un WAV ne fait pas planter la lecture des métadonnées.
def test_fichier_qui_n_est_pas_un_wav(tmp_path):
    p = tmp_path / "x.wav"
    p.write_bytes(b"pas un wav")
    assert metadata.recording_time(str(p)) == (None, None)


# Vérifie que la regex TRIGGERED_RE reconnaît les fichiers AudioMoth en mode déclenché (…T.WAV),
# avec ou sans numéro d'appareil, et ne se trompe pas sur des noms ordinaires.
# Ces fichiers sont refusés : leurs silences ont été retirés, l'activité serait fausse.
def test_mode_declenche_reconnu():
    assert metadata.TRIGGERED_RE.search("20240712_213000T.WAV")
    assert metadata.TRIGGERED_RE.search("24F319036_20240712_213000T.wav")
    assert not metadata.TRIGGERED_RE.search("20240712_213000.WAV")
    assert not metadata.TRIGGERED_RE.search("TEST.WAV")


# Vérifie que parse_date trouve la date après un numéro d'appareil et dans un nom en « T.WAV »,
# mais refuse une suite de chiffres collée à une lettre (le « regard en arrière » de la regex).
def test_date_dans_un_nom_avec_numero_d_appareil():
    assert analysis.parse_date("24F3190361CAB2E8_20240712_213000.WAV") == "2024-07-12T21:30:00"
    assert analysis.parse_date("20240712_213000T.WAV") == "2024-07-12T21:30:00"
    # Une suite de chiffres collée à des lettres n'est pas une date
    assert analysis.parse_date("A20240712_213000.WAV") is None
