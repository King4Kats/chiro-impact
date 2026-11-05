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
# Note pour le lecteur du code
# ----------------------------
# Le texte ci-dessus (la « docstring » du module) sert AUSSI d'aide en ligne de commande :
# main() le passe à argparse, qui l'affiche avec « --help ». Il est donc écrit pour l'utilisateur.
#
# Ce script ne touche ni à la base ni aux fichiers du serveur : il parle à l'API HTTP, exactement
# comme le ferait l'interface (POST /api/campaigns, /sites, /recordings, puis GET /summary).
# Il n'utilise que la bibliothèque standard pour HTTP (urllib).
#
# Sommaire
# - requete()    : envoie une requête HTTP à l'API et renvoie la réponse JSON
# - deposer()    : envoie plusieurs WAV d'un coup (formulaire « multipart »)
# - fabriquer()  : fabrique un WAV d'une minute en collant des extraits réels dans du silence
# - main()       : crée campagne + sites, fabrique les fichiers, les dépose, attend l'analyse
import argparse
import json
import tempfile
import time
import urllib.request
import uuid
from pathlib import Path

import numpy as np
import soundfile as sf

# Dossier des 3 extraits de démonstration (vrais cris de chauves-souris).
# Path(__file__) = chemin de ce script ; .resolve() le rend absolu ;
# .parents[2] remonte de 2 dossiers (scripts → backend → racine du projet).
# L'opérateur « / » entre objets Path assemble un chemin, quel que soit le système (Windows ou Linux).
DEMO = Path(__file__).resolve().parents[2] / "docs" / "demo_wav"
# Les 3 extraits, rangés par code espèce (celui qui figure dans le nom du fichier).
EXTRAITS = {
    "MYOMYS": DEMO / "20170701_213954-MYOMYS-LR_0_0.5.wav",
    "EPTSER": DEMO / "20180530_213516-EPTSER-LR_0_0.5.wav",
    "RHIFER": DEMO / "20180627_215323-RHIFER-LR_0_0.5.wav",
}


def requete(base, method, path, body=None, raw=None, ctype=None):
    """
    Envoie une requête HTTP à l'API et renvoie la réponse décodée (JSON), ou None si elle est vide.

    - body : un objet Python, envoyé en JSON
    - raw  : des octets déjà prêts (utilisé pour le dépôt de fichiers)
    - ctype: type de contenu à annoncer (Content-Type)
    """
    # Corps de la requête : les octets bruts s'ils sont fournis, sinon le JSON de `body`,
    # sinon rien (cas d'un GET).
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    r = urllib.request.Request(base + path, data=data, method=method)
    # On annonce le type de contenu, pour que le serveur sache le lire.
    if ctype or body is not None:
        r.add_header("Content-Type", ctype or "application/json")
    # Envoi et lecture de la réponse. urlopen lève une erreur si le serveur répond 4xx ou 5xx :
    # le script s'arrête alors avec le message d'erreur.
    with urllib.request.urlopen(r) as resp:
        txt = resp.read()
        return json.loads(txt) if txt else None


def deposer(base, cid, site_id, fichiers):
    """
    Dépose une liste de WAV sur un site, en phase « auto », en un seul envoi.

    Un envoi de fichiers par formulaire HTTP utilise le format « multipart/form-data » :
    les champs se suivent, séparés par une « frontière » (boundary), une chaîne qui ne doit
    apparaître nulle part ailleurs. Ici on la tire au hasard (uuid4). Chaque partie a un petit
    en-tête (Content-Disposition), une ligne vide (\r\n\r\n), puis sa valeur.
    """
    bnd = uuid.uuid4().hex
    # Les deux champs texte du formulaire : le site et la phase (« auto »).
    parts = [f'--{bnd}\r\nContent-Disposition: form-data; name="site_id"\r\n\r\n{site_id}\r\n'.encode(),
             f'--{bnd}\r\nContent-Disposition: form-data; name="phase"\r\n\r\nauto\r\n'.encode()]
    # Une partie « files » par WAV : en-tête avec le nom du fichier, puis son contenu brut.
    for f in fichiers:
        parts += [f'--{bnd}\r\nContent-Disposition: form-data; name="files"; filename="{f.name}"\r\nContent-Type: audio/wav\r\n\r\n'.encode(),
                  f.read_bytes(), b"\r\n"]
    # Frontière finale (avec « -- » à la fin) : signale la fin du formulaire.
    parts.append(f"--{bnd}--\r\n".encode())
    return requete(base, "POST", f"/campaigns/{cid}/recordings", raw=b"".join(parts),
                   ctype=f"multipart/form-data; boundary={bnd}")


def fabriquer(dossier: Path, nom: str, duree: float, passages: list[tuple[float, str]]) -> Path:
    """
    WAV de `duree` secondes, silencieux sauf les extraits placés aux instants donnés (384 kHz).

    `passages` est une liste de couples (instant en secondes, code de l'extrait), ex. [(1, "MYOMYS")].
    """
    # Un tableau numpy de zéros = du silence. Sa longueur = durée × fréquence d'échantillonnage.
    sr = 384_000
    y = np.zeros(int(duree * sr), dtype="float32")
    # On colle chaque extrait à son instant.
    for t, code in passages:
        x, xsr = sf.read(EXTRAITS[code], dtype="float32")
        # L'extrait doit avoir la même fréquence d'échantillonnage que le fichier fabriqué,
        # sinon il serait rejoué trop vite ou trop lentement.
        if xsr != sr:  # MYOMYS est à 500 kHz : on le ramène à 384 kHz
            import librosa
            x = librosa.resample(x, orig_sr=xsr, target_sr=sr)
        # i = position (en échantillons) où commence l'extrait.
        # x[: len(y) - i] coupe l'extrait s'il dépasse la fin du fichier.
        i = int(t * sr)
        y[i:i + len(x)] = x[: len(y) - i]
    # Écriture du WAV sur le disque (dossier créé si besoin).
    dossier.mkdir(exist_ok=True)
    p = dossier / nom
    sf.write(p, y, sr)
    return p


def main():
    """Crée la campagne de démonstration, dépose les fichiers, attend l'analyse et affiche la synthèse."""
    # Lecture de l'option --url. RawDescriptionHelpFormatter garde les retours à la ligne
    # de la docstring dans l'aide. On ajoute « /api » : toutes les routes de l'API commencent ainsi.
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="http://localhost:8000")
    base = ap.parse_args().url.rstrip("/") + "/api"

    # Création de la campagne (dates du festival) puis des deux sites, dont le témoin.
    camp = requete(base, "POST", "/campaigns", {
        "name": "Démo festival", "description": "Campagne fabriquée par scripts/creer_demo.py",
        "festival_start": "2024-07-12", "festival_end": "2024-07-14",
    })
    scene = requete(base, "POST", f"/campaigns/{camp['id']}/sites", {"name": "Lisière scène"})
    temoin = requete(base, "POST", f"/campaigns/{camp['id']}/sites", {"name": "Bois témoin", "is_control": True})

    # Préparation des fichiers dans un dossier temporaire du système.
    # - riche : 15 passages par minute, aux secondes 1, 5, 9, …, 57, en alternant les 3 extraits
    #   (zip associe chaque instant à un code ; la liste des codes répétée 5 fois en donne 15) ;
    # - pauvre : un passage sur 4 de « riche » ([::4] = un élément sur 4), soit 4 par minute.
    tmp = Path(tempfile.mkdtemp(prefix="chiro-demo-"))
    riche = [(t, c) for t, c in zip(range(1, 58, 4), ["MYOMYS", "EPTSER", "RHIFER"] * 5)]  # 15 passages / min
    pauvre = riche[::4]                                                                 # 4 passages / min
    # Nuits simulées et phase attendue (la phase réelle sera calculée par le serveur, mode « Auto »).
    nuits = {"2024-07-10": "avant", "2024-07-11": "avant", "2024-07-12": "pendant",
             "2024-07-13": "pendant", "2024-07-16": "apres", "2024-07-17": "apres"}
    fichiers = {scene["id"]: [], temoin["id"]: []}
    for nuit, phase in nuits.items():
        jour = nuit.replace("-", "")
        # 1 minute à 22 h 30, 1 minute à 1 h du matin (date du lendemain : même nuit)
        # Calcul du lendemain avec les dates numpy : datetime64 = une date, timedelta64(1, "D") = 1 jour.
        lendemain = (np.datetime64(nuit) + np.timedelta64(1, "D")).astype(str).replace("-", "")
        for stamp in (f"{jour}_223000", f"{lendemain}_010000"):
            # Un dossier par site : les enregistreurs donnent les mêmes noms de fichiers
            # La lisière « scène » reçoit le fichier pauvre pendant le festival, riche sinon ;
            # le témoin reçoit toujours le fichier riche.
            fichiers[scene["id"]].append(fabriquer(tmp / "scene", f"{stamp}.WAV", 60, pauvre if phase == "pendant" else riche))
            fichiers[temoin["id"]].append(fabriquer(tmp / "temoin", f"{stamp}.WAV", 60, riche))

    # Dépôt : un envoi par site, avec tous ses fichiers.
    for site_id, fs in fichiers.items():
        res = deposer(base, camp["id"], site_id, fs)
        print(f"site {site_id} : {len(res['created'])} fichier(s) déposé(s), {len(res['skipped'])} ignoré(s)")

    # Attente de la fin des analyses : on interroge la synthèse toutes les 2 s tant que
    # « pending » (nombre de fichiers en attente) n'est pas 0. Un point s'affiche à chaque tour.
    # flush=True force l'affichage immédiat (sinon Python peut garder le texte en mémoire).
    print("Analyse en cours…", end="", flush=True)
    t = time.time()
    while requete(base, "GET", f"/campaigns/{camp['id']}/summary")["pending"]:
        time.sleep(2)
        print(".", end="", flush=True)
    # Affichage du résultat : contacts par heure de chaque site, phase par phase.
    # {nom:<15} aligne le nom à gauche sur 15 caractères, pour un tableau lisible.
    s = requete(base, "GET", f"/campaigns/{camp['id']}/summary")
    print(f" terminé en {time.time() - t:.0f} s")
    for site in s["sites"]:
        ligne = " · ".join(f"{p} {v['contacts_per_hour']} c/h" for p, v in site["phases"].items())
        print(f"  {site['site']['name']:<15} {ligne}")
    # Adresse de la campagne dans l'interface : base[:-4] retire le « /api » final.
    print(f"Ouvrir : {base[:-4]}/campaigns/{camp['id']}")


# Ce bloc ne s'exécute que si on lance le fichier directement (python creer_demo.py),
# pas si un autre fichier l'importe.
if __name__ == "__main__":
    main()
