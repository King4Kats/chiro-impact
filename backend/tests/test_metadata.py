"""
Heure et fuseau lus dans les fichiers AudioMoth (commentaire ICMT en tête, bloc GUANO en fin de fichier).
Les faux fichiers ci-dessous reproduisent le format écrit par le firmware AudioMoth (main.c).
"""
import struct

import numpy as np
import soundfile as sf

from app import analysis, metadata


def _chunk(cid: bytes, data: bytes) -> bytes:
    return cid + struct.pack("<I", len(data)) + data + (b"\x00" if len(data) % 2 else b"")


def faux_audiomoth(path, icmt=None, guano=None, sr=384_000):
    """WAV mono silencieux de 0,1 s, avec les blocs AudioMoth demandés."""
    sf.write(path, np.zeros(sr // 10, dtype="float32"), sr, subtype="PCM_16")
    raw = path.read_bytes()
    body = raw[12:]  # blocs fmt + data
    extra_head = _chunk(b"LIST", b"INFO" + _chunk(b"ICMT", icmt.encode() + b"\x00")) if icmt else b""
    extra_tail = _chunk(b"guan", guano.encode()) if guano else b""
    # fmt (8 + 16 octets) puis LIST, puis data, puis guan (comme l'AudioMoth)
    fmt_len = 8 + struct.unpack("<I", body[4:8])[0]
    content = b"WAVE" + body[:fmt_len] + extra_head + body[fmt_len:] + extra_tail
    path.write_bytes(b"RIFF" + struct.pack("<I", len(content)) + content)
    return path


def test_guano_utc_converti_en_heure_francaise(tmp_path):
    p = faux_audiomoth(tmp_path / "20240712_213000.WAV",
                       icmt="Recorded at 21:30:00 12/07/2024 (UTC) by AudioMoth 24F3190361CAB2E8 at medium gain.",
                       guano="GUANO|Version:1.0\nMake:Open Acoustic Devices\nTimestamp:2024-07-12T21:30:00Z\n")
    dt, src = metadata.recording_time(str(p))
    assert src == "GUANO"
    assert metadata.to_local(dt) == "2024-07-12T23:30:00"   # été : UTC+2
    # Le fichier reste lisible normalement
    assert sf.info(str(p)).samplerate == 384_000


def test_commentaire_avec_fuseau(tmp_path):
    p = faux_audiomoth(tmp_path / "20240713_013000.WAV",
                       icmt="Recorded at 01:30:00 13/07/2024 (UTC+2) by AudioMoth 24F3190361CAB2E8 at medium gain.")
    dt, src = metadata.recording_time(str(p))
    assert src == "commentaire AudioMoth"
    assert metadata.to_local(dt) == "2024-07-13T01:30:00"
    assert analysis.night_of(metadata.to_local(dt)) == "2024-07-12"


def test_hiver_utc_plus_1(tmp_path):
    p = faux_audiomoth(tmp_path / "x.wav", guano="Timestamp:2024-12-01T20:00:00Z\n")
    dt, _ = metadata.recording_time(str(p))
    assert metadata.to_local(dt) == "2024-12-01T21:00:00"


def test_sans_metadonnees(tmp_path):
    p = tmp_path / "20240712_213000.WAV"
    sf.write(p, np.zeros(1000, dtype="float32"), 384_000)
    assert metadata.recording_time(str(p)) == (None, None)


def test_fichier_qui_n_est_pas_un_wav(tmp_path):
    p = tmp_path / "x.wav"
    p.write_bytes(b"pas un wav")
    assert metadata.recording_time(str(p)) == (None, None)


def test_mode_declenche_reconnu():
    assert metadata.TRIGGERED_RE.search("20240712_213000T.WAV")
    assert metadata.TRIGGERED_RE.search("24F319036_20240712_213000T.wav")
    assert not metadata.TRIGGERED_RE.search("20240712_213000.WAV")
    assert not metadata.TRIGGERED_RE.search("TEST.WAV")


def test_date_dans_un_nom_avec_numero_d_appareil():
    assert analysis.parse_date("24F3190361CAB2E8_20240712_213000.WAV") == "2024-07-12T21:30:00"
    assert analysis.parse_date("20240712_213000T.WAV") == "2024-07-12T21:30:00"
    # Une suite de chiffres collée à des lettres n'est pas une date
    assert analysis.parse_date("A20240712_213000.WAV") is None
