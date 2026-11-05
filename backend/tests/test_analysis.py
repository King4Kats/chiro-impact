"""Calculs « métier » : contacts de 5 s, dates dans les noms de fichiers, nuits et phases."""
from app import analysis as a


def cri(t, p=0.6):
    return {"start_time": t, "det_prob": p}


def test_contacts_une_tranche_de_5_s_compte_une_fois():
    # 12 cris entre 0 et 3 s = 1 seul contact
    assert a.contacts([cri(t / 4) for t in range(12)]) == 1


def test_contacts_tranches_differentes():
    # 1 s et 40 s = 2 contacts ; 4,9 s et 5,1 s tombent dans 2 tranches différentes
    assert a.contacts([cri(1), cri(40)]) == 2
    assert a.contacts([cri(4.9), cri(5.1)]) == 2


def test_contacts_ignore_les_cris_sous_le_seuil():
    assert a.contacts([cri(1, 0.2), cri(10, 0.29)]) == 0
    # Score affiché 0,3 = score brut ≤ 0,3 côté BatDetect2 : il ne compte pas
    assert a.contacts([cri(1, 0.2), cri(10, 0.3)]) == 0
    assert a.contacts([cri(1, 0.2), cri(10, 0.301)]) == 1


def test_parse_date_formats_courants():
    assert a.parse_date("20240712_213000.WAV") == "2024-07-12T21:30:00"            # AudioMoth
    assert a.parse_date("20180627_215323-RHIFER-LR_0_0.5.wav") == "2018-06-27T21:53:23"  # BatDetect2
    assert a.parse_date("LISIERE_20240712_213000.wav") == "2024-07-12T21:30:00"   # Wildlife Acoustics
    assert a.parse_date("enregistrement.wav") is None
    assert a.parse_date("20241345_990000.wav") is None  # date impossible


def test_nuit_apres_minuit_appartient_a_la_veille():
    assert a.night_of("2024-07-12T22:00:00") == "2024-07-12"
    assert a.night_of("2024-07-13T02:15:00") == "2024-07-12"
    assert a.night_of("2024-07-13T11:59:00") == "2024-07-12"
    assert a.night_of("2024-07-13T12:00:00") == "2024-07-13"
    assert a.night_of(None) is None


def test_phase_par_rapport_aux_dates_du_festival():
    debut, fin = "2024-07-12", "2024-07-14"   # festival les nuits du 12, 13 et 14
    assert a.phase_for("2024-07-10", debut, fin) == "avant"
    assert a.phase_for("2024-07-12", debut, fin) == "pendant"
    assert a.phase_for("2024-07-14", debut, fin) == "pendant"
    assert a.phase_for("2024-07-15", debut, fin) == "apres"
    assert a.phase_for("2024-07-12", None, fin) is None
    assert a.phase_for(None, debut, fin) is None


def test_synthese_d_une_phase():
    recs = [
        {"n_contacts": 30, "duration": 1800, "groups": ["Pipistrelles"]},
        {"n_contacts": 10, "duration": 1800, "groups": ["Myotis", "Pipistrelles"]},
    ]
    s = a.summarize_phase(recs)
    assert s["contacts"] == 40 and s["hours"] == 1 and s["contacts_per_hour"] == 40
    assert s["groups"] == ["Myotis", "Pipistrelles"] and s["n_groups"] == 2
    assert a.summarize_phase([])["contacts_per_hour"] is None


def test_chaque_espece_du_modele_a_un_groupe():
    """Régression : « Barbastellus barbastellus » (orthographe du modèle) tombait dans « Autre »."""
    from batdetect2 import api
    classes = api.get_config()["class_names"]
    assert len(classes) == 17
    sans_groupe = [c for c in classes if a.group_of(c) == "Autre"]
    assert sans_groupe == []
    assert a.group_of("Barbastellus barbastellus") == "Barbastelle"
    assert set(a.GROUPS) == set(classes)  # pas d'espèce inventée dans la table
