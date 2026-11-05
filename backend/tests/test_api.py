"""
Parcours complet par l'API, comme le ferait l'interface :
campagne → sites (dont un témoin) → dépôt de WAV avant / pendant / après → analyse →
détail, spectrogramme, écoute ralentie → synthèse → corrections → suppressions.

Ces tests visent app/main.py (les routes), et à travers lui toute la chaîne : base SQLite,
file d'analyse (worker.py), BatDetect2 (detection.py), calculs (analysis.py), images (spectro.py).

ATTENTION : les tests de ce fichier partagent la même campagne (fixture `campagne`, scope="module")
et s'exécutent dans l'ordre du fichier. Chacun part de l'état laissé par les précédents : par
exemple, test_synthese compte les fichiers déposés par les tests de dépôt plus haut.

Outils
- TestClient (FastAPI) : un faux navigateur qui appelle l'API directement, sans réseau.
  client.get / post / patch / delete renvoient une réponse avec .status_code et .json().
- Codes HTTP vérifiés : 200 OK, 201 créé, 202 accepté (travail lancé), 204 supprimé (pas de contenu),
  400 requête incorrecte, 404 introuvable, 410 disparu, 422 valeur refusée par la validation.

Sommaire
- Fixtures et aides : client, upload(), analysed(), campagne
- Campagne et sites ; dépôt, refus et doublons ; phase automatique et corrections
- Détail, spectrogramme, écoute ralentie ; synthèse ; reprise ; erreurs ; suppressions
- Heure lue dans le fichier et refus du mode déclenché
"""
import io
import struct

import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from app import worker
from app.config import UPLOAD_DIR
from app.main import app
from conftest import EPTSER, MYOMYS, RHIFER


# Fixture `client` : un TestClient partagé par tous les tests du fichier (scope="module").
# « yield » (au lieu de return) rend le client au test, puis reprend APRÈS les tests :
# la sortie du bloc « with » arrête proprement l'application.
@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:  # « with » déclenche le démarrage (création de la base, ouvrier)
        yield c


def upload(client, cid, site_id, phase, *paths):
    """
    Dépose un ou plusieurs fichiers sur un site, comme le formulaire de l'interface.
    `*paths` accepte un nombre quelconque de chemins. Vérifie la réponse 201 et renvoie son JSON
    ({"created": [...], "skipped": [...]}).
    """
    # Format attendu par le TestClient pour un envoi de fichiers :
    # (nom du champ, (nom du fichier, contenu, type)).
    files = [("files", (p.name, p.read_bytes(), "audio/wav")) for p in paths]
    r = client.post(f"/api/campaigns/{cid}/recordings", data={"site_id": site_id, "phase": phase}, files=files)
    # Le 2e argument d'assert (r.text) est affiché en cas d'échec : on voit l'erreur du serveur.
    assert r.status_code == 201, r.text
    return r.json()


def analysed(client, cid):
    """Attend la fin des analyses puis renvoie la liste des enregistrements."""
    # wait_idle(300) attend au plus 300 s que la file d'analyse soit vide ; renvoie False sinon.
    assert worker.wait_idle(300), "l'analyse n'a pas fini à temps"
    return client.get(f"/api/campaigns/{cid}/recordings").json()


@pytest.fixture(scope="module")
def campagne(client):
    """Une campagne « Festival test » : festival les nuits du 12 au 14 juillet 2024, 2 sites."""
    c = client.post("/api/campaigns", json={
        "name": "Festival test", "description": "tests automatiques",
        "festival_start": "2024-07-12", "festival_end": "2024-07-14",
    }).json()
    scene = client.post(f"/api/campaigns/{c['id']}/sites", json={"name": "Lisière scène"}).json()
    temoin = client.post(f"/api/campaigns/{c['id']}/sites", json={"name": "Bois témoin", "is_control": True}).json()
    # On ne garde que les identifiants : c'est tout ce dont les tests ont besoin.
    return {"id": c["id"], "scene": scene["id"], "temoin": temoin["id"]}


# Vérifie que l'API répond (route de santé) et sert la table espèce → groupe.
# Premier signal si l'application ne démarre plus.
def test_sante(client):
    assert client.get("/api/health").json()["status"] == "ok"
    assert client.get("/api/groups").json()["Myotis daubentonii"] == "Myotis"


# Vérifie que la campagne est enregistrée avec ses dates, que le site témoin est bien marqué
# et listé en dernier, et que la campagne apparaît dans la liste générale.
def test_campagne_et_sites(client, campagne):
    c = client.get(f"/api/campaigns/{campagne['id']}").json()
    assert c["festival_start"] == "2024-07-12" and c["festival_end"] == "2024-07-14"
    # Le témoin est listé en dernier
    assert [s["name"] for s in c["sites"]] == ["Lisière scène", "Bois témoin"]
    # SQLite n'a pas de vrai booléen : « vrai » est stocké et renvoyé sous la forme 1.
    assert c["sites"][1]["is_control"] == 1
    assert any(x["id"] == campagne["id"] for x in client.get("/api/campaigns").json())


# Vérifie qu'une campagne dont le festival finit avant de commencer est refusée (400).
# Empêche des phases incohérentes.
def test_dates_incoherentes_refusees(client):
    r = client.post("/api/campaigns", json={"name": "x", "festival_start": "2024-07-14", "festival_end": "2024-07-12"})
    assert r.status_code == 400


# Vérifie le dépôt avec phase choisie à la main et l'analyse complète des 3 extraits réels :
# phase et source « manuel » gardées, fréquence et date (lue dans le nom) correctes,
# nombre de cris comptés, groupes, contacts et progression à 100 %.
def test_depot_manuel_et_analyse(client, campagne):
    cid = campagne["id"]
    upload(client, cid, campagne["scene"], "avant", MYOMYS)
    upload(client, cid, campagne["scene"], "pendant", RHIFER)
    out = upload(client, cid, campagne["temoin"], "apres", EPTSER)
    rec = out["created"][0]
    assert rec["phase"] == "apres" and rec["phase_source"] == "manuel"
    assert rec["samplerate"] == 384_000 and rec["recorded_at"] == "2018-05-30T21:35:16"

    # Après analyse : on range les enregistrements dans un dict {nom de fichier: enregistrement}
    # pour les retrouver facilement.
    recs = {r["filename"]: r for r in analysed(client, cid)}
    assert {r["status"] for r in recs.values()} == {"done"}
    assert recs[MYOMYS.name]["n_calls"] == 15 and recs[MYOMYS.name]["groups"] == ["Myotis", "Pipistrelles"]
    assert recs[RHIFER.name]["n_calls"] == 9 and recs[RHIFER.name]["groups"] == ["Rhinolophes"]
    # 20 cris en 0,5 s = une seule tranche de 5 s = 1 contact.
    assert recs[EPTSER.name]["n_calls"] == 20 and recs[EPTSER.name]["n_contacts"] == 1
    assert recs[EPTSER.name]["progress"] == 1


# Vérifie qu'un même fichier déposé deux fois sur le même site est ignoré, avec une raison.
# Empêche de compter deux fois la même activité.
def test_doublon_ignore(client, campagne):
    out = upload(client, campagne["id"], campagne["scene"], "avant", MYOMYS)
    assert out["created"] == [] and out["skipped"][0]["reason"] == "déjà déposé sur ce site"


# Vérifie que les fichiers inutilisables sont refusés avec une raison claire
# (échantillonnage trop bas, WAV abîmé, pas un .wav) et ne restent pas sur le disque.
def test_fichiers_refuses_avec_raison(client, campagne, lowrate_wav, broken_wav, tmp_path):
    txt = tmp_path / "notes.txt"
    txt.write_text("pas du son")
    out = upload(client, campagne["id"], campagne["scene"], "avant", lowrate_wav, broken_wav, txt)
    raisons = {s["filename"]: s["reason"] for s in out["skipped"]}
    assert "trop bas" in raisons[lowrate_wav.name]
    assert "illisible" in raisons[broken_wav.name]
    assert raisons["notes.txt"] == "pas un fichier .wav"
    assert out["created"] == []
    # Les fichiers refusés ne restent pas sur le disque
    assert not any(lowrate_wav.name in p.name or broken_wav.name in p.name for p in UPLOAD_DIR.iterdir())


# Vérifie la phase « Auto » : date lue dans le nom, rattachement à la nuit (après minuit = veille)
# puis phase déduite des dates du festival. Attend la fin de l'analyse pour les tests suivants.
def test_phase_auto_depuis_le_nom_du_fichier(client, campagne, long_wav, very_long_wav):
    # long_wav : 12/07 22h30 → nuit du 12 = 1re nuit du festival → « pendant »
    # very_long_wav : 13/07 1h00 → nuit du 12 aussi (après minuit) → « pendant »
    out = upload(client, campagne["id"], campagne["scene"], "auto", long_wav, very_long_wav)
    assert [(r["phase"], r["phase_source"], r["night"]) for r in out["created"]] == [
        ("pendant", "auto", "2024-07-12"), ("pendant", "auto", "2024-07-12"),
    ]
    analysed(client, campagne["id"])


# Vérifie qu'en phase « Auto », un fichier sans date (ni dans le nom, ni dans le fichier) est refusé
# au lieu d'être classé au hasard.
def test_phase_auto_impossible_sans_date(client, campagne, tmp_path):
    p = tmp_path / "sans_date.wav"
    p.write_bytes(MYOMYS.read_bytes())
    out = upload(client, campagne["id"], campagne["scene"], "auto", p)
    assert out["created"] == [] and "pas de date" in out["skipped"][0]["reason"]


# Vérifie que changer les dates du festival reclasse les fichiers en phase « Auto »
# (ici 2 fichiers), mais pas ceux dont la phase a été choisie à la main.
# Remet les dates d'origine à la fin pour ne pas fausser les tests suivants.
def test_changer_les_dates_reclasse_les_fichiers_auto(client, campagne):
    cid = campagne["id"]
    # Le festival est décalé aux nuits du 20 au 22 : la nuit du 12 devient « avant »
    r = client.patch(f"/api/campaigns/{cid}", json={"festival_start": "2024-07-20", "festival_end": "2024-07-22"}).json()
    assert r["reclassified"] == 2
    phases = {x["filename"]: x["phase"] for x in client.get(f"/api/campaigns/{cid}/recordings").json()}
    assert phases["20240712_223000.WAV"] == "avant"
    assert phases[RHIFER.name] == "pendant"  # choisi à la main : ne bouge pas
    client.patch(f"/api/campaigns/{cid}", json={"festival_start": "2024-07-12", "festival_end": "2024-07-14"})


# Vérifie la correction d'un enregistrement : changer sa phase et son site, repasser en « auto »,
# et refuser une phase inconnue (422). Remet l'enregistrement dans son état d'origine.
def test_corriger_phase_et_site(client, campagne):
    cid = campagne["id"]
    # next(...) renvoie le premier élément qui correspond : ici l'enregistrement de RHIFER.
    rec = next(r for r in client.get(f"/api/campaigns/{cid}/recordings").json() if r["filename"] == RHIFER.name)
    r = client.patch(f"/api/recordings/{rec['id']}", json={"phase": "apres", "site_id": campagne["temoin"]}).json()
    assert r["phase"] == "apres" and r["site_id"] == campagne["temoin"]
    # Pas de date de festival exploitable pour un fichier de 2018 → l'auto le classe « avant »
    # (la nuit du 27/06/2018 est antérieure à la 1re nuit du festival, le 12/07/2024)
    assert client.patch(f"/api/recordings/{rec['id']}", json={"phase": "auto"}).json()["phase"] == "avant"
    client.patch(f"/api/recordings/{rec['id']}", json={"phase": "pendant", "site_id": campagne["scene"]})
    assert client.patch(f"/api/recordings/{rec['id']}", json={"phase": "nimporte"}).status_code == 422


# Vérifie le détail d'un enregistrement : nom du site, tous les cris gardés (dès 0,1) renvoyés,
# dont 15 au-dessus du seuil de comptage (égal à n_calls), triés par heure de début.
def test_detail_d_un_enregistrement(client, campagne):
    rec = next(r for r in client.get(f"/api/campaigns/{campagne['id']}/recordings").json() if r["filename"] == MYOMYS.name)
    d = client.get(f"/api/recordings/{rec['id']}").json()
    assert d["site_name"] == "Lisière scène"
    # Tous les cris gardés (dès 0,1) sont renvoyés ; 15 atteignent le seuil de comptage 0,3
    # (« 15 == rec["n_calls"] » : Python enchaîne les comparaisons, a == b == c)
    assert len([c for c in d["calls"] if c["det_prob"] > 0.3]) == 15 == rec["n_calls"]
    assert all(c["det_prob"] >= 0.1 for c in d["calls"])
    assert [c["start_time"] for c in d["calls"]] == sorted(c["start_time"] for c in d["calls"])


# Vérifie le spectrogramme avec de nombreux réglages (fenêtres de temps, seuil, cri surligné,
# fenêtre après la fin du fichier, tailles d'écran extrêmes) : toujours un PNG valide.
# Vérifie aussi la taille exacte de l'image et que le thème sombre donne une image différente.
def test_spectrogramme(client, campagne):
    recs = client.get(f"/api/campaigns/{campagne['id']}/recordings").json()
    rid = next(r["id"] for r in recs if r["filename"] == "20240712_223000.WAV")
    cri = client.get(f"/api/recordings/{rid}").json()["calls"][0]
    for q in ("", "?t0=5&t1=10", "?t0=10&t1=60", f"?t0=0&t1=5&min_prob=0.6&hl={cri['id']}", "?t0=500",
              "?w=343&h=260&dpr=3", "?w=1920&h=1000&dpr=2", "?w=10&h=10&dpr=9"):
        r = client.get(f"/api/recordings/{rid}/spectrogram.png{q}")
        # Tout fichier PNG commence par ces 8 octets (sa « signature »).
        assert r.status_code == 200 and r.content[:8] == b"\x89PNG\r\n\x1a\n", q
    # L'image est dessinée à la taille demandée × densité de l'écran (largeur, hauteur dans l'en-tête PNG)
    # Dans un PNG, la largeur et la hauteur sont aux octets 16 à 24, en entiers 4 octets
    # « gros-boutistes » (« >II » : octet de poids fort en premier, deux entiers non signés).
    png = client.get(f"/api/recordings/{rid}/spectrogram.png?w=400&h=200&dpr=2").content
    assert struct.unpack(">II", png[16:24]) == (800, 400)
    # Thème sombre de l'interface : même image, couleurs différentes
    sombre = client.get(f"/api/recordings/{rid}/spectrogram.png?w=400&h=200&dpr=2&theme=dark").content
    assert sombre[:8] == b"\x89PNG\r\n\x1a\n" and struct.unpack(">II", sombre[16:24]) == (800, 400)
    assert sombre != png


# Vérifie l'écoute ralentie : 0,5 s à 384 kHz ralenti 10 fois = un WAV déclaré à 38,4 kHz
# qui dure 5 s. Un facteur de ralentissement de 0 est refusé (400).
def test_ecoute_ralentie(client, campagne):
    rid = next(r["id"] for r in client.get(f"/api/campaigns/{campagne['id']}/recordings").json() if r["filename"] == RHIFER.name)
    r = client.get(f"/api/recordings/{rid}/audio.wav?t0=0&t1=0.5&slow=10")
    assert r.status_code == 200
    # io.BytesIO transforme les octets reçus en « faux fichier » que soundfile sait lire.
    y, sr = sf.read(io.BytesIO(r.content))
    assert sr == 38_400 and abs(len(y) / sr - 5.0) < 0.05   # 0,5 s jouée 10 fois plus lentement = 5 s
    assert client.get(f"/api/recordings/{rid}/audio.wav?slow=0").status_code == 400


# Vérifie la synthèse de la campagne : nombre de fichiers et contacts par phase, groupes,
# cris par groupe, séparation stricte témoin / festival (« control » / « impact »),
# contacts par heure d'un site et présence du découpage par nuit.
# Empêche le retour du bug où la synthèse mélangeait témoin et sites du festival
# (voir docs/AUDIT.md, § 1, point 7).
def test_synthese(client, campagne):
    s = client.get(f"/api/campaigns/{campagne['id']}/summary").json()
    assert s["pending"] == 0
    assert s["phases"]["avant"]["n_recordings"] == 1 and s["phases"]["avant"]["groups"] == ["Myotis", "Pipistrelles"]
    assert s["phases"]["pendant"]["n_recordings"] == 3            # RHIFER + 2 fichiers « auto »
    assert s["phases"]["pendant"]["contacts"] == 1 + 3 + 15       # 15 contacts dans le fichier de 150 s
    assert s["calls_by_group"]["pendant"]["Rhinolophes"] > 9
    # Le témoin n'est jamais mélangé aux sites du festival
    assert s["by_type"]["control"]["avant"]["n_recordings"] == 0
    assert s["by_type"]["control"]["apres"]["n_recordings"] == 1
    assert s["by_type"]["impact"]["apres"]["n_recordings"] == 0
    assert s["by_type"]["impact"]["pendant"]["n_recordings"] == 3
    temoin = next(x for x in s["sites"] if x["site"]["is_control"])
    assert temoin["phases"]["apres"]["contacts_per_hour"] == 7200.0  # 1 contact en 0,5 s
    # Ensemble des couples (site, nuit) présents dans le découpage par nuit.
    nuits = {(n["site_id"], n["night"]) for n in s["nights"]}
    assert (campagne["scene"], "2024-07-12") in nuits


# Vérifie qu'on peut relancer l'analyse d'un fichier (202 = travail accepté, fait en arrière-plan)
# et qu'il revient à l'état « done ».
def test_reprise_apres_erreur(client, campagne):
    rid = client.get(f"/api/campaigns/{campagne['id']}/recordings").json()[0]["id"]
    assert client.post(f"/api/recordings/{rid}/reprocess").status_code == 202
    assert worker.wait_idle(120)
    assert client.get(f"/api/recordings/{rid}").json()["status"] == "done"


# Vérifie que si le WAV a disparu du disque, le spectrogramme répond 410 (« disparu »)
# au lieu de planter. Le fichier est renommé le temps du test, puis remis en place
# (« finally » s'exécute même si l'assert échoue).
def test_fichier_disparu_du_disque(client, campagne):
    rec = next(r for r in client.get(f"/api/campaigns/{campagne['id']}/recordings").json() if r["filename"] == EPTSER.name)
    import pathlib
    pathlib.Path(rec["path"]).rename(rec["path"] + ".cache")
    try:
        assert client.get(f"/api/recordings/{rec['id']}/spectrogram.png").status_code == 410
    finally:
        pathlib.Path(rec["path"] + ".cache").rename(rec["path"])


# Vérifie que les identifiants inexistants donnent 404 sur les principales routes.
def test_erreurs_404(client):
    assert client.get("/api/campaigns/9999").status_code == 404
    assert client.get("/api/recordings/9999").status_code == 404
    assert client.get("/api/recordings/9999/spectrogram.png").status_code == 404
    assert client.patch("/api/sites/9999", json={"name": "x"}).status_code == 404


# Vérifie que supprimer un enregistrement efface aussi son WAV du disque, et que supprimer
# une campagne efface la campagne ET tous ses WAV. Empêche que le disque se remplisse
# de fichiers orphelins.
def test_suppressions_effacent_les_wav(client, campagne):
    cid = campagne["id"]
    recs = client.get(f"/api/campaigns/{cid}/recordings").json()
    one = recs[0]
    assert client.delete(f"/api/recordings/{one['id']}").status_code == 204
    # __import__("pathlib") importe le module pathlib à la volée, dans l'expression même.
    assert not __import__("pathlib").Path(one["path"]).exists()

    autres = [r["path"] for r in recs[1:]]
    assert client.delete(f"/api/campaigns/{cid}").status_code == 204
    assert client.get(f"/api/campaigns/{cid}").status_code == 404
    assert not any(__import__("pathlib").Path(p).exists() for p in autres)


# Vérifie, de bout en bout par l'API, deux règles de metadata.py :
# - l'heure UTC lue dans le bloc GUANO est convertie en heure française, et c'est elle (pas le nom
#   du fichier) qui décide de la nuit et de la phase ;
# - un fichier en mode déclenché (T.WAV) est refusé avec une raison.
# Crée sa propre campagne et la supprime à la fin.
def test_heure_lue_dans_le_fichier_et_mode_declenche(client, tmp_path):
    """Dépôt d'un faux fichier AudioMoth en UTC : heure convertie en heure française ; T.WAV refusé."""
    # On réutilise la fabrique de faux fichiers AudioMoth de test_metadata.py.
    from test_metadata import faux_audiomoth
    c = client.post("/api/campaigns", json={"name": "Fuseaux", "festival_start": "2024-07-12", "festival_end": "2024-07-12"}).json()
    site = client.post(f"/api/campaigns/{c['id']}/sites", json={"name": "S"}).json()
    # 22:30 UTC le 12/07 = 00:30 le 13/07 en France → nuit du 12 → « pendant »
    p = faux_audiomoth(tmp_path / "20240712_223000.WAV", guano="Timestamp:2024-07-12T22:30:00Z\n")
    # Copie du même fichier sous un nom en « T.WAV » (mode déclenché).
    t = tmp_path / "20240712_223000T.WAV"
    t.write_bytes(p.read_bytes())
    out = upload(client, c["id"], site["id"], "auto", p, t)
    rec = out["created"][0]
    assert rec["recorded_at"] == "2024-07-13T00:30:00" and rec["time_source"] == "GUANO"
    assert rec["night"] == "2024-07-12" and rec["phase"] == "pendant"
    assert "mode déclenché" in out["skipped"][0]["reason"]
    # Nettoyage : on attend la fin de l'analyse, puis on supprime la campagne de ce test.
    worker.wait_idle(60)
    client.delete(f"/api/campaigns/{c['id']}")


# Un nom envoyé explicitement à null doit être refusé proprement (422), pas faire planter le serveur (500).
def test_patch_nom_vide_refuse(client):
    cid = client.post("/api/campaigns", json={"name": "Test null"}).json()["id"]
    assert client.patch(f"/api/campaigns/{cid}", json={"name": None}).status_code == 422
    sid = client.post(f"/api/campaigns/{cid}/sites", json={"name": "S"}).json()["id"]
    assert client.patch(f"/api/sites/{sid}", json={"name": None}).status_code == 422
    assert client.patch(f"/api/sites/{sid}", json={"is_control": None}).status_code == 422
    assert client.patch(f"/api/sites/{sid}", json={"name": "S2"}).status_code == 200
    client.delete(f"/api/campaigns/{cid}")
