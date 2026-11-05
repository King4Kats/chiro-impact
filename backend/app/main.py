"""
Serveur API (FastAPI) : main.py. C'est le "cerveau" de l'appli :
- reçoit les WAV déposés par l'interface,
- les met dans la file d'analyse BatDetect2 (voir worker.py),
- calcule les indicateurs (contacts / heure, groupes) par phase, par site et par nuit,
- dessine les spectrogrammes et fabrique les extraits sonores ralentis,
- sert aussi l'interface web (dossier frontend/dist) pour qu'une seule commande lance tout.

VOCABULAIRE DE BASE
- API : un ensemble d'adresses (URL) que l'interface web appelle pour lire ou modifier des données.
  Les échanges se font en JSON (texte structuré, proche des dictionnaires Python).
- FastAPI : la bibliothèque Python qui reçoit ces appels et les dirige vers la bonne fonction.
- Route : une association « méthode HTTP + adresse → fonction Python ».
  Ex. `@app.get("/api/campaigns")` : quand le navigateur demande GET /api/campaigns,
  FastAPI appelle la fonction écrite juste en dessous et renvoie son résultat en JSON.
- Méthodes HTTP utilisées : GET (lire), POST (créer / déclencher), PATCH (modifier une partie),
  DELETE (supprimer).
- Codes HTTP de réponse : 200 OK, 201 créé, 202 accepté (traitement lancé plus tard),
  204 OK sans contenu, 400 requête incorrecte, 404 introuvable, 410 n'existe plus,
  422 données mal formées (renvoyé automatiquement par FastAPI quand le JSON ne correspond pas au schéma).

AVEC QUI IL PARLE
- config.py   : chemins (UPLOAD_DIR, FRONT_DIST) et échantillonnage minimum.
- db.py       : get_conn() pour la base, init_db() au démarrage.
- worker.py   : file d'analyse (enqueue, resume_pending, idle).
- detection.py: seuils de score, lecture des infos audio (durée, échantillonnage).
- analysis.py : groupes d'espèces, dates, nuits, phases, calcul des indicateurs.
- metadata.py : heure écrite dans le fichier, repérage des fichiers AudioMoth « déclenchés ».
- spectro.py  : image du spectrogramme et extrait audio ralenti.
- L'interface React (frontend/) appelle toutes les routes /api/...

SOMMAIRE
1. Démarrage (lifespan) et création de l'application
2. Schémas d'entrée (ce que l'interface envoie)
3. Fonctions utilitaires (helpers)
4. Routes : santé, campagnes, sites, enregistrements, spectrogramme / audio, synthèse
5. Service de l'interface web compilée

Lancer : uvicorn app.main:app --reload   (depuis le dossier backend/)
Doc interactive automatique : http://localhost:8000/docs
"""
import logging
import shutil
import uuid
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
# Outils de typage :
# - Optional[X] = « une valeur de type X, ou None (absente) ».
# - Literal["a", "b"] = « seulement l'une de ces valeurs exactes ».
from typing import Literal, Optional

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
# Pydantic vérifie automatiquement les données reçues (types, longueurs…) à partir d'une classe
from pydantic import BaseModel, Field

from . import analysis, compare, detection, metadata, spectro, worker
from .config import FRONT_DIST, MIN_SAMPLERATE, UPLOAD_DIR
from .db import get_conn, init_db

# Les trois phases du plan d'étude, dans l'ordre chronologique.
# C'est un tuple (liste non modifiable, entre parenthèses).
PHASES = ("avant", "pendant", "apres")
log = logging.getLogger("chiro")


# ---------- 1. Démarrage ----------
# Le « lifespan » (durée de vie) est le code que FastAPI exécute au démarrage et à l'arrêt du serveur.
# Tout ce qui est AVANT le `yield` s'exécute au démarrage, avant de répondre à la moindre requête.
# Le `yield` rend la main au serveur, qui tourne alors normalement. Ce qui serait après le `yield`
# s'exécuterait à l'arrêt (ici il n'y a rien).
# `@asynccontextmanager` est la version « async » de @contextmanager (voir db.py) : FastAPI l'exige pour le lifespan.
# `async def` déclare une fonction asynchrone, le style de fonction attendu ici par FastAPI.
@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Prépare la base (tables, colonnes) et le dossier de dépôt des WAV
    init_db()
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    # La table espèce → groupe peut évoluer (ex. correction de la Barbastelle) : on remet à jour
    # le groupe des cris déjà en base, sans relancer l'analyse.
    # `.items()` parcourt le dictionnaire GROUPS par paires (espèce, groupe).
    # `grp<>?` (= « différent de ») : on ne touche qu'aux lignes dont le groupe a changé.
    with get_conn() as c:
        for species, grp in analysis.GROUPS.items():
            c.execute("UPDATE calls SET grp=? WHERE species=? AND grp<>?", (grp, species, grp))
    n = worker.resume_pending()  # reprend les analyses interrompues par un arrêt du serveur
    if n:
        log.info("%s enregistrement(s) remis dans la file d'analyse", n)
    yield


# L'objet `app` est l'application FastAPI elle-même. Toutes les routes ci-dessous s'y accrochent
# grâce aux décorateurs @app.get, @app.post, etc. C'est cet objet que lance uvicorn (app.main:app).
app = FastAPI(title="Chiro Impact API", version="0.2.0", lifespan=lifespan)

# CORS : autorise le frontend Vite (port 5173) à appeler l'API (port 8000) pendant le développement.
# Par sécurité, un navigateur bloque par défaut les appels d'une page vers une autre adresse
# (ici un autre port). Ce « middleware » (code qui s'intercale devant toutes les routes) ajoute
# aux réponses les en-têtes qui lèvent ce blocage. "*" = toutes origines, méthodes et en-têtes acceptés.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ---------- 2. Schémas d'entrée (ce que l'interface envoie en JSON) ----------
# Chaque classe qui hérite de BaseModel décrit la forme attendue d'un JSON reçu.
# Quand une route prend un paramètre de ce type (ex. `body: CampaignIn`), FastAPI lit le JSON
# de la requête, vérifie chaque champ et le convertit. Si quelque chose ne va pas
# (champ obligatoire manquant, mauvais type, texte vide…), FastAPI répond tout seul 422.
# - `Field(min_length=1)` : texte d'au moins 1 caractère.
# - Un champ avec une valeur par défaut (`= ""`, `= None`) est facultatif.

# Création d'une campagne : le nom est obligatoire, le reste facultatif.
class CampaignIn(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""
    # Première et dernière NUIT du festival : servent à classer automatiquement les fichiers.
    # Le type `date` fait que Pydantic convertit le texte "2027-07-15" en vraie date (et refuse "n'importe quoi").
    festival_start: Optional[date] = None
    festival_end: Optional[date] = None


# Modification d'une campagne (PATCH) : tous les champs sont facultatifs,
# on n'envoie que ceux qu'on veut changer.
class CampaignPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1)
    description: Optional[str] = None
    festival_start: Optional[date] = None
    festival_end: Optional[date] = None


# Création d'un site d'enregistrement. is_control = True pour le site témoin (hors festival).
class SiteIn(BaseModel):
    name: str = Field(min_length=1)
    is_control: bool = False
    notes: str = ""


# Modification d'un site : mêmes champs, tous facultatifs.
class SitePatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1)
    is_control: Optional[bool] = None
    notes: Optional[str] = None


# Correction d'un enregistrement déjà déposé : changer sa phase et/ou son site.
class RecordingPatch(BaseModel):
    # 'auto' = recalculer depuis la date du fichier et les dates du festival
    phase: Optional[Literal["avant", "pendant", "apres", "auto"]] = None
    site_id: Optional[int] = None


# ---------- 3. Helpers (petites fonctions réutilisées par les routes) ----------
def _row(r) -> Optional[dict]:
    """Convertit une ligne SQLite en dictionnaire Python (que FastAPI sait envoyer en JSON). None reste None."""
    # Écriture « valeur_si_vrai if condition else valeur_si_faux » : un if/else sur une ligne
    return dict(r) if r is not None else None


def _campaign_or_404(c, cid: int):
    """Renvoie la campagne `cid`, ou arrête la requête avec une erreur 404 si elle n'existe pas."""
    # Requête paramétrée : le `?` est remplacé par la valeur de `cid`, passée à part.
    # SQLite la traite toujours comme une donnée, jamais comme du code SQL :
    # c'est ce qui protège de l'injection SQL (un texte piégé qui modifierait la requête).
    camp = c.execute("SELECT * FROM campaigns WHERE id=?", (cid,)).fetchone()
    # `raise HTTPException(code, message)` interrompt la route : FastAPI renvoie alors au navigateur
    # une réponse avec ce code HTTP et ce message, au lieu du résultat normal.
    # 404 = « introuvable ».
    if not camp:
        raise HTTPException(404, "Campagne introuvable")
    return camp


def _recording_or_404(c, rid: int):
    """Renvoie l'enregistrement `rid`, ou une erreur 404 s'il n'existe pas."""
    rec = c.execute("SELECT * FROM recordings WHERE id=?", (rid,)).fetchone()
    if not rec:
        raise HTTPException(404, "Enregistrement introuvable")
    return rec


def _check_dates(start: Optional[str], end: Optional[str]) -> None:
    """Refuse (erreur 400 = requête incorrecte) une dernière nuit placée avant la première."""
    # Les dates sont au format texte AAAA-MM-JJ : dans ce format, l'ordre alphabétique
    # est aussi l'ordre chronologique, donc on peut comparer les textes directement.
    if start and end and end < start:
        raise HTTPException(400, "La dernière nuit du festival est avant la première.")


def _groups_by_recording(c, rec_ids: list[int], threshold: float = detection.DEFAULT_THRESHOLD) -> dict[int, list[str]]:
    """Groupes distincts détectés dans chaque enregistrement (cris au-dessus du seuil), en une requête."""
    # Liste vide : rien à chercher (et `IN ()` serait du SQL invalide)
    if not rec_ids:
        return {}
    # On fabrique autant de `?` que d'identifiants : pour 3 ids, marks = "?,?,?".
    # On garde ainsi une requête paramétrée même avec une liste de longueur variable.
    marks = ",".join("?" * len(rec_ids))
    # Dictionnaire de départ : chaque enregistrement → ensemble vide (un set évite les doublons).
    # `{i: set() for i in rec_ids}` est une compréhension de dictionnaire.
    out: dict[int, set] = {i: set() for i in rec_ids}
    # Une seule requête pour tous les enregistrements (plutôt qu'une par enregistrement).
    # La f-string insère seulement les `?` ; les vraies valeurs sont passées à part :
    # `(*rec_ids, threshold)` « déplie » la liste des ids puis ajoute le seuil à la fin.
    for r in c.execute(
        f"SELECT DISTINCT recording_id, grp FROM calls WHERE recording_id IN ({marks}) AND det_prob>?",
        (*rec_ids, threshold),
    ):
        out[r["recording_id"]].add(r["grp"])
    # On renvoie des listes triées (un set n'a pas d'ordre et ne passe pas tel quel en JSON)
    return {k: sorted(v) for k, v in out.items()}


def _apply_auto_phases(c, cid: int) -> int:
    """Recalcule la phase des enregistrements classés automatiquement (après un changement de dates).
    Renvoie le nombre d'enregistrements qui ont changé de phase."""
    camp = c.execute("SELECT * FROM campaigns WHERE id=?", (cid,)).fetchone()
    n = 0
    # On ne touche qu'aux enregistrements en phase 'auto' : une phase choisie à la main ('manuel') est respectée.
    # `.fetchall()` lit toutes les lignes d'un coup avant la boucle, car on fait d'autres requêtes dedans.
    for r in c.execute("SELECT id, night, phase FROM recordings WHERE campaign_id=? AND phase_source='auto'", (cid,)).fetchall():
        p = analysis.phase_for(r["night"], camp["festival_start"], camp["festival_end"])
        # On n'écrit que si une phase a pu être calculée ET qu'elle est différente de l'actuelle
        if p and p != r["phase"]:
            c.execute("UPDATE recordings SET phase=? WHERE id=?", (p, r["id"]))
            n += 1
    return n


def _unlink(paths) -> None:
    """Supprime des fichiers du disque. missing_ok=True : pas d'erreur si un fichier n'existe déjà plus."""
    for p in paths:
        Path(p).unlink(missing_ok=True)


# ---------- 4a. Santé ----------
# `@app.get("/api/health")` est un décorateur de route : il enregistre la fonction en dessous
# comme réponse à GET /api/health. Le dictionnaire renvoyé est converti en JSON par FastAPI.
@app.get("/api/health")
def health():
    """Indique que le serveur répond, avec quelques réglages utiles à l'interface (seuils, état de la file)."""
    return {
        "status": "ok", "model": "batdetect2", "threshold": detection.DEFAULT_THRESHOLD,
        "analysis_threshold": detection.ANALYSIS_THRESHOLD,
        "queue_idle": worker.idle(), "min_samplerate": MIN_SAMPLERATE,
    }


@app.get("/api/groups")
def groups():
    """Table espèce → groupe, utile à l'interface pour les légendes."""
    return analysis.GROUPS


# ---------- 4b. Campagnes ----------
@app.get("/api/campaigns")
def list_campaigns():
    """Liste toutes les campagnes, de la plus récente à la plus ancienne, avec leur nombre d'enregistrements et de sites."""
    with get_conn() as c:
        # `ca.*` = toutes les colonnes de la campagne. Les deux `(SELECT COUNT(*) ...)` sont des
        # sous-requêtes : pour chaque campagne, elles comptent ses enregistrements et ses sites.
        # `AS n_recordings` donne un nom à la colonne calculée.
        rows = c.execute(
            """SELECT ca.*,
                      (SELECT COUNT(*) FROM recordings r WHERE r.campaign_id=ca.id) AS n_recordings,
                      (SELECT COUNT(*) FROM sites s WHERE s.campaign_id=ca.id) AS n_sites
               FROM campaigns ca ORDER BY ca.id DESC"""
        ).fetchall()
    return [_row(r) for r in rows]


# status_code=201 : en cas de succès, on répond 201 (« créé ») au lieu de 200.
# `body: CampaignIn` : FastAPI lit le JSON envoyé et le vérifie avec le schéma CampaignIn.
@app.post("/api/campaigns", status_code=201)
def create_campaign(body: CampaignIn):
    """Crée une campagne et renvoie la ligne créée."""
    # Les dates arrivent en objets `date` : on les remet en texte AAAA-MM-JJ (`.isoformat()`)
    # pour les stocker en base. Si une date est absente, on stocke None (NULL en SQL).
    start = body.festival_start.isoformat() if body.festival_start else None
    end = body.festival_end.isoformat() if body.festival_end else None
    _check_dates(start, end)
    with get_conn() as c:
        # `.strip()` retire les espaces au début et à la fin du nom
        cur = c.execute(
            "INSERT INTO campaigns(name, description, festival_start, festival_end) VALUES (?,?,?,?)",
            (body.name.strip(), body.description, start, end),
        )
        # `cur.lastrowid` = l'identifiant que SQLite vient de donner à la nouvelle ligne
        return _row(c.execute("SELECT * FROM campaigns WHERE id=?", (cur.lastrowid,)).fetchone())


# `{cid}` dans l'adresse est un paramètre de chemin : pour GET /api/campaigns/7, FastAPI appelle
# get_campaign(cid=7). L'annotation `cid: int` fait que FastAPI convertit "7" en nombre
# (et répond 422 si ce n'est pas un nombre).
@app.get("/api/campaigns/{cid}")
def get_campaign(cid: int):
    """Une campagne avec la liste de ses sites (sites du festival d'abord, témoins ensuite)."""
    with get_conn() as c:
        camp = _campaign_or_404(c, cid)
        # ORDER BY is_control : 0 (festival) avant 1 (témoin), puis par ordre de création
        sites = c.execute("SELECT * FROM sites WHERE campaign_id=? ORDER BY is_control, id", (cid,)).fetchall()
    # `{**a, "cle": v}` crée un nouveau dictionnaire : toutes les clés de `a`, plus "cle"
    return {**_row(camp), "sites": [_row(s) for s in sites]}


def _refuse_null(data: dict, *fields: str) -> None:
    """
    Refuse (erreur 422) un champ envoyé explicitement à null alors que la base l'interdit.
    Sans ce contrôle, `{"name": null}` passerait la validation puis ferait planter l'UPDATE
    (colonne NOT NULL) avec une erreur 500 peu claire.
    """
    for f in fields:
        if f in data and data[f] is None:
            raise HTTPException(422, f"Le champ « {f} » ne peut pas être vide")


@app.patch("/api/campaigns/{cid}")
def update_campaign(cid: int, body: CampaignPatch):
    """Modifie une campagne. Changer les dates du festival reclasse les fichiers en phase « auto »."""
    # `exclude_unset=True` : on ne garde que les champs réellement envoyés par l'interface.
    # Ça permet de distinguer « champ non envoyé » (on n'y touche pas) de « champ envoyé vide ».
    data = body.model_dump(exclude_unset=True)
    _refuse_null(data, "name")
    with get_conn() as c:
        camp = _row(_campaign_or_404(c, cid))
        # Les dates envoyées sont converties en texte AAAA-MM-JJ (ou None pour les effacer)
        for k in ("festival_start", "festival_end"):
            if k in data:
                data[k] = data[k].isoformat() if data[k] else None
        # On vérifie la cohérence des dates sur le résultat final : anciennes valeurs
        # remplacées par les nouvelles (`{**camp, **data}` : les clés de data écrasent celles de camp).
        merged = {**camp, **data}
        _check_dates(merged["festival_start"], merged["festival_end"])
        # Une requête UPDATE par champ envoyé. Le nom de colonne est inséré par f-string
        # (SQLite n'accepte pas de `?` pour un nom de colonne) ; il ne peut valoir qu'un nom
        # de champ du schéma CampaignPatch, puisque Pydantic a filtré le JSON reçu.
        # La valeur, elle, passe bien par un `?`.
        for k, v in data.items():
            c.execute(f"UPDATE campaigns SET {k}=? WHERE id=?", (v, cid))
        # `&` entre deux ensembles = leur intersection : vrai si au moins une des dates a été envoyée.
        # Dans ce cas seulement, on reclasse les enregistrements en phase « auto ».
        moved = _apply_auto_phases(c, cid) if {"festival_start", "festival_end"} & data.keys() else 0
        out = _row(c.execute("SELECT * FROM campaigns WHERE id=?", (cid,)).fetchone())
    # On renvoie la campagne à jour + le nombre de fichiers reclassés (pour l'afficher à l'utilisateur)
    return {**out, "reclassified": moved}


@app.delete("/api/campaigns/{cid}", status_code=204)
def delete_campaign(cid: int):
    """Supprime une campagne, tout ce qu'elle contient en base, et ses fichiers WAV sur le disque."""
    with get_conn() as c:
        _campaign_or_404(c, cid)
        # On note d'abord les chemins des WAV : après la suppression en base, on ne pourrait plus les retrouver.
        paths = [r["path"] for r in c.execute("SELECT path FROM recordings WHERE campaign_id=?", (cid,))]
        # Grâce à ON DELETE CASCADE (voir db.py), les sites, enregistrements et cris partent avec la campagne
        c.execute("DELETE FROM campaigns WHERE id=?", (cid,))
    # Les fichiers sont supprimés après la sortie du `with`, donc une fois la suppression en base validée
    _unlink(paths)  # on supprime aussi les WAV du disque
    # 204 = succès sans contenu : on renvoie une réponse vide
    return Response(status_code=204)


# ---------- 4c. Sites ----------
@app.post("/api/campaigns/{cid}/sites", status_code=201)
def create_site(cid: int, body: SiteIn):
    """Ajoute un site d'enregistrement à une campagne."""
    with get_conn() as c:
        _campaign_or_404(c, cid)
        # SQLite n'a pas de vrai type booléen : on stocke True/False en 1/0 avec int()
        cur = c.execute(
            "INSERT INTO sites(campaign_id, name, is_control, notes) VALUES (?,?,?,?)",
            (cid, body.name.strip(), int(body.is_control), body.notes),
        )
        return _row(c.execute("SELECT * FROM sites WHERE id=?", (cur.lastrowid,)).fetchone())


@app.patch("/api/sites/{sid}")
def update_site(sid: int, body: SitePatch):
    """Modifie le nom, le statut témoin ou les notes d'un site (seulement les champs envoyés)."""
    data = body.model_dump(exclude_unset=True)
    _refuse_null(data, "name", "is_control")
    # Même conversion booléen → 0/1 que pour la création
    if "is_control" in data:
        data["is_control"] = int(data["is_control"])
    with get_conn() as c:
        # `SELECT 1` : on ne veut pas les données, seulement savoir si la ligne existe
        if not c.execute("SELECT 1 FROM sites WHERE id=?", (sid,)).fetchone():
            raise HTTPException(404, "Site introuvable")
        # Une mise à jour par champ envoyé (même principe que update_campaign)
        for k, v in data.items():
            c.execute(f"UPDATE sites SET {k}=? WHERE id=?", (v, sid))
        return _row(c.execute("SELECT * FROM sites WHERE id=?", (sid,)).fetchone())


@app.delete("/api/sites/{sid}", status_code=204)
def delete_site(sid: int):
    """Supprime un site, ses enregistrements (en base, par cascade) et leurs WAV sur le disque."""
    with get_conn() as c:
        if not c.execute("SELECT 1 FROM sites WHERE id=?", (sid,)).fetchone():
            raise HTTPException(404, "Site introuvable")
        paths = [r["path"] for r in c.execute("SELECT path FROM recordings WHERE site_id=?", (sid,))]
        c.execute("DELETE FROM sites WHERE id=?", (sid,))
    _unlink(paths)
    return Response(status_code=204)


# ---------- 4d. Enregistrements ----------
# Ici les données n'arrivent pas en JSON mais en « formulaire multipart » (le format d'envoi de fichiers) :
# - `Form(...)` : champ texte du formulaire ; les `...` veulent dire « obligatoire ».
# - `File(...)` : un ou plusieurs fichiers ; `UploadFile` donne accès au nom et au contenu de chacun.
@app.post("/api/campaigns/{cid}/recordings", status_code=201)
def upload_recordings(
    cid: int,
    site_id: int = Form(...),
    phase: str = Form(...),
    files: list[UploadFile] = File(...),
):
    """
    Dépôt d'un ou plusieurs WAV. phase = avant | pendant | apres | auto.
    'auto' : la phase est déduite de la date de l'enregistrement et des dates du festival.
    Chaque fichier accepté est enregistré sur le disque puis mis dans la file d'analyse.
    Les fichiers refusés sont listés dans `skipped` avec la raison, sans bloquer les autres.
    (Fonction « def » et non « async def » : FastAPI l'exécute à part, les gros fichiers ne bloquent pas le serveur.)
    """
    # --- Vérifications générales, avant de regarder les fichiers ---
    # `(*PHASES, "auto")` construit le tuple ("avant", "pendant", "apres", "auto")
    if phase not in (*PHASES, "auto"):
        raise HTTPException(400, f"phase doit être l'une de {PHASES} ou 'auto'")
    with get_conn() as c:
        camp = _campaign_or_404(c, cid)
        # Le site doit exister ET appartenir à cette campagne
        if not c.execute("SELECT 1 FROM sites WHERE id=? AND campaign_id=?", (site_id, cid)).fetchone():
            raise HTTPException(404, "Site introuvable dans cette campagne")
        # Noms des fichiers déjà déposés sur ce site (un set), pour repérer les doublons
        already = {r["filename"] for r in c.execute("SELECT filename FROM recordings WHERE site_id=?", (site_id,))}

    # `created` : identifiants des enregistrements créés ; `skipped` : fichiers refusés avec leur raison.
    # `continue` (plus bas) passe directement au fichier suivant de la boucle.
    created, skipped = [], []
    for up in files:
        # --- Contrôles rapides sur le NOM du fichier (avant même de l'écrire sur le disque) ---
        # `Path(...).name` ne garde que le nom, sans dossier : protège contre un nom du type "../../x.wav".
        # `or ""` : si le nom est absent (None), on prend un texte vide.
        name = Path(up.filename or "").name
        if not name.lower().endswith(".wav"):
            skipped.append({"filename": name, "reason": "pas un fichier .wav"})
            continue
        if name in already:
            skipped.append({"filename": name, "reason": "déjà déposé sur ce site"})
            continue
        if metadata.TRIGGERED_RE.search(name):
            # Mode déclenché : l'AudioMoth a retiré les silences du fichier. Sa durée n'est donc pas
            # le temps d'écoute et l'activité (contacts / heure) serait fausse.
            skipped.append({"filename": name, "reason": "fichier AudioMoth en mode déclenché (T.WAV) : "
                            "les silences en ont été retirés, l'activité serait fausse. Le « déplier » "
                            "d'abord avec l'application AudioMoth (menu Fichier → Expand), puis déposer le résultat."})
            continue

        # --- Copie du fichier sur le disque ---
        # Nom unique sur le disque pour éviter les collisions entre fichiers de même nom :
        # campagne_site_8-caractères-aléatoires_nom-d-origine. `uuid4().hex[:8]` = début d'un identifiant aléatoire.
        dest = UPLOAD_DIR / f"{cid}_{site_id}_{uuid.uuid4().hex[:8]}_{name}"
        # Copie par morceaux de 1 Mo (`length=1024 * 1024`) : on ne charge jamais tout le fichier en mémoire,
        # ce qui compte pour des WAV de plusieurs centaines de Mo.
        with dest.open("wb") as out:
            shutil.copyfileobj(up.file, out, length=1024 * 1024)

        # Petite fonction définie dans la boucle : refuser le fichier courant = l'effacer du disque
        # et noter la raison. Elle évite de répéter ces deux lignes à chaque contrôle ci-dessous.
        def refuse(reason: str) -> None:
            dest.unlink(missing_ok=True)
            skipped.append({"filename": name, "reason": reason})

        # --- Contrôles sur le CONTENU audio (il faut le fichier sur le disque pour les faire) ---
        # Lecture de la durée (secondes) et de l'échantillonnage (Hz). Si le fichier ne se lit pas, on le refuse.
        try:
            duration, sr = detection.audio_info(str(dest))
        except Exception:
            refuse("WAV illisible ou abîmé")
            continue
        # Échantillonnage trop bas : le fichier ne peut pas contenir les ultrasons (voir config.py).
        # Dans la f-string, `:g` affiche le nombre sans zéros inutiles (ex. 48.0 → 48).
        if sr < MIN_SAMPLERATE:
            refuse(f"échantillonnage {sr / 1000:g} kHz trop bas pour des ultrasons (minimum {MIN_SAMPLERATE // 1000} kHz)")
            continue
        if duration <= 0:
            refuse("fichier vide")
            continue

        # --- Date et nuit de l'enregistrement ---
        # Heure de l'enregistrement : d'abord celle écrite DANS le fichier (avec son fuseau, convertie en
        # heure française), sinon celle du nom du fichier (fuseau inconnu, UTC par défaut sur AudioMoth).
        dt, time_source = metadata.recording_time(str(dest))
        if dt is not None:
            recorded_at = metadata.to_local(dt)
        else:
            recorded_at = analysis.parse_date(name)
            time_source = "nom du fichier" if recorded_at else None
        # Nuit à laquelle appartient l'enregistrement (un fichier de 2 h du matin compte pour la veille)
        night = analysis.night_of(recorded_at)

        # --- Phase de l'enregistrement ---
        # Par défaut : la phase choisie dans l'interface, marquée « manuel ».
        # En mode 'auto' : calculée à partir de la nuit et des dates du festival. Si le calcul est
        # impossible (pas de date, ou dates du festival absentes), on refuse le fichier avec la raison.
        rec_phase, source = phase, "manuel"
        if phase == "auto":
            rec_phase, source = analysis.phase_for(night, camp["festival_start"], camp["festival_end"]), "auto"
            if rec_phase is None:
                refuse("dates du festival non renseignées dans la campagne" if night
                       else "pas de date dans le fichier ni dans son nom (attendu : AAAAMMJJ_HHMMSS)")
                continue

        # --- Enregistrement en base, puis mise en file d'analyse ---
        with get_conn() as c:
            cur = c.execute(
                """INSERT INTO recordings(campaign_id,site_id,phase,phase_source,filename,path,recorded_at,time_source,night,duration,samplerate)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (cid, site_id, rec_phase, source, name, str(dest), recorded_at, time_source, night, duration, sr),
            )
            created.append(cur.lastrowid)
        # On ajoute le nom aux « déjà déposés » pour refuser un doublon dans le même envoi
        already.add(name)
        # `created[-1]` = le dernier élément de la liste, c'est-à-dire l'id qu'on vient de créer.
        # L'analyse se fera en arrière-plan (voir worker.py) : on n'attend pas.
        worker.enqueue(created[-1])

    # --- Réponse ---
    # Ni créé ni refusé : la liste de fichiers était vide
    if not created and not skipped:
        raise HTTPException(400, "Aucun fichier reçu")
    # On relit les enregistrements créés pour les renvoyer à l'interface (même technique des `?` multiples
    # que dans _groups_by_recording). S'il n'y en a aucun, liste vide.
    with get_conn() as c:
        rows = c.execute(
            f"SELECT * FROM recordings WHERE id IN ({','.join('?' * len(created))})", created
        ).fetchall() if created else []
    return {"created": [_row(r) for r in rows], "skipped": skipped}


@app.get("/api/campaigns/{cid}/recordings")
def list_recordings(cid: int):
    """Tous les enregistrements d'une campagne, avec le nom de leur site et les groupes d'espèces détectés."""
    with get_conn() as c:
        _campaign_or_404(c, cid)
        # JOIN : on assemble chaque enregistrement (r) avec la ligne de son site (s), reliés par s.id = r.site_id,
        # pour récupérer le nom du site et son statut témoin dans la même requête.
        rows = c.execute(
            """SELECT r.*, s.name AS site_name, s.is_control
               FROM recordings r JOIN sites s ON s.id=r.site_id
               WHERE r.campaign_id=? ORDER BY r.phase, s.id, r.recorded_at, r.id""",
            (cid,),
        ).fetchall()
        # Groupes d'espèces : seulement pour les enregistrements déjà analysés
        grp = _groups_by_recording(c, [r["id"] for r in rows if r["status"] == "done"])
    # `grp.get(id, [])` : la liste des groupes, ou une liste vide si l'enregistrement n'est pas analysé
    return [{**_row(r), "groups": grp.get(r["id"], [])} for r in rows]


@app.get("/api/recordings/{rid}")
def get_recording(rid: int):
    """Un enregistrement avec son site et la liste complète de ses cris, dans l'ordre du temps."""
    with get_conn() as c:
        rec = c.execute(
            "SELECT r.*, s.name AS site_name, s.is_control FROM recordings r JOIN sites s ON s.id=r.site_id WHERE r.id=?",
            (rid,),
        ).fetchone()
        if not rec:
            raise HTTPException(404, "Enregistrement introuvable")
        calls = c.execute("SELECT * FROM calls WHERE recording_id=? ORDER BY start_time", (rid,)).fetchall()
    return {**_row(rec), "calls": [_row(k) for k in calls]}


@app.patch("/api/recordings/{rid}")
def update_recording(rid: int, body: RecordingPatch):
    """Corrige la phase (ou repasse en 'auto') et/ou le site d'un enregistrement déjà déposé."""
    with get_conn() as c:
        rec = _recording_or_404(c, rid)
        # Changement de site : le nouveau site doit appartenir à la même campagne
        if body.site_id is not None:
            if not c.execute("SELECT 1 FROM sites WHERE id=? AND campaign_id=?", (body.site_id, rec["campaign_id"])).fetchone():
                raise HTTPException(404, "Site introuvable dans cette campagne")
            c.execute("UPDATE recordings SET site_id=? WHERE id=?", (body.site_id, rid))
        # Retour en 'auto' : on recalcule la phase depuis la nuit et les dates du festival
        if body.phase == "auto":
            camp = c.execute("SELECT * FROM campaigns WHERE id=?", (rec["campaign_id"],)).fetchone()
            p = analysis.phase_for(rec["night"], camp["festival_start"], camp["festival_end"])
            if p is None:
                raise HTTPException(400, "Impossible de calculer la phase : date du fichier ou dates du festival manquantes")
            c.execute("UPDATE recordings SET phase=?, phase_source='auto' WHERE id=?", (p, rid))
        # Phase choisie à la main : elle est marquée 'manuel' et ne sera plus recalculée automatiquement
        elif body.phase is not None:
            c.execute("UPDATE recordings SET phase=?, phase_source='manuel' WHERE id=?", (body.phase, rid))
        return _row(c.execute("SELECT * FROM recordings WHERE id=?", (rid,)).fetchone())


@app.delete("/api/recordings/{rid}", status_code=204)
def delete_recording(rid: int):
    """Supprime un enregistrement (ses cris partent avec, par cascade) et son WAV sur le disque."""
    with get_conn() as c:
        rec = _recording_or_404(c, rid)
        c.execute("DELETE FROM recordings WHERE id=?", (rid,))
    _unlink([rec["path"]])
    return Response(status_code=204)


# 202 = « accepté » : la demande est prise en compte, mais le travail se fera plus tard (dans la file)
@app.post("/api/recordings/{rid}/reprocess", status_code=202)
def reprocess(rid: int):
    """Relance l'analyse (utile après une erreur)."""
    with get_conn() as c:
        _recording_or_404(c, rid)
        # On remet l'enregistrement « en attente » avant de le redéposer dans la file
        c.execute("UPDATE recordings SET status='pending', progress=0, error='' WHERE id=?", (rid,))
    worker.enqueue(rid)
    return {"queued": rid}


def _wav_path_or_410(rec) -> str:
    """Renvoie le chemin du WAV, ou une erreur 410 (« n'existe plus ») si le fichier a disparu du disque
    alors que l'enregistrement est toujours en base."""
    if not Path(rec["path"]).exists():
        raise HTTPException(410, "Le fichier WAV n'est plus sur le disque")
    return rec["path"]


# ---------- 4e. Spectrogramme et extrait audio ----------
# Les paramètres de la fonction qui ne figurent pas dans l'adresse (t0, t1, w, h…) sont des
# paramètres de requête : ils se passent après un « ? » dans l'URL,
# ex. /api/recordings/3/spectrogram.png?t0=10&t1=15&theme=dark.
# Ceux qui ont une valeur par défaut sont facultatifs ; FastAPI convertit chacun dans le type annoncé.
@app.get("/api/recordings/{rid}/spectrogram.png")
def spectrogram(rid: int, t0: float = 0.0, t1: Optional[float] = None, min_prob: float = 0.0, hl: Optional[int] = None,
                w: int = 1200, h: int = 360, dpr: float = 1.0, theme: str = "light"):
    """
    Image PNG du spectrogramme entre t0 et t1 (5 s max) avec les boîtes des cris dont det_prob >= min_prob.
    hl = id d'un cri à surligner en jaune.
    w, h = taille d'affichage en pixels CSS (bornées), dpr = densité de l'écran (1 à 3).
    theme = "light" (fond blanc, cris en noir) ou "dark" (fond sombre, cris en clair).
    """
    # On borne les valeurs reçues : `min(max(x, bas), haut)` ramène x entre bas et haut.
    # Ça évite qu'une URL demande une image démesurée.
    dpr = min(max(dpr, 1.0), 3.0)
    w = min(max(w, 280), 3000)
    h = min(max(h, 160), 2000)
    # On plafonne la taille réelle de l'image (~4,5 millions de pixels) pour garder un rendu rapide
    dpr = min(dpr, (4_500_000 / (w * h)) ** 0.5)

    # Cris à dessiner : ceux de cet enregistrement, au-dessus du score demandé, et qui chevauchent
    # la fenêtre [t0, t1] (un cri chevauche si sa fin est après t0 et son début avant t1).
    # Si t1 n'est pas donné, la fenêtre s'arrête à t0 + spectro.MAX_SPAN.
    with get_conn() as c:
        rec = _recording_or_404(c, rid)
        calls = [_row(k) for k in c.execute(
            "SELECT * FROM calls WHERE recording_id=? AND det_prob>? AND end_time>=? AND start_time<=?",
            (rid, min_prob, t0, (t1 if t1 is not None else t0 + spectro.MAX_SPAN)),
        )]
    # Le dessin lui-même est fait par spectro.py, qui renvoie les octets de l'image PNG
    png = spectro.render(_wav_path_or_410(rec), calls, t0=max(t0, 0.0), t1=t1, highlight=hl, width=w, height=h, dpr=dpr,
                         dark=(theme == "dark"))
    # L'image d'une fenêtre ne change pas tant que les détections ne changent pas : le navigateur peut la garder
    # (en-tête Cache-Control : garder 300 secondes, pour ce navigateur seulement).
    return Response(content=png, media_type="image/png", headers={"Cache-Control": "private, max-age=300"})


@app.get("/api/recordings/{rid}/audio.wav")
def audio(rid: int, t0: float = 0.0, t1: Optional[float] = None, slow: int = 10):
    """Extrait sonore ralenti (×10 par défaut) entre t0 et t1 (10 s max) : les ultrasons deviennent audibles."""
    # Facteur de ralentissement accepté : de 1 à 40 (`1 <= slow <= 40` est une double comparaison)
    if not 1 <= slow <= 40:
        raise HTTPException(400, "slow doit être entre 1 et 40")
    with get_conn() as c:
        rec = _recording_or_404(c, rid)
    # Sans t1, l'extrait dure 5 s à partir de t0. Le découpage et le ralentissement sont faits par spectro.py.
    wav = spectro.audio_clip(_wav_path_or_410(rec), max(t0, 0.0), t1 if t1 is not None else t0 + 5, slow=slow)
    return Response(content=wav, media_type="audio/wav")


# ---------- 4f. Synthèse d'une campagne ----------
@app.get("/api/campaigns/{cid}/summary")
def summary(cid: int):
    """
    Les chiffres qui comptent : contacts par heure et groupes présents,
    - par phase et par type de site (`by_type` : « impact » = sites du festival, « control » = témoins),
    - par phase tous sites confondus (`phases`, à ne pas utiliser pour conclure : il mélange témoin et festival),
    - par site × phase (comparaison festival / témoin = design BACI),
    - par site × nuit (pour voir la variabilité d'une nuit à l'autre).
    Ne prend que les enregistrements analysés ('done').
    """
    # --- Lecture en base (tout est lu d'un coup, les calculs se font ensuite en Python) ---
    with get_conn() as c:
        _campaign_or_404(c, cid)
        sites = [_row(s) for s in c.execute("SELECT * FROM sites WHERE campaign_id=? ORDER BY is_control, id", (cid,))]
        recs = [_row(r) for r in c.execute("SELECT * FROM recordings WHERE campaign_id=? AND status='done'", (cid,))]
        # On ajoute à chaque enregistrement la liste de ses groupes d'espèces
        grp = _groups_by_recording(c, [r["id"] for r in recs])
        for r in recs:
            r["groups"] = grp.get(r["id"], [])
        # Répartition des cris par groupe et par phase (pour le graphique de diversité).
        # GROUP BY regroupe les lignes par (phase, groupe) et COUNT(*) compte les cris de chaque paquet.
        grp_rows = c.execute(
            """SELECT r.phase, k.grp, COUNT(*) AS n
               FROM calls k JOIN recordings r ON r.id=k.recording_id
               WHERE r.campaign_id=? AND r.status='done' AND k.det_prob>?
               GROUP BY r.phase, k.grp""",
            (cid, detection.DEFAULT_THRESHOLD),
        ).fetchall()
        # Nombre d'enregistrements pas encore analysés (l'interface peut prévenir que la synthèse est incomplète).
        # `[0]` : la requête renvoie une seule ligne d'une seule colonne, on prend cette valeur.
        pending = c.execute(
            "SELECT COUNT(*) FROM recordings WHERE campaign_id=? AND status IN ('pending','processing')", (cid,)
        ).fetchone()[0]

    # --- Par phase, tous sites confondus ---
    # Compréhension de dictionnaire : une entrée par phase, chacune résumée par analysis.summarize_phase
    # à partir des enregistrements de cette phase.
    by_phase = {p: analysis.summarize_phase([r for r in recs if r["phase"] == p]) for p in PHASES}

    # --- Par type de site (impact / témoin) et par phase ---
    # Design BACI : on ne mélange JAMAIS les sites du festival (« impact ») et le témoin (« control »).
    control_ids = {s["id"] for s in sites if s["is_control"]}
    # Pour chaque type puis chaque phase, on garde les enregistrements de la phase dont le site est
    # du bon type. Le test `(site témoin ?) == (type demandé = control ?)` est vrai quand les deux concordent.
    by_type = {
        kind: {p: analysis.summarize_phase([r for r in recs if r["phase"] == p and ((r["site_id"] in control_ids) == (kind == "control"))])
               for p in PHASES}
        for kind in ("impact", "control")
    }

    # --- Par site et par phase ---
    by_site = [
        {"site": s, "phases": {p: analysis.summarize_phase([r for r in recs if r["phase"] == p and r["site_id"] == s["id"]]) for p in PHASES}}
        for s in sites
    ]

    # --- Nombre de cris par groupe, rangé par phase : {"avant": {"Pipistrelles": 120, ...}, ...} ---
    calls_by_group = {p: {} for p in PHASES}
    for g in grp_rows:
        calls_by_group[g["phase"]][g["grp"]] = g["n"]

    # --- Par site et par nuit ---
    # Une ligne par site × nuit (les fichiers sans date sont regroupés sous night = null)
    # On range d'abord les enregistrements dans des paquets repérés par (site, nuit, phase).
    # `setdefault(clé, [])` renvoie la liste de cette clé, en la créant vide si elle n'existe pas encore.
    nights = {}
    for r in recs:
        key = (r["site_id"], r["night"], r["phase"])
        nights.setdefault(key, []).append(r)
    # Puis on résume chaque paquet et on trie par site puis par nuit.
    # `key=lambda x: ...` : une lambda est une petite fonction sans nom, ici « la clé de tri ».
    # `x["night"] or ""` : une nuit absente (None) est remplacée par "" pour pouvoir être comparée.
    by_night = sorted(
        ({"site_id": k[0], "night": k[1], "phase": k[2], **analysis.summarize_phase(v)} for k, v in nights.items()),
        key=lambda x: (x["site_id"], x["night"] or ""),
    )

    return {"phases": by_phase, "by_type": by_type, "sites": by_site, "nights": by_night,
            "calls_by_group": calls_by_group, "pending": pending}


@app.get("/api/campaigns/{cid}/compare")
def compare_campaign(
    cid: int,
    # Query(...) décrit un paramètre d'adresse (?threshold=0.3) et ses bornes : FastAPI renvoie
    # une erreur 422 tout seul si la valeur sort des bornes.
    # Seuil : pas en dessous du seuil d'analyse (0,1), car les cris plus faibles ne sont pas gardés en base.
    threshold: float = Query(detection.DEFAULT_THRESHOLD, ge=detection.ANALYSIS_THRESHOLD, lt=1),
    window: float = Query(analysis.CONTACT_WINDOW, ge=1, le=60),   # largeur d'une tranche de contact (s)
    h_start: Optional[float] = Query(None, ge=0, lt=24),          # début de la plage horaire (21.5 = 21 h 30)
    h_end: Optional[float] = Query(None, ge=0, lt=24),            # fin de la plage horaire
):
    """
    Données de la page « Comparer » : une ligne par site × nuit, recalculée avec les réglages choisis
    (seuil de score, largeur des tranches de contact, plage horaire de la nuit).
    Le choix des sites, des nuits, du groupe et de la moyenne se fait ensuite dans le navigateur.
    """
    # La plage horaire n'a de sens qu'avec ses deux bornes, et dans le bon ordre une fois rangées
    # sur la nuit (21 h → 6 h est valable, 6 h → 21 h ne l'est pas : ce serait le jour).
    hours = None
    if (h_start is None) != (h_end is None):
        raise HTTPException(422, "Il faut donner le début ET la fin de la plage horaire")
    if h_start is not None:
        a, b = compare.night_window("2000-01-01", h_start, h_end)
        if a >= b:
            raise HTTPException(422, "La plage horaire doit aller du soir vers le matin (ex. 21 h → 6 h)")
        hours = (h_start, h_end)

    with get_conn() as c:
        _campaign_or_404(c, cid)
        sites = [_row(s) for s in c.execute("SELECT * FROM sites WHERE campaign_id=? ORDER BY is_control, id", (cid,))]
        recs = [_row(r) for r in c.execute(
            "SELECT id, site_id, phase, night, recorded_at, duration FROM recordings WHERE campaign_id=? AND status='done'",
            (cid,))]
        # Tous les cris des fichiers analysés au-dessus du seuil choisi (JOIN : on relie chaque cri à son fichier)
        calls = [_row(k) for k in c.execute(
            """SELECT k.recording_id, k.start_time, k.grp, k.det_prob
               FROM calls k JOIN recordings r ON r.id=k.recording_id
               WHERE r.campaign_id=? AND r.status='done' AND k.det_prob>?""",
            (cid, threshold))]
        pending = c.execute(
            "SELECT COUNT(*) FROM recordings WHERE campaign_id=? AND status IN ('pending','processing')", (cid,)
        ).fetchone()[0]

    result = compare.site_nights(recs, calls, threshold, window, hours)
    return {
        "params": {"threshold": threshold, "window": window, "h_start": h_start, "h_end": h_end},
        "sites": sites,
        "groups": sorted({g for row in result["rows"] for g in row["by_group"]}),
        "pending": pending,
        **result,
    }


# ---------- 5. Interface web (frontend compilé) ----------
# Si frontend/dist existe (après `npm run build`), le serveur la sert sur http://localhost:8000/
# Sinon (en développement, avec `npm run dev`), c'est Vite qui sert l'interface sur le port 5173.
if FRONT_DIST.exists():
    # `mount` branche un dossier entier de fichiers statiques (JS, CSS, images) sur l'adresse /assets
    app.mount("/assets", StaticFiles(directory=FRONT_DIST / "assets"), name="assets")

    # Route « attrape-tout » : `{full_path:path}` accepte n'importe quelle adresse, y compris avec des « / ».
    # Elle est déclarée en dernier pour ne pas passer avant les routes /api ci-dessus.
    # include_in_schema=False : elle n'apparaît pas dans la doc automatique /docs.
    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        """Renvoie la page de l'interface React pour toute adresse qui n'est pas une route API."""
        # Une adresse /api/... arrivée jusqu'ici n'existe pas : on répond 404 plutôt que la page web
        if full_path.startswith("api/"):
            raise HTTPException(404, "Route API inconnue")
        # Toute autre URL renvoie index.html : c'est React qui gère la navigation
        return FileResponse(FRONT_DIST / "index.html")
