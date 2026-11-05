"""
Tests de compare.py : les calculs de la page « Comparer ».

On vérifie sur de petits exemples écrits à la main (pas besoin de vrais fichiers audio) :
- la plage horaire d'une nuit (« 21 h → 6 h » passe bien minuit) ;
- les heures d'écoute comptées dans la plage ;
- le seuil strict, la largeur des tranches, le tri des cris dans ou hors de la plage, les groupes.
"""
from datetime import datetime

from app.compare import night_window, overlap_hours, site_nights


# La nuit du 12 juillet de 21 h à 6 h finit le 13 au matin : une heure avant midi = lendemain.
def test_plage_horaire_passe_minuit():
    a, b = night_window("2024-07-12", 21, 6)
    assert a == datetime(2024, 7, 12, 21) and b == datetime(2024, 7, 13, 6)
    # Les deux bornes après minuit : toutes les deux le lendemain
    a, b = night_window("2024-07-12", 0.5, 2)
    assert a == datetime(2024, 7, 13, 0, 30) and b == datetime(2024, 7, 13, 2)


# Heures communes entre un enregistrement et la plage : début, fin, dedans, dehors.
def test_heures_dans_la_plage():
    w = (datetime(2024, 7, 12, 22), datetime(2024, 7, 13, 2))
    assert overlap_hours(datetime(2024, 7, 12, 21), 2 * 3600, *w) == 1.0      # 21 h-23 h : 1 h dedans
    assert overlap_hours(datetime(2024, 7, 12, 23), 600, *w) == 600 / 3600    # entièrement dedans
    assert overlap_hours(datetime(2024, 7, 13, 3), 3600, *w) == 0.0           # entièrement après


REC = {"id": 1, "site_id": 7, "phase": "avant", "night": "2024-07-12",
       "recorded_at": "2024-07-12T23:59:00", "duration": 120.0}   # de 23 h 59 à 0 h 01
CALLS = [
    {"recording_id": 1, "start_time": 1.0, "grp": "Myotis", "det_prob": 0.9},        # 23:59:01, tranche 0
    {"recording_id": 1, "start_time": 2.0, "grp": "Pipistrelles", "det_prob": 0.5},  # tranche 0
    {"recording_id": 1, "start_time": 70.0, "grp": "Pipistrelles", "det_prob": 0.3}, # pile au seuil : exclu
    {"recording_id": 1, "start_time": 90.0, "grp": "Pipistrelles", "det_prob": 0.8}, # 0:00:30, tranche 18
]


# Réglages par défaut : seuil strict (0,3 exclu), tranches de 5 s, contacts par groupe.
def test_ligne_site_nuit():
    row = site_nights([REC], CALLS, threshold=0.3, window=5)["rows"][0]
    assert (row["site_id"], row["night"], row["files"]) == (7, "2024-07-12", 1)
    assert row["calls"] == 3 and row["contacts"] == 2
    assert row["by_group"] == {"Myotis": 1, "Pipistrelles": 2}
    assert row["calls_by_group"] == {"Myotis": 1, "Pipistrelles": 2}
    assert row["hours"] == round(120 / 3600, 6)


# Largeur des tranches : en 60 s, tranche 0 (cris à 1 s et 2 s) et tranche 1 (cri à 90 s) → 2 contacts.
# En 1 s, les trois cris gardés sont chacun dans leur tranche → 3 contacts.
def test_largeur_des_tranches():
    assert site_nights([REC], CALLS, 0.3, 60)["rows"][0]["contacts"] == 2
    assert site_nights([REC], CALLS, 0.3, 1)["rows"][0]["contacts"] == 3


# Plage 0 h → 6 h : seule la partie après minuit compte (1 min d'écoute, 1 cri).
def test_plage_horaire_filtre_effort_et_cris():
    row = site_nights([REC], CALLS, 0.3, 5, hours=(0, 6))["rows"][0]
    assert row["hours"] == round(60 / 3600, 6)
    assert row["calls"] == 1 and row["contacts"] == 1


# Un fichier sans date ne peut pas être placé dans la plage horaire : il est écarté et compté.
def test_fichier_sans_date_ecarte_avec_plage():
    sans_date = {**REC, "id": 2, "recorded_at": None, "night": None}
    out = site_nights([REC, sans_date], CALLS, 0.3, 5, hours=(21, 6))
    assert out["excluded_no_date"] == 1 and len(out["rows"]) == 1
    # Sans plage horaire, il est gardé (ligne « sans nuit »)
    assert len(site_nights([REC, sans_date], CALLS, 0.3, 5)["rows"]) == 2


# Un fichier entièrement hors de la plage horaire n'est pas compté (ni ses heures, ni comme fichier).
def test_fichier_hors_plage_ignore():
    tot = {**REC, "id": 3, "recorded_at": "2024-07-12T19:00:00"}   # 19 h → 19 h 02 : avant 21 h
    row = site_nights([REC, tot], CALLS, 0.3, 5, hours=(21, 6))["rows"][0]
    assert row["files"] == 1
