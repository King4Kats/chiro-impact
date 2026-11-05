"""
Calculs "métier" : du cri brut aux indicateurs qui servent à prouver un impact.

- GROUPS       : table espèce → groupe (le modèle est fiable au niveau du groupe, pas de l'espèce)
- contacts()   : regroupe les cris en "contacts" de 5 secondes (convention Vigie-Chiro / Barataud)
- parse_date() : lit la date/heure dans le nom du fichier (AudioMoth, BatDetect2, etc.)
- night_of()   : rattache un enregistrement à sa nuit (2 h du matin = nuit de la veille)
- phase_for()  : déduit avant / pendant / après à partir de la nuit et des dates du festival
"""
import re
from datetime import date, datetime, timedelta
from typing import Iterable, Optional

# Durée d'une fenêtre de contact, en secondes. Un contact = une tranche de 5 s avec au moins un cri.
CONTACT_WINDOW = 5.0

# Les 17 classes du modèle BatDetect2 (entraîné au Royaume-Uni), rangées par groupe acoustique.
# Les noms sont ceux QUE RENVOIE LE MODÈLE, y compris son orthographe : il écrit « Barbastellus
# barbastellus » (le nom scientifique correct est Barbastella barbastellus). Un test vérifie que
# chaque classe du modèle a bien un groupe (tests/test_analysis.py).
# À savoir : le modèle ne connaît PAS la Pipistrelle de Kuhl (Pipistrellus kuhlii), très commune
# dans l'ouest de la France, ni le Grand murin (Myotis myotis) : leurs cris seront attribués à une
# espèce voisine. C'est une raison de plus de raisonner en groupes.
GROUPS = {
    "Pipistrellus pipistrellus": "Pipistrelles",
    "Pipistrellus pygmaeus": "Pipistrelles",
    "Pipistrellus nathusii": "Pipistrelles",
    "Myotis daubentonii": "Myotis",
    "Myotis mystacinus": "Myotis",
    "Myotis brandtii": "Myotis",
    "Myotis nattereri": "Myotis",
    "Myotis bechsteinii": "Myotis",
    "Myotis alcathoe": "Myotis",
    "Nyctalus noctula": "Noctules / Sérotines",
    "Nyctalus leisleri": "Noctules / Sérotines",
    "Eptesicus serotinus": "Noctules / Sérotines",
    "Plecotus auritus": "Oreillards",
    "Plecotus austriacus": "Oreillards",
    "Barbastellus barbastellus": "Barbastelle",
    "Rhinolophus ferrumequinum": "Rhinolophes",
    "Rhinolophus hipposideros": "Rhinolophes",
}


def group_of(species: str) -> str:
    """Retourne le groupe d'une espèce, ou 'Autre' si inconnue (ne devrait pas arriver avec le modèle actuel)."""
    return GROUPS.get(species, "Autre")


def contacts(calls: Iterable[dict], threshold: float = 0.3, window: float = CONTACT_WINDOW) -> int:
    """
    Nombre de contacts : on découpe le temps en tranches de `window` secondes
    et on compte les tranches qui contiennent au moins un cri au-dessus du seuil.
    Exemple : 12 cris entre 0 et 3 s = 1 contact ; 2 cris à 1 s et 40 s = 2 contacts.
    """
    # « > » strict : même règle que BatDetect2 (un score affiché 0,3 n'atteint pas le seuil 0,3)
    windows = {int(c["start_time"] // window) for c in calls if c["det_prob"] > threshold}
    return len(windows)


# Motifs de date dans les noms de fichiers :
#   AudioMoth           : 20240712_213000.WAV
#   BatDetect2 exemples : 20180627_215323-RHIFER-LR_0_0.5.wav
#   Wildlife Acoustics  : SITE_20240712_213000.wav
#   AudioMoth avec n° d'appareil / mode déclenché : 24F319036_20240712_213000T.WAV
# Le (?<![0-9A-Za-z]) évite de lire une « date » au milieu d'un numéro d'appareil.
_DATE_RE = re.compile(r"(?<![0-9A-Za-z])(20\d{2})(\d{2})(\d{2})[_-]?(\d{2})(\d{2})(\d{2})")


def parse_date(filename: str) -> Optional[str]:
    """Extrait une date ISO ('2024-07-12T21:30:00') du nom de fichier, ou None si rien trouvé."""
    m = _DATE_RE.search(filename)
    if not m:
        return None
    try:
        y, mo, d, h, mi, s = (int(x) for x in m.groups())
        return datetime(y, mo, d, h, mi, s).isoformat()
    except ValueError:
        return None


# Heure de bascule d'une nuit à la suivante. Les chauves-souris sortent au crépuscule et rentrent
# à l'aube : tout ce qui est enregistré avant midi appartient à la nuit qui a commencé la veille.
NIGHT_CUTOFF_HOUR = 12


def night_of(recorded_at: Optional[str]) -> Optional[str]:
    """'2024-07-13T02:15:00' → '2024-07-12' (la nuit du 12 au 13). None si pas de date."""
    if not recorded_at:
        return None
    dt = datetime.fromisoformat(recorded_at)
    return (dt - timedelta(hours=NIGHT_CUTOFF_HOUR)).date().isoformat()


def phase_for(night: Optional[str], festival_start: Optional[str], festival_end: Optional[str]) -> Optional[str]:
    """
    Phase d'une nuit par rapport au festival. festival_start / festival_end = première et dernière
    NUIT du festival (AAAA-MM-JJ, bornes incluses). Renvoie None si une information manque.
    """
    if not (night and festival_start and festival_end):
        return None
    n, a, b = (date.fromisoformat(x) for x in (night, festival_start, festival_end))
    if n < a:
        return "avant"
    if n <= b:
        return "pendant"
    return "apres"


def summarize_phase(recs: list[dict]) -> dict:
    """
    Agrège une liste d'enregistrements (déjà analysés) d'une même phase :
    - total contacts, total heures d'audio, contacts par heure
    - groupes détectés (union)
    """
    total_contacts = sum(r["n_contacts"] for r in recs)
    total_hours = sum((r["duration"] or 0) for r in recs) / 3600.0
    groups: set[str] = set()
    for r in recs:
        groups.update(r.get("groups", []))
    return {
        "n_recordings": len(recs),
        "hours": round(total_hours, 6),
        "contacts": total_contacts,
        "contacts_per_hour": round(total_contacts / total_hours, 1) if total_hours > 0 else None,
        "groups": sorted(groups),
        "n_groups": len(groups),
    }
