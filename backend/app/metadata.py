"""
Lecture des métadonnées d'un WAV d'enregistreur (AudioMoth surtout) : date, heure ET fuseau horaire.

Pourquoi ? Par défaut, l'AudioMoth nomme ses fichiers en heure UTC (20240712_213000.WAV = 21 h 30 UTC
= 23 h 30 en France l'été). Si on prenait le nom pour l'heure française, on se tromperait de 2 h.
L'AudioMoth écrit l'heure avec son fuseau à deux endroits du fichier (source : son firmware, main.c) :
  - le commentaire ICMT (en tête) : « Recorded at 21:30:00 12/07/2024 (UTC+2) by AudioMoth … »
  - le bloc GUANO « guan » (en FIN de fichier) : « Timestamp:2024-07-12T21:30:00+02:00 »
On lit ces blocs sans charger le son (on saute par-dessus les données audio).

Un WAV est une suite de « blocs » (chunks) : 4 lettres d'identifiant, 4 octets de taille, le contenu.
"""
import re
import struct
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from .config import LOCAL_TZ

_ICMT_RE = re.compile(r"Recorded at (\d{2}):(\d{2}):(\d{2}) (\d{2})/(\d{2})/(\d{4}) \(UTC([+-]\d{1,2})?(?::(\d{2}))?\)")
_GUANO_TS_RE = re.compile(r"^Timestamp:\s*(\S+)\s*$", re.MULTILINE)
# Fichier AudioMoth en mode « déclenché » : 20240712_213000T.WAV
TRIGGERED_RE = re.compile(r"\d{8}_\d{6}T\.wav$", re.IGNORECASE)


def read_chunks(path: str, wanted=(b"LIST", b"guan"), max_size: int = 65536) -> dict[bytes, bytes]:
    """Renvoie le contenu des blocs demandés (au plus `max_size` octets chacun), sans lire l'audio."""
    found: dict[bytes, bytes] = {}
    with open(path, "rb") as f:
        head = f.read(12)
        if len(head) < 12 or head[:4] != b"RIFF" or head[8:12] != b"WAVE":
            return found
        while True:
            h = f.read(8)
            if len(h) < 8:
                break
            cid, size = h[:4], struct.unpack("<I", h[4:])[0]
            if cid in wanted and size <= max_size:
                found[cid] = f.read(size)
                if size % 2:
                    f.seek(1, 1)
            else:
                f.seek(size + (size % 2), 1)  # on saute le bloc (ex. les données audio)
    return found


def _icmt_text(list_chunk: bytes) -> Optional[str]:
    """Le bloc LIST/INFO contient des sous-blocs ; ICMT = commentaire."""
    if not list_chunk.startswith(b"INFO"):
        return None
    i = 4
    while i + 8 <= len(list_chunk):
        sid, size = list_chunk[i:i + 4], struct.unpack("<I", list_chunk[i + 4:i + 8])[0]
        if sid == b"ICMT":
            return list_chunk[i + 8:i + 8 + size].split(b"\x00")[0].decode("utf-8", "replace")
        i += 8 + size + (size % 2)
    return None


def recording_time(path: str) -> tuple[Optional[datetime], Optional[str]]:
    """
    Heure de début de l'enregistrement, avec fuseau, lue dans le fichier. Renvoie (datetime « aware »,
    source) ou (None, None) si le fichier ne contient pas l'information.
    """
    try:
        chunks = read_chunks(path)
    except OSError:
        return None, None
    guano = chunks.get(b"guan")
    if guano:
        m = _GUANO_TS_RE.search(guano.decode("utf-8", "replace"))
        if m:
            try:
                dt = datetime.fromisoformat(m.group(1).replace("Z", "+00:00"))
                if dt.tzinfo is not None:
                    return dt, "GUANO"
            except ValueError:
                pass
    if b"LIST" in chunks:
        text = _icmt_text(chunks[b"LIST"]) or ""
        m = _ICMT_RE.search(text)
        if m:
            hh, mi, ss, dd, mo, yy, tzh, tzm = m.groups()
            sign = -1 if (tzh or "+").startswith("-") else 1
            offset = timedelta(hours=abs(int(tzh or 0)), minutes=int(tzm or 0)) * sign
            try:
                dt = datetime(int(yy), int(mo), int(dd), int(hh), int(mi), int(ss), tzinfo=timezone(offset))
                return dt, "commentaire AudioMoth"
            except ValueError:
                pass
    return None, None


def to_local(dt: datetime) -> str:
    """Heure « aware » → heure locale du projet (Europe/Paris), en ISO sans fuseau ('2024-07-12T23:30:00')."""
    return dt.astimezone(ZoneInfo(LOCAL_TZ)).replace(tzinfo=None).isoformat()
