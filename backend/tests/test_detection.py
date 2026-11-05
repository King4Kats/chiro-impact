"""
Détection BatDetect2 sur de vrais cris de chauves-souris.

On vérifie surtout que notre lecture par blocs (mémoire constante, indispensable pour une nuit entière)
donne EXACTEMENT les mêmes cris que la fonction d'origine de BatDetect2.
"""
import pytest
from batdetect2 import api

from app import detection
from conftest import EPTSER, MYOMYS, RHIFER


def reference(path):
    """Résultat de la fonction officielle de BatDetect2 (qui charge tout le fichier)."""
    ann = api.process_file(str(path), config=detection._config)["pred_dict"]["annotation"]
    return sorted(ann, key=lambda a: a["start_time"])


def assert_meme_resultat(mine, ref):
    assert len(mine) == len(ref)
    for m, r in zip(mine, ref):
        assert m["start_time"] == pytest.approx(r["start_time"], abs=1e-3)
        assert m["end_time"] == pytest.approx(r["end_time"], abs=1e-3)
        assert m["species"] == r["class"]
        assert m["det_prob"] == pytest.approx(r["det_prob"], abs=1e-3)


@pytest.mark.parametrize("path,n,groupe", [
    (MYOMYS, 15, "Myotis"),
    (EPTSER, 20, "Noctules / Sérotines"),
    (RHIFER, 9, "Rhinolophes"),
])
def test_extraits_de_demo(path, n, groupe):
    calls = detection.detect(str(path))
    # n = cris au seuil de comptage (0,3) ; les cris faibles (0,1 à 0,3) sont gardés en plus
    assert len([c for c in calls if detection.counted(c["det_prob"])]) == n
    assert min(c["det_prob"] for c in calls) >= detection.ANALYSIS_THRESHOLD
    # Le groupe majoritaire est le bon (l'espèce exacte est dans le nom du fichier)
    groupes = [c["grp"] for c in calls if detection.counted(c["det_prob"])]
    assert max(set(groupes), key=groupes.count) == groupe
    assert_meme_resultat(calls, reference(path))


def test_champs_d_un_cri():
    c = detection.detect(str(RHIFER))[0]
    assert set(c) == {"start_time", "end_time", "low_freq", "high_freq", "species", "grp", "det_prob", "class_prob"}
    assert 0 <= c["start_time"] < c["end_time"] <= 0.6
    assert 10_000 < c["low_freq"] < c["high_freq"] <= 192_000   # 384 kHz / 2
    assert detection.ANALYSIS_THRESHOLD <= c["det_prob"] <= 1


def test_fichier_long_identique_a_batdetect2(long_wav):
    calls = detection.detect(str(long_wav))
    assert_meme_resultat(calls, reference(long_wav))
    assert calls[-1]["start_time"] > 10   # des cris jusqu'à la fin du fichier, horodatés au bon endroit


def test_plusieurs_blocs_et_progression(very_long_wav):
    """150 s = 3 blocs de 60 s : les cris sont bien recalés dans le temps et la progression atteint 100 %."""
    vus = []
    calls = detection.detect(str(very_long_wav), on_progress=vus.append)
    assert_meme_resultat(calls, reference(very_long_wav))
    assert len(vus) == 3 and vus[-1] == 1.0 and vus == sorted(vus)
    # un extrait toutes les 10 s à partir de 2 s : des cris autour de 72 s et 142 s
    debuts = [c["start_time"] for c in calls]
    assert any(72 <= t <= 73 for t in debuts) and any(142 <= t <= 143 for t in debuts)


def test_stereo_lit_la_premiere_voie(stereo_wav):
    assert len([c for c in detection.detect(str(stereo_wav)) if detection.counted(c["det_prob"])]) == 15


def test_audio_info():
    duree, sr = detection.audio_info(str(MYOMYS))
    assert duree == pytest.approx(0.5, abs=0.01) and sr == 500_000


def test_seuil_de_comptage_identique_a_batdetect2():
    """Garder les cris dès 0,1 ne doit rien changer à ceux comptés au seuil 0,3 (régression : arrondi)."""
    for path in (MYOMYS, EPTSER, RHIFER):
        cfg = api.get_config(detection_threshold=detection.DEFAULT_THRESHOLD, quiet=True)
        ref = api.process_file(str(path), config=cfg)["pred_dict"]["annotation"]
        mine = [c for c in detection.detect(str(path)) if detection.counted(c["det_prob"])]
        assert len(mine) == len(ref), path.name


def test_rien_au_dessus_de_la_frequence_maximale_du_fichier(wav_dir):
    """
    Fichier à 192 kHz : il ne peut rien contenir au-dessus de 96 kHz. Comme `process_file`
    de BatDetect2, on jette toute détection plus haute (artefact du passage à 256 kHz, ticket #22).
    """
    import librosa
    import soundfile as sf
    y, sr = sf.read(MYOMYS, dtype="float32")          # Murin à moustaches : cris jusqu'à ~115 kHz
    p = wav_dir / "myomys_192k.wav"
    sf.write(p, librosa.resample(y, orig_sr=sr, target_sr=192_000), 192_000)
    calls = detection.detect(str(p))
    assert calls and all(c["high_freq"] <= 96_000 for c in calls)
    assert_meme_resultat(calls, reference(p))
