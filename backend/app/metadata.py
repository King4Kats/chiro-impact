"""
Lecture des métadonnées d'un WAV d'enregistreur (AudioMoth surtout) : date, heure ET fuseau horaire.

Pourquoi ? Par défaut, l'AudioMoth nomme ses fichiers en heure UTC (20240712_213000.WAV = 21 h 30 UTC
= 23 h 30 en France l'été). Si on prenait le nom pour l'heure française, on se tromperait de 2 h.
L'AudioMoth écrit l'heure avec son fuseau à deux endroits du fichier (source : son firmware, main.c) :
  - le commentaire ICMT (en tête) : « Recorded at 21:30:00 12/07/2024 (UTC+2) by AudioMoth … »
  - le bloc GUANO « guan » (en FIN de fichier) : « Timestamp:2024-07-12T21:30:00+02:00 »
On lit ces blocs sans charger le son (on saute par-dessus les données audio).

Qui l'utilise ?
- main.py, au dépôt d'un fichier : TRIGGERED_RE (refus des fichiers T.WAV), recording_time()
  puis to_local(). Si le fichier ne contient pas l'heure, main.py se rabat sur le nom du fichier
  (analysis.parse_date) et signale que le fuseau n'est pas vérifié.
- Il lit config.LOCAL_TZ (fuseau du projet, Europe/Paris par défaut).

Sommaire
- _ICMT_RE, _GUANO_TS_RE, TRIGGERED_RE : expressions régulières
- read_chunks()    : parcourt les blocs du WAV et garde ceux qu'on demande
- _icmt_text()     : extrait le commentaire ICMT du bloc LIST
- recording_time() : heure de début avec fuseau (GUANO d'abord, sinon ICMT)
- to_local()       : conversion vers l'heure française

Notions utiles
- Un WAV est une suite de « blocs » (chunks), au format RIFF : 4 lettres d'identifiant, 4 octets de
  taille, puis le contenu. Le fichier commence par « RIFF », sa taille, puis « WAVE ». Viennent
  ensuite les blocs : « fmt » (format du son), « data » (le son lui-même, l'essentiel du poids),
  et d'autres facultatifs comme « LIST » (informations texte) ou « guan » (GUANO).
- GUANO : format ouvert de métadonnées pour les enregistrements de chauves-souris. C'est du texte,
  une ligne « Clé:Valeur » par information, rangé dans un bloc « guan ».
- UTC : temps universel, l'heure de référence sans heure d'été. La France est à UTC+1 l'hiver et
  UTC+2 l'été.
- datetime « aware » / « naive » : en Python, une date « aware » connaît son fuseau (tzinfo rempli),
  une date « naive » n'en a pas. On ne peut convertir d'un fuseau à l'autre qu'une date « aware ».
"""
# Imports
# - re : expressions régulières.
# - struct : décoder des nombres binaires (ici la taille des blocs, écrite sur 4 octets).
# - datetime / timedelta / timezone : dates, durées, et fuseau à décalage fixe (ex. UTC+2).
# - ZoneInfo : fuseau « réel » avec ses règles d'heure d'été (ex. Europe/Paris).
import re
import struct
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from .config import LOCAL_TZ

# Commentaire AudioMoth, ex. « Recorded at 21:30:00 12/07/2024 (UTC+2) by AudioMoth … ».
# Décomposition :
#   Recorded at                   texte fixe
#   (\d{2}):(\d{2}):(\d{2})       heures, minutes, secondes (3 groupes capturés)
#   " "                           un espace
#   (\d{2})/(\d{2})/(\d{4})       jour / mois / année (3 groupes)
#   \(UTC                         « (UTC » ; la parenthèse est précédée de « \ » car « ( » a un
#                                 sens spécial en regex (début de groupe)
#   ([+-]\d{1,2})?                décalage en heures, facultatif : signe + ou -, puis 1 ou 2 chiffres.
#                                 Absent quand l'enregistreur est réglé sur UTC : « (UTC) »
#   (?::(\d{2}))?                 minutes de décalage, facultatives, précédées de « : » (ex. UTC+5:30).
#                                 « (?: … ) » groupe SANS capturer ; seul (\d{2}) est capturé.
#   \)                            parenthèse fermante
# Au total 8 groupes : hh, mi, ss, jj, mm, aaaa, décalage heures, décalage minutes.
_ICMT_RE = re.compile(r"Recorded at (\d{2}):(\d{2}):(\d{2}) (\d{2})/(\d{2})/(\d{4}) \(UTC([+-]\d{1,2})?(?::(\d{2}))?\)")
# Ligne « Timestamp » du bloc GUANO, ex. « Timestamp:2024-07-12T21:30:00+02:00 ».
#   ^ … $          début et fin de LIGNE (grâce à re.MULTILINE ; sans lui, ce serait début/fin du texte)
#   Timestamp:     texte fixe
#   \s*            des espaces éventuels (\s = espace, tabulation… ; * = 0 fois ou plus)
#   (\S+)          la date elle-même : une suite d'au moins un caractère qui n'est pas un espace
_GUANO_TS_RE = re.compile(r"^Timestamp:\s*(\S+)\s*$", re.MULTILINE)
# Fichier AudioMoth en mode « déclenché » : 20240712_213000T.WAV
#   \d{8}_\d{6}   8 chiffres (date), « _ », 6 chiffres (heure)
#   T\.wav$       puis « T.wav » en toute FIN de nom (« \. » = un vrai point ; « $ » = fin du texte)
#   re.IGNORECASE accepte .WAV comme .wav
# Ces fichiers ont eu leurs silences retirés : l'activité calculée dessus serait fausse.
# main.py les refuse avec la marche à suivre (voir docs/AUDIT.md, § 3).
TRIGGERED_RE = re.compile(r"\d{8}_\d{6}T\.wav$", re.IGNORECASE)


def read_chunks(path: str, wanted=(b"LIST", b"guan"), max_size: int = 65536) -> dict[bytes, bytes]:
    """
    Renvoie le contenu des blocs demandés (au plus `max_size` octets chacun), sans lire l'audio.

    Les identifiants sont des « bytes » (b"LIST") et non du texte : on lit le fichier en binaire.
    Résultat : un dict {identifiant: contenu}, vide si ce n'est pas un WAV.
    """
    found: dict[bytes, bytes] = {}
    # "rb" = lecture (read) en binaire : on récupère les octets bruts, sans décodage en texte.
    with open(path, "rb") as f:
        # En-tête du fichier (12 octets) : « RIFF » + taille totale (4 octets) + « WAVE ».
        # S'il manque ou ne correspond pas, ce n'est pas un WAV : on renvoie un dict vide.
        head = f.read(12)
        if len(head) < 12 or head[:4] != b"RIFF" or head[8:12] != b"WAVE":
            return found
        # Parcours des blocs un par un, jusqu'à la fin du fichier.
        while True:
            # En-tête d'un bloc : 8 octets. Moins de 8 = fin du fichier atteinte.
            h = f.read(8)
            if len(h) < 8:
                break
            # cid = identifiant (4 octets). size = taille du contenu.
            # struct.unpack("<I", …) décode 4 octets en nombre entier :
            #   « < » = petit-boutiste (little-endian, l'octet de poids faible en premier, la règle RIFF)
            #   « I » = entier non signé sur 4 octets. unpack renvoie un tuple, d'où le [0].
            cid, size = h[:4], struct.unpack("<I", h[4:])[0]
            # Bloc voulu et pas trop gros : on lit son contenu.
            # La limite de taille évite de charger en mémoire un bloc énorme inattendu.
            if cid in wanted and size <= max_size:
                found[cid] = f.read(size)
                # Règle RIFF : un bloc de taille impaire est suivi d'un octet de remplissage.
                # f.seek(1, 1) avance d'1 octet depuis la position actuelle (le 2e « 1 » = « relatif »).
                if size % 2:
                    f.seek(1, 1)
            else:
                f.seek(size + (size % 2), 1)  # on saute le bloc (ex. les données audio)
    return found


def _icmt_text(list_chunk: bytes) -> Optional[str]:
    """
    Le bloc LIST/INFO contient des sous-blocs ; ICMT = commentaire.

    Les sous-blocs ont la même forme que les blocs : 4 lettres, 4 octets de taille, le contenu.
    """
    # Un bloc LIST peut contenir autre chose que des informations texte : on ne lit que « INFO ».
    if not list_chunk.startswith(b"INFO"):
        return None
    # i = position de lecture dans le bloc, juste après « INFO ».
    i = 4
    # Tant qu'il reste au moins un en-tête de sous-bloc (8 octets) à lire.
    while i + 8 <= len(list_chunk):
        sid, size = list_chunk[i:i + 4], struct.unpack("<I", list_chunk[i + 4:i + 8])[0]
        if sid == b"ICMT":
            # Le texte se termine par un octet nul (\x00), hérité du langage C : on coupe dessus.
            # decode("utf-8", "replace") transforme les octets en texte ; un octet invalide devient « � »
            # au lieu de provoquer une erreur.
            return list_chunk[i + 8:i + 8 + size].split(b"\x00")[0].decode("utf-8", "replace")
        # Sous-bloc suivant : en-tête (8) + contenu + octet de remplissage si la taille est impaire.
        i += 8 + size + (size % 2)
    return None


def recording_time(path: str) -> tuple[Optional[datetime], Optional[str]]:
    """
    Heure de début de l'enregistrement, avec fuseau, lue dans le fichier. Renvoie (datetime « aware »,
    source) ou (None, None) si le fichier ne contient pas l'information.

    source vaut "GUANO" ou "commentaire AudioMoth" : elle est rangée en base pour savoir d'où vient l'heure.
    """
    # Lecture des blocs. OSError = problème d'accès au fichier (absent, illisible…) : on abandonne
    # sans planter, l'appelant se rabattra sur le nom du fichier.
    try:
        chunks = read_chunks(path)
    except OSError:
        return None, None
    # 1re source essayée : le bloc GUANO (date au format ISO, avec fuseau).
    guano = chunks.get(b"guan")
    if guano:
        m = _GUANO_TS_RE.search(guano.decode("utf-8", "replace"))
        if m:
            try:
                # « Z » (zoulou) = UTC. Les anciennes versions de Python ne savent pas lire « Z »
                # avec fromisoformat : on le remplace par l'écriture équivalente « +00:00 ».
                dt = datetime.fromisoformat(m.group(1).replace("Z", "+00:00"))
                # On n'accepte qu'une date « aware » (avec fuseau) : c'est tout l'intérêt de ce bloc.
                if dt.tzinfo is not None:
                    return dt, "GUANO"
            except ValueError:
                # Date mal formée : on ignore et on essaie le commentaire.
                pass
    # 2e source : le commentaire ICMT du bloc LIST.
    if b"LIST" in chunks:
        # « or "" » : si _icmt_text renvoie None, on cherche dans un texte vide (pas d'erreur).
        text = _icmt_text(chunks[b"LIST"]) or ""
        m = _ICMT_RE.search(text)
        if m:
            # Les 8 groupes capturés par la regex, dans l'ordre. tzh / tzm valent None s'ils sont absents.
            hh, mi, ss, dd, mo, yy, tzh, tzm = m.groups()
            # Construction du décalage horaire :
            # - sign = -1 si le décalage commence par « - », sinon +1 (y compris « (UTC) » sans décalage)
            # - on prend la valeur absolue des heures, on ajoute les minutes, puis on applique le signe
            #   (ainsi « -3:30 » donne bien -3 h 30 et non -3 h + 30 min)
            sign = -1 if (tzh or "+").startswith("-") else 1
            offset = timedelta(hours=abs(int(tzh or 0)), minutes=int(tzm or 0)) * sign
            try:
                # timezone(offset) = fuseau à décalage fixe ; la date obtenue est donc « aware ».
                dt = datetime(int(yy), int(mo), int(dd), int(hh), int(mi), int(ss), tzinfo=timezone(offset))
                return dt, "commentaire AudioMoth"
            except ValueError:
                # Date impossible (ex. 31/02) : on abandonne cette source.
                pass
    # Aucune des deux sources n'a donné d'heure fiable.
    return None, None


def to_local(dt: datetime) -> str:
    """
    Heure « aware » → heure locale du projet (Europe/Paris), en ISO sans fuseau ('2024-07-12T23:30:00').

    - astimezone() convertit vers le fuseau du projet ; ZoneInfo connaît les dates d'heure d'été,
      donc 21 h 30 UTC donne 23 h 30 en juillet et 22 h 30 en décembre.
    - replace(tzinfo=None) retire ensuite le fuseau : la base stocke des heures locales « naive »,
      au même format que celles lues dans les noms de fichiers.
    """
    return dt.astimezone(ZoneInfo(LOCAL_TZ)).replace(tzinfo=None).isoformat()
