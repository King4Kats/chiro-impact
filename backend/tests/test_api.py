"""
Parcours complet par l'API, comme le ferait l'interface :
campagne → sites (dont un témoin) → dépôt de WAV avant / pendant / après → analyse →
détail, spectrogramme, écoute ralentie → synthèse → corrections → suppressions.
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


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:  # « with » déclenche le démarrage (création de la base, ouvrier)
        yield c


def upload(client, cid, site_id, phase, *paths):
    files = [("files", (p.name, p.read_bytes(), "audio/wav")) for p in paths]
    r = client.post(f"/api/campaigns/{cid}/recordings", data={"site_id": site_id, "phase": phase}, files=files)
    assert r.status_code == 201, r.text
    return r.json()


def analysed(client, cid):
    """Attend la fin des analyses puis renvoie la liste des enregistrements."""
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
    return {"id": c["id"], "scene": scene["id"], "temoin": temoin["id"]}


def test_sante(client):
    assert client.get("/api/health").json()["status"] == "ok"
    assert client.get("/api/groups").json()["Myotis daubentonii"] == "Myotis"


def test_campagne_et_sites(client, campagne):
    c = client.get(f"/api/campaigns/{campagne['id']}").json()
    assert c["festival_start"] == "2024-07-12" and c["festival_end"] == "2024-07-14"
    # Le témoin est listé en dernier
    assert [s["name"] for s in c["sites"]] == ["Lisière scène", "Bois témoin"]
    assert c["sites"][1]["is_control"] == 1
    assert any(x["id"] == campagne["id"] for x in client.get("/api/campaigns").json())


def test_dates_incoherentes_refusees(client):
    r = client.post("/api/campaigns", json={"name": "x", "festival_start": "2024-07-14", "festival_end": "2024-07-12"})
    assert r.status_code == 400


def test_depot_manuel_et_analyse(client, campagne):
    cid = campagne["id"]
    upload(client, cid, campagne["scene"], "avant", MYOMYS)
    upload(client, cid, campagne["scene"], "pendant", RHIFER)
    out = upload(client, cid, campagne["temoin"], "apres", EPTSER)
    rec = out["created"][0]
    assert rec["phase"] == "apres" and rec["phase_source"] == "manuel"
    assert rec["samplerate"] == 384_000 and rec["recorded_at"] == "2018-05-30T21:35:16"

    recs = {r["filename"]: r for r in analysed(client, cid)}
    assert {r["status"] for r in recs.values()} == {"done"}
    assert recs[MYOMYS.name]["n_calls"] == 15 and recs[MYOMYS.name]["groups"] == ["Myotis", "Pipistrelles"]
    assert recs[RHIFER.name]["n_calls"] == 9 and recs[RHIFER.name]["groups"] == ["Rhinolophes"]
    assert recs[EPTSER.name]["n_calls"] == 20 and recs[EPTSER.name]["n_contacts"] == 1
    assert recs[EPTSER.name]["progress"] == 1


def test_doublon_ignore(client, campagne):
    out = upload(client, campagne["id"], campagne["scene"], "avant", MYOMYS)
    assert out["created"] == [] and out["skipped"][0]["reason"] == "déjà déposé sur ce site"


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


def test_phase_auto_depuis_le_nom_du_fichier(client, campagne, long_wav, very_long_wav):
    # long_wav : 12/07 22h30 → nuit du 12 = 1re nuit du festival → « pendant »
    # very_long_wav : 13/07 1h00 → nuit du 12 aussi (après minuit) → « pendant »
    out = upload(client, campagne["id"], campagne["scene"], "auto", long_wav, very_long_wav)
    assert [(r["phase"], r["phase_source"], r["night"]) for r in out["created"]] == [
        ("pendant", "auto", "2024-07-12"), ("pendant", "auto", "2024-07-12"),
    ]
    analysed(client, campagne["id"])


def test_phase_auto_impossible_sans_date(client, campagne, tmp_path):
    p = tmp_path / "sans_date.wav"
    p.write_bytes(MYOMYS.read_bytes())
    out = upload(client, campagne["id"], campagne["scene"], "auto", p)
    assert out["created"] == [] and "pas de date" in out["skipped"][0]["reason"]


def test_changer_les_dates_reclasse_les_fichiers_auto(client, campagne):
    cid = campagne["id"]
    # Le festival est décalé aux nuits du 20 au 22 : la nuit du 12 devient « avant »
    r = client.patch(f"/api/campaigns/{cid}", json={"festival_start": "2024-07-20", "festival_end": "2024-07-22"}).json()
    assert r["reclassified"] == 2
    phases = {x["filename"]: x["phase"] for x in client.get(f"/api/campaigns/{cid}/recordings").json()}
    assert phases["20240712_223000.WAV"] == "avant"
    assert phases[RHIFER.name] == "pendant"  # choisi à la main : ne bouge pas
    client.patch(f"/api/campaigns/{cid}", json={"festival_start": "2024-07-12", "festival_end": "2024-07-14"})


def test_corriger_phase_et_site(client, campagne):
    cid = campagne["id"]
    rec = next(r for r in client.get(f"/api/campaigns/{cid}/recordings").json() if r["filename"] == RHIFER.name)
    r = client.patch(f"/api/recordings/{rec['id']}", json={"phase": "apres", "site_id": campagne["temoin"]}).json()
    assert r["phase"] == "apres" and r["site_id"] == campagne["temoin"]
    # Pas de date de festival exploitable pour un fichier de 2018 → l'auto le classe « avant »
    assert client.patch(f"/api/recordings/{rec['id']}", json={"phase": "auto"}).json()["phase"] == "avant"
    client.patch(f"/api/recordings/{rec['id']}", json={"phase": "pendant", "site_id": campagne["scene"]})
    assert client.patch(f"/api/recordings/{rec['id']}", json={"phase": "nimporte"}).status_code == 422


def test_detail_d_un_enregistrement(client, campagne):
    rec = next(r for r in client.get(f"/api/campaigns/{campagne['id']}/recordings").json() if r["filename"] == MYOMYS.name)
    d = client.get(f"/api/recordings/{rec['id']}").json()
    assert d["site_name"] == "Lisière scène"
    # Tous les cris gardés (dès 0,1) sont renvoyés ; 15 atteignent le seuil de comptage 0,3
    assert len([c for c in d["calls"] if c["det_prob"] > 0.3]) == 15 == rec["n_calls"]
    assert all(c["det_prob"] >= 0.1 for c in d["calls"])
    assert [c["start_time"] for c in d["calls"]] == sorted(c["start_time"] for c in d["calls"])


def test_spectrogramme(client, campagne):
    recs = client.get(f"/api/campaigns/{campagne['id']}/recordings").json()
    rid = next(r["id"] for r in recs if r["filename"] == "20240712_223000.WAV")
    cri = client.get(f"/api/recordings/{rid}").json()["calls"][0]
    for q in ("", "?t0=5&t1=10", "?t0=10&t1=60", f"?t0=0&t1=5&min_prob=0.6&hl={cri['id']}", "?t0=500",
              "?w=343&h=260&dpr=3", "?w=1920&h=1000&dpr=2", "?w=10&h=10&dpr=9"):
        r = client.get(f"/api/recordings/{rid}/spectrogram.png{q}")
        assert r.status_code == 200 and r.content[:8] == b"\x89PNG\r\n\x1a\n", q
    # L'image est dessinée à la taille demandée × densité de l'écran (largeur, hauteur dans l'en-tête PNG)
    png = client.get(f"/api/recordings/{rid}/spectrogram.png?w=400&h=200&dpr=2").content
    assert struct.unpack(">II", png[16:24]) == (800, 400)


def test_ecoute_ralentie(client, campagne):
    rid = next(r["id"] for r in client.get(f"/api/campaigns/{campagne['id']}/recordings").json() if r["filename"] == RHIFER.name)
    r = client.get(f"/api/recordings/{rid}/audio.wav?t0=0&t1=0.5&slow=10")
    assert r.status_code == 200
    y, sr = sf.read(io.BytesIO(r.content))
    assert sr == 38_400 and abs(len(y) / sr - 5.0) < 0.05   # 0,5 s jouée 10 fois plus lentement = 5 s
    assert client.get(f"/api/recordings/{rid}/audio.wav?slow=0").status_code == 400


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
    nuits = {(n["site_id"], n["night"]) for n in s["nights"]}
    assert (campagne["scene"], "2024-07-12") in nuits


def test_reprise_apres_erreur(client, campagne):
    rid = client.get(f"/api/campaigns/{campagne['id']}/recordings").json()[0]["id"]
    assert client.post(f"/api/recordings/{rid}/reprocess").status_code == 202
    assert worker.wait_idle(120)
    assert client.get(f"/api/recordings/{rid}").json()["status"] == "done"


def test_fichier_disparu_du_disque(client, campagne):
    rec = next(r for r in client.get(f"/api/campaigns/{campagne['id']}/recordings").json() if r["filename"] == EPTSER.name)
    import pathlib
    pathlib.Path(rec["path"]).rename(rec["path"] + ".cache")
    try:
        assert client.get(f"/api/recordings/{rec['id']}/spectrogram.png").status_code == 410
    finally:
        pathlib.Path(rec["path"] + ".cache").rename(rec["path"])


def test_erreurs_404(client):
    assert client.get("/api/campaigns/9999").status_code == 404
    assert client.get("/api/recordings/9999").status_code == 404
    assert client.get("/api/recordings/9999/spectrogram.png").status_code == 404
    assert client.patch("/api/sites/9999", json={"name": "x"}).status_code == 404


def test_suppressions_effacent_les_wav(client, campagne):
    cid = campagne["id"]
    recs = client.get(f"/api/campaigns/{cid}/recordings").json()
    one = recs[0]
    assert client.delete(f"/api/recordings/{one['id']}").status_code == 204
    assert not __import__("pathlib").Path(one["path"]).exists()

    autres = [r["path"] for r in recs[1:]]
    assert client.delete(f"/api/campaigns/{cid}").status_code == 204
    assert client.get(f"/api/campaigns/{cid}").status_code == 404
    assert not any(__import__("pathlib").Path(p).exists() for p in autres)


def test_heure_lue_dans_le_fichier_et_mode_declenche(client, tmp_path):
    """Dépôt d'un faux fichier AudioMoth en UTC : heure convertie en heure française ; T.WAV refusé."""
    from test_metadata import faux_audiomoth
    c = client.post("/api/campaigns", json={"name": "Fuseaux", "festival_start": "2024-07-12", "festival_end": "2024-07-12"}).json()
    site = client.post(f"/api/campaigns/{c['id']}/sites", json={"name": "S"}).json()
    # 22:30 UTC le 12/07 = 00:30 le 13/07 en France → nuit du 12 → « pendant »
    p = faux_audiomoth(tmp_path / "20240712_223000.WAV", guano="Timestamp:2024-07-12T22:30:00Z\n")
    t = tmp_path / "20240712_223000T.WAV"
    t.write_bytes(p.read_bytes())
    out = upload(client, c["id"], site["id"], "auto", p, t)
    rec = out["created"][0]
    assert rec["recorded_at"] == "2024-07-13T00:30:00" and rec["time_source"] == "GUANO"
    assert rec["night"] == "2024-07-12" and rec["phase"] == "pendant"
    assert "mode déclenché" in out["skipped"][0]["reason"]
    worker.wait_idle(60)
    client.delete(f"/api/campaigns/{c['id']}")
