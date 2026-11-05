"""
Crée une campagne de démonstration complète sur un serveur Chiro Impact qui tourne déjà.

Utile pour travailler l'interface sans avoir de vraies nuits d'enregistrement sous la main.
- Campagne « Démo festival » : festival les nuits du 12 au 14 juillet 2024
- 2 sites : « Lisière scène » (festival) et « Bois témoin » (témoin)
- Des WAV fabriqués à partir des 3 extraits de docs/demo_wav, datés dans le nom (format AudioMoth),
  répartis sur des nuits avant / pendant / après, déposés en phase « Auto ».
  Pendant le festival, la lisière a volontairement moins de cris : la synthèse montre une baisse.

Lancer (serveur démarré sur le port 8000) :
    cd backend
    .venv\\Scripts\\python scripts\\creer_demo.py
Option : --url http://autre-adresse:8000
"""
import argparse
import json
import tempfile
import time
import urllib.request
import uuid
from pathlib import Path

import numpy as np
import soundfile as sf

DEMO = Path(__file__).resolve().parents[2] / "docs" / "demo_wav"
EXTRAITS = {
    "MYOMYS": DEMO / "20170701_213954-MYOMYS-LR_0_0.5.wav",
    "EPTSER": DEMO / "20180530_213516-EPTSER-LR_0_0.5.wav",
    "RHIFER": DEMO / "20180627_215323-RHIFER-LR_0_0.5.wav",
}


def requete(base, method, path, body=None, raw=None, ctype=None):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    r = urllib.request.Request(base + path, data=data, method=method)
    if ctype or body is not None:
        r.add_header("Content-Type", ctype or "application/json")
    with urllib.request.urlopen(r) as resp:
        txt = resp.read()
        return json.loads(txt) if txt else None


def deposer(base, cid, site_id, fichiers):
    bnd = uuid.uuid4().hex
    parts = [f'--{bnd}\r\nContent-Disposition: form-data; name="site_id"\r\n\r\n{site_id}\r\n'.encode(),
             f'--{bnd}\r\nContent-Disposition: form-data; name="phase"\r\n\r\nauto\r\n'.encode()]
    for f in fichiers:
        parts += [f'--{bnd}\r\nContent-Disposition: form-data; name="files"; filename="{f.name}"\r\nContent-Type: audio/wav\r\n\r\n'.encode(),
                  f.read_bytes(), b"\r\n"]
    parts.append(f"--{bnd}--\r\n".encode())
    return requete(base, "POST", f"/campaigns/{cid}/recordings", raw=b"".join(parts),
                   ctype=f"multipart/form-data; boundary={bnd}")


def fabriquer(dossier: Path, nom: str, duree: float, passages: list[tuple[float, str]]) -> Path:
    """WAV de `duree` secondes, silencieux sauf les extraits placés aux instants donnés (384 kHz)."""
    sr = 384_000
    y = np.zeros(int(duree * sr), dtype="float32")
    for t, code in passages:
        x, xsr = sf.read(EXTRAITS[code], dtype="float32")
        if xsr != sr:  # MYOMYS est à 500 kHz : on le ramène à 384 kHz
            import librosa
            x = librosa.resample(x, orig_sr=xsr, target_sr=sr)
        i = int(t * sr)
        y[i:i + len(x)] = x[: len(y) - i]
    dossier.mkdir(exist_ok=True)
    p = dossier / nom
    sf.write(p, y, sr)
    return p


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="http://localhost:8000")
    base = ap.parse_args().url.rstrip("/") + "/api"

    camp = requete(base, "POST", "/campaigns", {
        "name": "Démo festival", "description": "Campagne fabriquée par scripts/creer_demo.py",
        "festival_start": "2024-07-12", "festival_end": "2024-07-14",
    })
    scene = requete(base, "POST", f"/campaigns/{camp['id']}/sites", {"name": "Lisière scène"})
    temoin = requete(base, "POST", f"/campaigns/{camp['id']}/sites", {"name": "Bois témoin", "is_control": True})

    tmp = Path(tempfile.mkdtemp(prefix="chiro-demo-"))
    riche = [(t, c) for t, c in zip(range(1, 58, 4), ["MYOMYS", "EPTSER", "RHIFER"] * 5)]  # 15 passages / min
    pauvre = riche[::4]                                                                 # 4 passages / min
    nuits = {"2024-07-10": "avant", "2024-07-11": "avant", "2024-07-12": "pendant",
             "2024-07-13": "pendant", "2024-07-16": "apres", "2024-07-17": "apres"}
    fichiers = {scene["id"]: [], temoin["id"]: []}
    for nuit, phase in nuits.items():
        jour = nuit.replace("-", "")
        # 1 minute à 22 h 30, 1 minute à 1 h du matin (date du lendemain : même nuit)
        lendemain = (np.datetime64(nuit) + np.timedelta64(1, "D")).astype(str).replace("-", "")
        for stamp in (f"{jour}_223000", f"{lendemain}_010000"):
            # Un dossier par site : les enregistreurs donnent les mêmes noms de fichiers
            fichiers[scene["id"]].append(fabriquer(tmp / "scene", f"{stamp}.WAV", 60, pauvre if phase == "pendant" else riche))
            fichiers[temoin["id"]].append(fabriquer(tmp / "temoin", f"{stamp}.WAV", 60, riche))

    for site_id, fs in fichiers.items():
        res = deposer(base, camp["id"], site_id, fs)
        print(f"site {site_id} : {len(res['created'])} fichier(s) déposé(s), {len(res['skipped'])} ignoré(s)")

    print("Analyse en cours…", end="", flush=True)
    t = time.time()
    while requete(base, "GET", f"/campaigns/{camp['id']}/summary")["pending"]:
        time.sleep(2)
        print(".", end="", flush=True)
    s = requete(base, "GET", f"/campaigns/{camp['id']}/summary")
    print(f" terminé en {time.time() - t:.0f} s")
    for site in s["sites"]:
        ligne = " · ".join(f"{p} {v['contacts_per_hour']} c/h" for p, v in site["phases"].items())
        print(f"  {site['site']['name']:<15} {ligne}")
    print(f"Ouvrir : {base[:-4]}/campaigns/{camp['id']}")


if __name__ == "__main__":
    main()
