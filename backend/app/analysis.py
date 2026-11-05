"""
Calculs « métier » : du cri brut aux indicateurs qui servent à mesurer l'effet du festival.

Rôle du fichier
---------------
BatDetect2 (voir detection.py) renvoie une liste de cris. Ce fichier transforme ces cris en chiffres
lisibles par un naturaliste : nombre de contacts, groupes d'espèces, nuit et phase (avant / pendant /
après le festival). Il ne lit aucun fichier audio et ne parle pas à la base de données : ce ne sont
que des fonctions de calcul « pures » (mêmes entrées → même résultat), faciles à tester.

Qui l'utilise ?
- detection.py : appelle group_of() pour ranger chaque cri détecté dans un groupe.
- main.py (l'API) : appelle parse_date(), night_of(), phase_for() au dépôt d'un fichier,
  summarize_phase() pour la synthèse, et sert la table GROUPS à l'interface.
- worker.py (la file d'analyse) : appelle contacts() une fois les cris détectés.
- tests/test_analysis.py : vérifie chacune de ces fonctions.

Sommaire
- GROUPS / group_of() : table espèce → groupe. Le modèle n'a pas été évalué sur des données
  françaises : le groupe comme l'espèce restent une indication à faire confirmer.
- contacts()          : regroupe les cris en « contacts » de 5 secondes (convention Vigie-Chiro / Barataud)
- parse_date()        : lit la date/heure dans le nom du fichier (AudioMoth, BatDetect2, etc.)
- night_of()          : rattache un enregistrement à sa nuit (2 h du matin = nuit de la veille)
- phase_for()         : déduit avant / pendant / après à partir de la nuit et des dates du festival
- summarize_phase()   : additionne les enregistrements d'une phase (contacts par heure, groupes)
"""
# Imports de la bibliothèque standard de Python (rien à installer) :
# - re : expressions régulières, pour reconnaître une date dans un nom de fichier.
# - datetime : manipuler des dates. `date` = un jour ; `datetime` = un jour + une heure ;
#   `timedelta` = une durée, qu'on peut ajouter à une date ou lui retirer.
# - typing : uniquement des « annotations de type ». Elles ne changent rien à l'exécution, elles
#   documentent ce qu'une fonction attend. Optional[str] veut dire « une chaîne OU None ».
#   Iterable[dict] veut dire « n'importe quoi qu'on peut parcourir avec for » (liste, générateur…).
import re
from datetime import date, datetime, timedelta
from typing import Iterable, Optional

# Durée d'une fenêtre de contact, en secondes. Un contact = une tranche de 5 s avec au moins un cri.
# Le nom en MAJUSCULES est une convention Python : « constante, on n'y touche pas pendant l'exécution ».
CONTACT_WINDOW = 5.0

# Les 17 classes du modèle BatDetect2 (entraîné au Royaume-Uni), rangées par groupe acoustique.
# Les noms sont ceux QUE RENVOIE LE MODÈLE, y compris son orthographe : il écrit « Barbastellus
# barbastellus » (le nom scientifique correct est Barbastella barbastellus). Un test vérifie que
# chaque classe du modèle a bien un groupe (tests/test_analysis.py).
# À savoir : le modèle ne connaît PAS la Pipistrelle de Kuhl (Pipistrellus kuhlii), très commune
# dans l'ouest de la France, ni le Grand murin (Myotis myotis) : leurs cris seront attribués à une
# espèce voisine. C'est une raison de plus de raisonner en groupes.
#
# Côté Python : c'est un dictionnaire (dict), une table « clé → valeur ». Ici la clé est le nom
# d'espèce renvoyé par le modèle, la valeur est le nom du groupe affiché dans l'interface.
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
    """
    Retourne le groupe d'une espèce, ou 'Autre' si inconnue (ne devrait pas arriver avec le modèle actuel).

    dict.get(clé, défaut) renvoie la valeur de la clé, ou `défaut` si la clé n'existe pas.
    Contrairement à GROUPS[species], cela ne plante jamais (pas d'erreur KeyError).
    """
    return GROUPS.get(species, "Autre")


def contacts(calls: Iterable[dict], threshold: float = 0.3, window: float = CONTACT_WINDOW) -> int:
    """
    Nombre de contacts : on découpe le temps en tranches de `window` secondes
    et on compte les tranches qui contiennent au moins un cri au-dessus du seuil.
    Exemple : 12 cris entre 0 et 3 s = 1 contact ; 2 cris à 1 s et 40 s = 2 contacts.

    Un contact mesure une ACTIVITÉ, pas un nombre d'individus : 40 cris dans la même tranche
    comptent 1, qu'ils viennent d'une seule chauve-souris ou de plusieurs.

    Paramètres
    - calls     : les cris, chacun sous forme de dict avec au moins "start_time" (s) et "det_prob" (score 0 à 1)
    - threshold : seuil de score (0,3 par défaut, la même valeur que detection.DEFAULT_THRESHOLD)
    - window    : largeur d'une tranche en secondes (5 s par défaut)
    """
    # Comment on trouve la tranche d'un cri : division entière de son heure de début par 5.
    #   « // » est la division entière : 7.2 // 5 = 1.0 ; 4.9 // 5 = 0.0 ; 5.1 // 5 = 1.0
    #   Un cri entre 0 et 4,99 s est dans la tranche 0, entre 5 et 9,99 s dans la tranche 1, etc.
    # Les accolades { … for … if … } construisent un « set » (ensemble) : une collection SANS doublons.
    # Si 12 cris tombent dans la tranche 0, l'ensemble ne contient qu'une fois le nombre 0.
    # Le nombre d'éléments de l'ensemble (len) est donc exactement le nombre de tranches occupées.
    # « > » strict : même règle que BatDetect2 (un score affiché 0,3 n'atteint pas le seuil 0,3).
    # Pourquoi : BatDetect2 arrondit les scores à 3 décimales ; un score brut de 0,2996 arrive
    # ici sous la forme 0,300 alors qu'il était SOUS le seuil (voir docs/AUDIT.md, § 1, point 3).
    windows = {int(c["start_time"] // window) for c in calls if c["det_prob"] > threshold}
    return len(windows)


# Motifs de date dans les noms de fichiers :
#   AudioMoth           : 20240712_213000.WAV
#   BatDetect2 exemples : 20180627_215323-RHIFER-LR_0_0.5.wav
#   Wildlife Acoustics  : SITE_20240712_213000.wav
#   AudioMoth avec n° d'appareil / mode déclenché : 24F319036_20240712_213000T.WAV
#
# Une « expression régulière » (regex) est un petit langage pour décrire un motif de texte.
# Décomposition de celle-ci, morceau par morceau :
#   r"..."              la lettre r = chaîne « brute » : Python laisse les « \ » tels quels
#                       (indispensable en regex, où « \d » a un sens)
#   (?<![0-9A-Za-z])    « regard en arrière négatif » : le caractère JUSTE AVANT ne doit être ni un
#                       chiffre ni une lettre. Évite de lire une « date » au milieu d'un numéro
#                       d'appareil (« A20240712_213000 » est refusé). Ne consomme aucun caractère.
#   (20\d{2})           l'année : « 20 » suivi de 2 chiffres (\d = un chiffre, {2} = deux fois).
#                       Les parenthèses « capturent » le morceau pour le récupérer ensuite.
#   (\d{2})(\d{2})      le mois puis le jour, 2 chiffres chacun
#   [_-]?               un « _ » ou un « - », facultatif (le ? veut dire « 0 ou 1 fois »)
#   (\d{2})(\d{2})(\d{2})  heures, minutes, secondes
# Au total, 6 groupes capturés : année, mois, jour, heure, minute, seconde.
# re.compile() prépare la regex une seule fois, au chargement du module, au lieu de la relire à chaque appel.
_DATE_RE = re.compile(r"(?<![0-9A-Za-z])(20\d{2})(\d{2})(\d{2})[_-]?(\d{2})(\d{2})(\d{2})")


def parse_date(filename: str) -> Optional[str]:
    """
    Extrait une date ISO ('2024-07-12T21:30:00') du nom de fichier, ou None si rien trouvé.

    Attention : c'est l'heure ÉCRITE dans le nom, sans fuseau. Pour un AudioMoth, elle est en UTC
    par défaut. Quand le fichier contient l'heure avec son fuseau, metadata.py la lit à la place.
    """
    # search() cherche le motif n'importe où dans le nom. Renvoie None s'il est absent.
    m = _DATE_RE.search(filename)
    if not m:
        return None
    # Le motif a été trouvé, mais les chiffres peuvent former une date impossible
    # (ex. « 20241345 » = 45e jour du 13e mois). datetime(...) lève alors une ValueError :
    # on l'attrape avec try / except et on répond « pas de date » au lieu de planter.
    try:
        # m.groups() = les 6 morceaux capturés, sous forme de texte ("2024", "07", …).
        # On les convertit en nombres entiers, puis on les range dans 6 variables d'un coup.
        y, mo, d, h, mi, s = (int(x) for x in m.groups())
        # isoformat() écrit la date au format ISO 8601 : '2024-07-12T21:30:00'.
        # C'est ce texte qui est rangé dans la base.
        return datetime(y, mo, d, h, mi, s).isoformat()
    except ValueError:
        return None


# Heure de bascule d'une nuit à la suivante. Les chauves-souris sortent au crépuscule et rentrent
# à l'aube : tout ce qui est enregistré avant midi appartient à la nuit qui a commencé la veille.
NIGHT_CUTOFF_HOUR = 12


def night_of(recorded_at: Optional[str]) -> Optional[str]:
    """
    '2024-07-13T02:15:00' → '2024-07-12' (la nuit du 12 au 13). None si pas de date.

    Une nuit est désignée par le jour où elle COMMENCE (le soir).
    """
    # Pas d'heure connue : impossible de savoir à quelle nuit appartient le fichier.
    if not recorded_at:
        return None
    # Astuce : on recule l'heure de 12 h, puis on ne garde que le jour.
    #   13/07 02:15 - 12 h = 12/07 14:15 → nuit du 12
    #   12/07 22:00 - 12 h = 12/07 10:00 → nuit du 12
    #   13/07 12:00 - 12 h = 13/07 00:00 → nuit du 13
    # fromisoformat() fait l'inverse d'isoformat() : texte ISO → objet datetime.
    dt = datetime.fromisoformat(recorded_at)
    return (dt - timedelta(hours=NIGHT_CUTOFF_HOUR)).date().isoformat()


def phase_for(night: Optional[str], festival_start: Optional[str], festival_end: Optional[str]) -> Optional[str]:
    """
    Phase d'une nuit par rapport au festival. festival_start / festival_end = première et dernière
    NUIT du festival (AAAA-MM-JJ, bornes incluses). Renvoie None si une information manque.

    Valeurs renvoyées : "avant", "pendant" ou "apres" (sans accent : c'est la valeur stockée en base).
    """
    # Il faut les trois informations. Si l'une manque, on ne devine pas : on renvoie None.
    if not (night and festival_start and festival_end):
        return None
    # On convertit les trois textes en objets `date`, qu'on peut comparer avec < et <=.
    n, a, b = (date.fromisoformat(x) for x in (night, festival_start, festival_end))
    # Avant la première nuit du festival → « avant ».
    if n < a:
        return "avant"
    # Entre la première et la dernière nuit, bornes comprises → « pendant ».
    if n <= b:
        return "pendant"
    # Sinon, après la dernière nuit.
    return "apres"


def summarize_phase(recs: list[dict]) -> dict:
    """
    Agrège une liste d'enregistrements (déjà analysés) d'une même phase :
    - total contacts, total heures d'audio, contacts par heure
    - groupes détectés (union)

    Chaque enregistrement est un dict avec "n_contacts", "duration" (en secondes) et "groups" (liste).
    Les contacts par heure ne sont comparables que si l'enregistreur a tourné en continu, sur une
    plage horaire comparable d'une nuit à l'autre (voir docs/AUDIT.md, § 5).
    """
    # Total des contacts : sum() additionne les valeurs produites par la boucle entre parenthèses.
    total_contacts = sum(r["n_contacts"] for r in recs)
    # Total de la durée enregistrée, converti de secondes en heures (÷ 3600).
    # « r["duration"] or 0 » : si la durée est inconnue (None), on compte 0 au lieu de planter.
    total_hours = sum((r["duration"] or 0) for r in recs) / 3600.0
    # Groupes présents dans la phase : UNION des groupes de chaque fichier.
    # Un set évite les doublons (Myotis vu dans 3 fichiers ne compte qu'une fois).
    # r.get("groups", []) : liste vide si la clé n'existe pas.
    groups: set[str] = set()
    for r in recs:
        groups.update(r.get("groups", []))
    # Dictionnaire renvoyé à l'API (puis à l'interface en JSON) :
    # - hours arrondi à 6 décimales, pour gommer les poussières de calcul (0.30000000000000004)
    # - contacts_per_hour arrondi à 1 décimale ; None s'il n'y a aucune durée (on ne divise pas par 0)
    # - groups trié par ordre alphabétique, pour un affichage stable
    return {
        "n_recordings": len(recs),
        "hours": round(total_hours, 6),
        "contacts": total_contacts,
        "contacts_per_hour": round(total_contacts / total_hours, 1) if total_hours > 0 else None,
        "groups": sorted(groups),
        "n_groups": len(groups),
    }
