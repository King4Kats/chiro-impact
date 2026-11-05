"""
Détection BatDetect2 sur de vrais cris de chauves-souris.

On vérifie surtout que notre lecture par blocs (mémoire constante, indispensable pour une nuit entière)
donne EXACTEMENT les mêmes cris que la fonction d'origine de BatDetect2.

Ces tests visent app/detection.py. Ils font vraiment tourner le modèle : ils sont plus lents
que ceux de test_analysis.py. Les fichiers fabriqués (long_wav, very_long_wav…) viennent des
fixtures de conftest.py.

Sommaire
- reference() / assert_meme_resultat() : outils de comparaison avec BatDetect2
- test_extraits_de_demo (×3)          : nombre de cris et groupe sur les 3 extraits réels
- test_champs_d_un_cri                : format d'un cri renvoyé
- test_fichier_long_identique_…       : fichier de 12 s
- test_plusieurs_blocs_et_progression : fichier de 150 s, plusieurs blocs de lecture
- test_stereo_lit_la_premiere_voie    : fichier stéréo
- test_audio_info                     : durée et fréquence
- test_seuil_de_comptage_…            : seuil strict et arrondi des scores
- test_rien_au_dessus_de_la_…         : limite de Nyquist d'un fichier à 192 kHz
"""
import pytest
from batdetect2 import api

from app import detection
from conftest import EPTSER, MYOMYS, RHIFER


def reference(path):
    """Résultat de la fonction officielle de BatDetect2 (qui charge tout le fichier)."""
    # Même configuration que notre code (detection._config, seuil 0,1), pour comparer à égalité.
    # La réponse est un dict imbriqué : les cris sont dans ["pred_dict"]["annotation"].
    # On les trie par heure de début, comme detection.detect().
    ann = api.process_file(str(path), config=detection._config)["pred_dict"]["annotation"]
    return sorted(ann, key=lambda a: a["start_time"])


def assert_meme_resultat(mine, ref):
    """
    Vérifie que nos cris (`mine`) et ceux de BatDetect2 (`ref`) sont les mêmes, un par un.

    pytest.approx(valeur, abs=1e-3) accepte un écart d'au plus 0,001 : on compare des nombres
    à virgule, qui peuvent différer d'un cheveu selon l'ordre des calculs.
    """
    # Même nombre de cris…
    assert len(mine) == len(ref)
    # … et, cri par cri (zip les parcourt ensemble), mêmes temps, même espèce, même score.
    # Attention aux noms : notre champ s'appelle "species", celui de BatDetect2 "class".
    for m, r in zip(mine, ref):
        assert m["start_time"] == pytest.approx(r["start_time"], abs=1e-3)
        assert m["end_time"] == pytest.approx(r["end_time"], abs=1e-3)
        assert m["species"] == r["class"]
        assert m["det_prob"] == pytest.approx(r["det_prob"], abs=1e-3)


# Test « paramétré » : @pytest.mark.parametrize lance la même fonction 3 fois, une par ligne
# du tableau, en remplissant les paramètres path, n et groupe. pytest affiche 3 tests distincts.
#
# Pour chaque extrait réel, on vérifie :
# - le nombre de cris comptés au seuil 0,3 (n) ;
# - qu'aucun cri sous le seuil d'analyse (0,1) n'est gardé ;
# - que le groupe le plus fréquent est le bon (l'espèce est connue grâce au nom du fichier) ;
# - que tout est identique à BatDetect2.
# Empêche une régression du modèle, du découpage ou de la table des groupes.
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
    # max(set(groupes), key=groupes.count) = le groupe qui revient le plus souvent dans la liste.
    groupes = [c["grp"] for c in calls if detection.counted(c["det_prob"])]
    assert max(set(groupes), key=groupes.count) == groupe
    assert_meme_resultat(calls, reference(path))


# Vérifie le format exact d'un cri renvoyé (les colonnes attendues par la table `calls`)
# et que ses valeurs sont plausibles : temps dans l'extrait de 0,5 s, fréquences entre 10 kHz
# et la limite de Nyquist du fichier (384 kHz / 2), score entre 0,1 et 1.
# Empêche qu'un champ soit oublié ou renommé sans que la base et l'interface suivent.
def test_champs_d_un_cri():
    c = detection.detect(str(RHIFER))[0]
    assert set(c) == {"start_time", "end_time", "low_freq", "high_freq", "species", "grp", "det_prob", "class_prob"}
    assert 0 <= c["start_time"] < c["end_time"] <= 0.6
    assert 10_000 < c["low_freq"] < c["high_freq"] <= 192_000   # 384 kHz / 2
    assert detection.ANALYSIS_THRESHOLD <= c["det_prob"] <= 1
    # (« a < b < c » en Python se lit « a < b ET b < c ».)


# Vérifie, sur un fichier de 12 s (4 tranches de 3 s), que le découpage en tranches donne les
# mêmes cris que BatDetect2, et que les cris de la fin du fichier sont horodatés au bon endroit.
# Empêche un décalage de temps entre tranches.
def test_fichier_long_identique_a_batdetect2(long_wav):
    calls = detection.detect(str(long_wav))
    assert_meme_resultat(calls, reference(long_wav))
    assert calls[-1]["start_time"] > 10   # des cris jusqu'à la fin du fichier, horodatés au bon endroit


# Vérifie la lecture par blocs de 60 s sur un fichier de 150 s : mêmes cris que BatDetect2,
# temps recalés d'un bloc à l'autre, et progression signalée 3 fois, croissante, jusqu'à 100 %.
# Empêche que les cris du 2e ou 3e bloc soient placés au début du fichier.
def test_plusieurs_blocs_et_progression(very_long_wav):
    """150 s = 3 blocs de 60 s : les cris sont bien recalés dans le temps et la progression atteint 100 %."""
    # vus.append sert de callback : chaque appel on_progress(fraction) ajoute la fraction à la liste.
    vus = []
    calls = detection.detect(str(very_long_wav), on_progress=vus.append)
    assert_meme_resultat(calls, reference(very_long_wav))
    assert len(vus) == 3 and vus[-1] == 1.0 and vus == sorted(vus)
    # un extrait toutes les 10 s à partir de 2 s : des cris autour de 72 s et 142 s
    # (72 s est dans le 2e bloc, 142 s dans le 3e). any(...) = « au moins un élément vérifie… ».
    debuts = [c["start_time"] for c in calls]
    assert any(72 <= t <= 73 for t in debuts) and any(142 <= t <= 143 for t in debuts)


# Vérifie qu'un fichier stéréo est analysé sur sa PREMIÈRE voie (celle qui contient les cris
# dans le fichier de test) : on doit retrouver les 15 cris de MYOMYS.
def test_stereo_lit_la_premiere_voie(stereo_wav):
    assert len([c for c in detection.detect(str(stereo_wav)) if detection.counted(c["det_prob"])]) == 15


# Vérifie que audio_info lit la bonne durée (0,5 s) et la bonne fréquence d'échantillonnage
# (500 kHz pour cet extrait). Ces valeurs servent au dépôt (refus sous 96 kHz) et aux contacts par heure.
def test_audio_info():
    duree, sr = detection.audio_info(str(MYOMYS))
    assert duree == pytest.approx(0.5, abs=0.01) and sr == 500_000


# Vérifie que garder les cris dès 0,1 puis compter avec « > 0,3 » donne le MÊME nombre de cris que
# BatDetect2 réglé directement à 0,3. Empêche le retour du bug de l'arrondi (21 cris au lieu de 20
# sur l'extrait Sérotine, voir docs/AUDIT.md, § 1, point 3).
def test_seuil_de_comptage_identique_a_batdetect2():
    """Garder les cris dès 0,1 ne doit rien changer à ceux comptés au seuil 0,3 (régression : arrondi)."""
    for path in (MYOMYS, EPTSER, RHIFER):
        cfg = api.get_config(detection_threshold=detection.DEFAULT_THRESHOLD, quiet=True)
        ref = api.process_file(str(path), config=cfg)["pred_dict"]["annotation"]
        mine = [c for c in detection.detect(str(path)) if detection.counted(c["det_prob"])]
        # Le 2e argument d'assert est le message affiché en cas d'échec : ici le nom du fichier fautif.
        assert len(mine) == len(ref), path.name


# Vérifie qu'aucune détection ne dépasse la limite de Nyquist d'un fichier à 192 kHz (96 kHz),
# et que le résultat reste identique à BatDetect2. Empêche le retour des fausses détections
# produites par le passage à 256 kHz (ticket #22 de BatDetect2).
def test_rien_au_dessus_de_la_frequence_maximale_du_fichier(wav_dir):
    """
    Fichier à 192 kHz : il ne peut rien contenir au-dessus de 96 kHz. Comme `process_file`
    de BatDetect2, on jette toute détection plus haute (artefact du passage à 256 kHz, ticket #22).
    """
    import librosa
    import soundfile as sf
    # Fabrication du fichier de test : l'extrait MYOMYS (500 kHz) converti à 192 kHz.
    y, sr = sf.read(MYOMYS, dtype="float32")          # Murin à moustaches : cris jusqu'à ~115 kHz
    p = wav_dir / "myomys_192k.wav"
    sf.write(p, librosa.resample(y, orig_sr=sr, target_sr=192_000), 192_000)
    calls = detection.detect(str(p))
    # « calls and … » : la liste ne doit pas être vide (sinon all(...) serait vrai sans rien vérifier).
    assert calls and all(c["high_freq"] <= 96_000 for c in calls)
    assert_meme_resultat(calls, reference(p))
