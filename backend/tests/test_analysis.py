"""
Calculs « métier » : contacts de 5 s, dates dans les noms de fichiers, nuits et phases.

Ces tests visent app/analysis.py. Ce sont des tests rapides : ni son, ni base de données,
seulement des fonctions de calcul appelées avec des valeurs choisies à la main.

Rappel : `assert condition` arrête le test (échec) si la condition est fausse.

Sommaire
- contacts()       : tranches de 5 s, seuil strict > 0,3
- parse_date()     : formats de noms de fichiers
- night_of()       : bascule à midi
- phase_for()      : avant / pendant / après
- summarize_phase(): totaux d'une phase
- GROUPS           : chaque espèce du modèle a un groupe
"""
# « as a » donne un nom court au module : a.contacts(...) au lieu de analysis.contacts(...).
from app import analysis as a


def cri(t, p=0.6):
    """Fabrique un faux cri : seulement les deux champs utilisés par contacts() (début, score)."""
    return {"start_time": t, "det_prob": p}


# Vérifie qu'une rafale de cris dans la même tranche de 5 s ne compte qu'UN contact.
# C'est la définition même du contact : sans cette règle, l'activité gonflerait avec le
# nombre de cris d'un seul passage.
def test_contacts_une_tranche_de_5_s_compte_une_fois():
    # 12 cris entre 0 et 3 s = 1 seul contact
    # (t / 4 pour t de 0 à 11 donne 0 ; 0,25 ; 0,5 ; … ; 2,75 s)
    assert a.contacts([cri(t / 4) for t in range(12)]) == 1


# Vérifie que des cris dans des tranches différentes comptent pour des contacts différents,
# y compris de part et d'autre d'une limite (4,9 s est dans la tranche 0-5, 5,1 s dans 5-10).
def test_contacts_tranches_differentes():
    # 1 s et 40 s = 2 contacts ; 4,9 s et 5,1 s tombent dans 2 tranches différentes
    assert a.contacts([cri(1), cri(40)]) == 2
    assert a.contacts([cri(4.9), cri(5.1)]) == 2


# Vérifie le seuil de score : les cris sous 0,3 ne comptent pas, et un score de 0,3 tout juste
# ne compte pas non plus (comparaison STRICTE). Empêche le retour du bug de l'arrondi :
# BatDetect2 arrondit les scores, un 0,2996 arrive en 0,3 et ne doit pas être compté.
def test_contacts_ignore_les_cris_sous_le_seuil():
    assert a.contacts([cri(1, 0.2), cri(10, 0.29)]) == 0
    # Score affiché 0,3 = score brut ≤ 0,3 côté BatDetect2 : il ne compte pas
    assert a.contacts([cri(1, 0.2), cri(10, 0.3)]) == 0
    assert a.contacts([cri(1, 0.2), cri(10, 0.301)]) == 1


# Vérifie la lecture de la date dans les formats de noms courants, et le refus d'un nom sans
# date ou d'une date impossible. Une mauvaise date = mauvaise nuit = mauvaise phase.
def test_parse_date_formats_courants():
    assert a.parse_date("20240712_213000.WAV") == "2024-07-12T21:30:00"            # AudioMoth
    assert a.parse_date("20180627_215323-RHIFER-LR_0_0.5.wav") == "2018-06-27T21:53:23"  # BatDetect2
    assert a.parse_date("LISIERE_20240712_213000.wav") == "2024-07-12T21:30:00"   # Wildlife Acoustics
    assert a.parse_date("enregistrement.wav") is None
    assert a.parse_date("20241345_990000.wav") is None  # date impossible


# Vérifie qu'un enregistrement fait après minuit (et jusqu'à 11 h 59) est rattaché à la nuit de
# la veille, et que la bascule se fait à midi pile. Sans cela, une même nuit serait coupée
# en deux et pourrait même changer de phase à minuit.
def test_nuit_apres_minuit_appartient_a_la_veille():
    assert a.night_of("2024-07-12T22:00:00") == "2024-07-12"
    assert a.night_of("2024-07-13T02:15:00") == "2024-07-12"
    assert a.night_of("2024-07-13T11:59:00") == "2024-07-12"
    assert a.night_of("2024-07-13T12:00:00") == "2024-07-13"
    assert a.night_of(None) is None


# Vérifie le classement avant / pendant / après, avec les deux bornes du festival INCLUSES,
# et qu'il ne devine rien quand une information manque (None).
def test_phase_par_rapport_aux_dates_du_festival():
    debut, fin = "2024-07-12", "2024-07-14"   # festival les nuits du 12, 13 et 14
    assert a.phase_for("2024-07-10", debut, fin) == "avant"
    assert a.phase_for("2024-07-12", debut, fin) == "pendant"
    assert a.phase_for("2024-07-14", debut, fin) == "pendant"
    assert a.phase_for("2024-07-15", debut, fin) == "apres"
    assert a.phase_for("2024-07-12", None, fin) is None
    assert a.phase_for(None, debut, fin) is None


# Vérifie les totaux d'une phase : 40 contacts en 2 × 30 min = 40 contacts par heure,
# union des groupes sans doublon et triée, et pas de division par zéro sur une phase vide.
def test_synthese_d_une_phase():
    recs = [
        {"n_contacts": 30, "duration": 1800, "groups": ["Pipistrelles"]},
        {"n_contacts": 10, "duration": 1800, "groups": ["Myotis", "Pipistrelles"]},
    ]
    s = a.summarize_phase(recs)
    assert s["contacts"] == 40 and s["hours"] == 1 and s["contacts_per_hour"] == 40
    assert s["groups"] == ["Myotis", "Pipistrelles"] and s["n_groups"] == 2
    assert a.summarize_phase([])["contacts_per_hour"] is None


# Vérifie que la table GROUPS correspond exactement aux 17 classes du modèle installé :
# aucune classe sans groupe, aucune espèce inventée dans la table.
# C'est le test qui aurait détecté le bug « Barbastelle » (voir docs/AUDIT.md, § 1, point 4).
def test_chaque_espece_du_modele_a_un_groupe():
    """Régression : « Barbastellus barbastellus » (orthographe du modèle) tombait dans « Autre »."""
    # Import placé dans le test : dans ce fichier, seul ce test a besoin de BatDetect2.
    from batdetect2 import api
    # Liste des noms de classes, lue dans la configuration du modèle (et non recopiée à la main).
    classes = api.get_config()["class_names"]
    assert len(classes) == 17
    sans_groupe = [c for c in classes if a.group_of(c) == "Autre"]
    assert sans_groupe == []
    assert a.group_of("Barbastellus barbastellus") == "Barbastelle"
    assert set(a.GROUPS) == set(classes)  # pas d'espèce inventée dans la table
