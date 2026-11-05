"""
compare.py — calculs de la page « Comparer » (avant / pendant / après, festival / témoin).

Rôle du fichier
---------------
La synthèse (main.py, route /summary) utilise des réglages fixes : seuil 0,3, tranches de 5 s,
tout l'enregistrement. La page « Comparer » laisse l'utilisateur changer ces réglages pour voir
si la conclusion tient. Ce fichier refait donc le calcul à partir des cris enregistrés en base,
avec les réglages choisis, et renvoie une ligne par site × nuit.

Le serveur ne fait que la partie lourde (relire des milliers de cris). Le reste (choisir les sites,
les nuits, le groupe, la façon de faire la moyenne) se fait dans le navigateur, instantanément.

Qui l'utilise ?
- main.py : la route GET /api/campaigns/{id}/compare appelle site_nights().
- tests/test_compare.py : vérifie chaque fonction.

Sommaire
- night_window()  : transforme « de 21 h à 6 h » en deux dates précises pour une nuit donnée
- overlap_hours() : combien d'heures d'un enregistrement tombent dans cette plage
- site_nights()   : le calcul complet, une ligne par site × nuit

Notions utiles
- « Effort » d'écoute : le nombre d'heures réellement enregistrées. On divise toujours les contacts
  par l'effort, sinon un site enregistré 10 h paraîtrait plus actif qu'un site enregistré 2 h.
- Plage horaire : si l'enregistreur tourne plus longtemps certaines nuits, comparer la même plage
  (par exemple 22 h → 2 h) chaque nuit rend les nuits plus comparables (voir docs/AUDIT.md, § 5).
"""

from datetime import date, datetime, timedelta
from typing import Optional

from .analysis import NIGHT_CUTOFF_HOUR


def night_window(night: str, h_start: float, h_end: float) -> tuple[datetime, datetime]:
    """
    Plage horaire [début, fin) d'une nuit, en dates complètes.

    `night` est la date du SOIR (format AAAA-MM-JJ, comme dans analysis.night_of).
    Les heures sont des nombres décimaux (21.5 = 21 h 30). Une heure avant midi appartient
    au lendemain matin : pour la nuit du 12 juillet, « 2 h » veut dire le 13 juillet à 2 h.

    Exemple : night_window("2024-07-12", 21, 6) → (12/07 21:00, 13/07 06:00)
    """
    # Minuit du soir de la nuit (le 12 juillet à 0 h), point de départ des calculs
    base = datetime.combine(date.fromisoformat(night), datetime.min.time())

    # Une heure avant midi (NIGHT_CUTOFF_HOUR = 12) se situe le lendemain : on ajoute 24 h
    def at(h: float) -> datetime:
        return base + timedelta(hours=h if h >= NIGHT_CUTOFF_HOUR else h + 24)

    return at(h_start), at(h_end)


def overlap_hours(start: datetime, duration_s: float, w_start: datetime, w_end: datetime) -> float:
    """
    Nombre d'heures communes entre l'enregistrement [start, start + durée] et la plage [w_start, w_end].

    Le chevauchement de deux intervalles = de « le plus tardif des débuts » à « le plus tôt des fins ».
    S'il est négatif, les intervalles ne se touchent pas : on renvoie 0.
    """
    end = start + timedelta(seconds=duration_s)
    common = (min(end, w_end) - max(start, w_start)).total_seconds()
    return max(common, 0.0) / 3600.0


def site_nights(recordings: list[dict], calls: list[dict], threshold: float, window: float,
                hours: Optional[tuple[float, float]] = None) -> dict:
    """
    Recalcule l'activité par site × nuit avec les réglages choisis.

    Paramètres
    - recordings : enregistrements analysés (dict avec id, site_id, phase, night, recorded_at, duration)
    - calls      : leurs cris (dict avec recording_id, start_time, grp, det_prob)
    - threshold  : un cri compte si son score est STRICTEMENT au-dessus (même règle que BatDetect2)
    - window     : largeur d'une tranche de contact, en secondes (5 s par convention)
    - hours      : (heure de début, heure de fin) de la plage horaire, ou None pour tout garder

    Renvoie {"rows": [...], "excluded_no_date": n}. Chaque ligne :
    site_id, night, phase, files, hours (effort), contacts, calls,
    by_group (contacts par groupe) et calls_by_group (cris par groupe).
    """
    # 1. Ranger les cris par enregistrement, en ne gardant que ceux au-dessus du seuil.
    #    `setdefault(clé, [])` crée la liste vide la première fois qu'on voit cet enregistrement.
    by_rec: dict[int, list[dict]] = {}
    for c in calls:
        if c["det_prob"] > threshold:
            by_rec.setdefault(c["recording_id"], []).append(c)

    rows: dict[tuple, dict] = {}
    excluded = 0

    for r in recordings:
        start = datetime.fromisoformat(r["recorded_at"]) if r.get("recorded_at") else None
        duration = r.get("duration") or 0.0
        kept = by_rec.get(r["id"], [])

        # 2. Plage horaire : on ne garde que la partie de l'enregistrement qui tombe dedans,
        #    et seulement les cris situés dans cette partie. Sans date, impossible de savoir
        #    où se situe le fichier dans la nuit : il est mis de côté (et compté pour le dire).
        if hours is not None:
            if start is None or not r.get("night"):
                excluded += 1
                continue
            w_start, w_end = night_window(r["night"], *hours)
            effort = overlap_hours(start, duration, w_start, w_end)
            # Fichier entièrement hors de la plage : il n'apporte rien à cette nuit, on l'ignore
            if effort == 0:
                continue
            # Heure réelle d'un cri = début du fichier + sa position dans le fichier
            kept = [c for c in kept if w_start <= start + timedelta(seconds=c["start_time"]) < w_end]
        else:
            effort = duration / 3600.0

        # 3. Contacts : les tranches de `window` secondes qui contiennent au moins un cri.
        #    Un ensemble (set) ne garde chaque numéro de tranche qu'une fois.
        slots = {int(c["start_time"] // window) for c in kept}
        group_slots: dict[str, set[int]] = {}
        for c in kept:
            group_slots.setdefault(c["grp"] or "Autre", set()).add(int(c["start_time"] // window))

        # 4. Ajouter ce fichier à sa ligne site × nuit (plusieurs fichiers par nuit, c'est courant).
        key = (r["site_id"], r.get("night"), r.get("phase"))
        row = rows.setdefault(key, {
            "site_id": r["site_id"], "night": r.get("night"), "phase": r.get("phase"),
            "files": 0, "hours": 0.0, "contacts": 0, "calls": 0, "by_group": {}, "calls_by_group": {},
        })
        row["files"] += 1
        row["hours"] += effort
        row["contacts"] += len(slots)
        row["calls"] += len(kept)
        for g, s in group_slots.items():
            row["by_group"][g] = row["by_group"].get(g, 0) + len(s)
        for c in kept:
            g = c["grp"] or "Autre"
            row["calls_by_group"][g] = row["calls_by_group"].get(g, 0) + 1

    # 5. Arrondir les heures (affichage) et trier par site puis par nuit
    out = sorted(rows.values(), key=lambda x: (x["site_id"], x["night"] or ""))
    for row in out:
        row["hours"] = round(row["hours"], 6)
    return {"rows": out, "excluded_no_date": excluded}
