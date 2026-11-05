"""
Serveur API (FastAPI). C'est le "cerveau" de l'appli :
- reçoit les WAV déposés par l'interface,
- les met dans la file d'analyse BatDetect2 (voir worker.py),
- calcule les indicateurs (contacts / heure, groupes) par phase, par site et par nuit,
- dessine les spectrogrammes et fabrique les extraits sonores ralentis,
- sert aussi l'interface web (dossier frontend/dist) pour qu'une seule commande lance tout.

Lancer : uvicorn app.main:app --reload   (depuis le dossier backend/)
Doc interactive automatique : http://localhost:8000/docs
"""
import logging
import shutil
import uuid
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Literal, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import analysis, detection, metadata, spectro, worker
from .config import FRONT_DIST, MIN_SAMPLERATE, UPLOAD_DIR
from .db import get_conn, init_db

PHASES = ("avant", "pendant", "apres")
log = logging.getLogger("chiro")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    # La table espèce → groupe peut évoluer (ex. correction de la Barbastelle) : on remet à jour
    # le groupe des cris déjà en base, sans relancer l'analyse.
    with get_conn() as c:
        for species, grp in analysis.GROUPS.items():
            c.execute("UPDATE calls SET grp=? WHERE species=? AND grp<>?", (grp, species, grp))
    n = worker.resume_pending()  # reprend les analyses interrompues par un arrêt du serveur
    if n:
        log.info("%s enregistrement(s) remis dans la file d'analyse", n)
    yield


app = FastAPI(title="Chiro Impact API", version="0.2.0", lifespan=lifespan)

# CORS : autorise le frontend Vite (port 5173) à appeler l'API (port 8000) pendant le développement
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ---------- Schémas d'entrée (ce que l'interface envoie en JSON) ----------
class CampaignIn(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""
    # Première et dernière NUIT du festival : servent à classer automatiquement les fichiers
    festival_start: Optional[date] = None
    festival_end: Optional[date] = None


class CampaignPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1)
    description: Optional[str] = None
    festival_start: Optional[date] = None
    festival_end: Optional[date] = None


class SiteIn(BaseModel):
    name: str = Field(min_length=1)
    is_control: bool = False
    notes: str = ""


class SitePatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1)
    is_control: Optional[bool] = None
    notes: Optional[str] = None


class RecordingPatch(BaseModel):
    # 'auto' = recalculer depuis la date du fichier et les dates du festival
    phase: Optional[Literal["avant", "pendant", "apres", "auto"]] = None
    site_id: Optional[int] = None


# ---------- Helpers ----------
def _row(r) -> Optional[dict]:
    return dict(r) if r is not None else None


def _campaign_or_404(c, cid: int):
    camp = c.execute("SELECT * FROM campaigns WHERE id=?", (cid,)).fetchone()
    if not camp:
        raise HTTPException(404, "Campagne introuvable")
    return camp


def _recording_or_404(c, rid: int):
    rec = c.execute("SELECT * FROM recordings WHERE id=?", (rid,)).fetchone()
    if not rec:
        raise HTTPException(404, "Enregistrement introuvable")
    return rec


def _check_dates(start: Optional[str], end: Optional[str]) -> None:
    if start and end and end < start:
        raise HTTPException(400, "La dernière nuit du festival est avant la première.")


def _groups_by_recording(c, rec_ids: list[int], threshold: float = detection.DEFAULT_THRESHOLD) -> dict[int, list[str]]:
    """Groupes distincts détectés dans chaque enregistrement (cris au-dessus du seuil), en une requête."""
    if not rec_ids:
        return {}
    marks = ",".join("?" * len(rec_ids))
    out: dict[int, set] = {i: set() for i in rec_ids}
    for r in c.execute(
        f"SELECT DISTINCT recording_id, grp FROM calls WHERE recording_id IN ({marks}) AND det_prob>?",
        (*rec_ids, threshold),
    ):
        out[r["recording_id"]].add(r["grp"])
    return {k: sorted(v) for k, v in out.items()}


def _apply_auto_phases(c, cid: int) -> int:
    """Recalcule la phase des enregistrements classés automatiquement (après un changement de dates)."""
    camp = c.execute("SELECT * FROM campaigns WHERE id=?", (cid,)).fetchone()
    n = 0
    for r in c.execute("SELECT id, night, phase FROM recordings WHERE campaign_id=? AND phase_source='auto'", (cid,)).fetchall():
        p = analysis.phase_for(r["night"], camp["festival_start"], camp["festival_end"])
        if p and p != r["phase"]:
            c.execute("UPDATE recordings SET phase=? WHERE id=?", (p, r["id"]))
            n += 1
    return n


def _unlink(paths) -> None:
    for p in paths:
        Path(p).unlink(missing_ok=True)


# ---------- Santé ----------
@app.get("/api/health")
def health():
    return {
        "status": "ok", "model": "batdetect2", "threshold": detection.DEFAULT_THRESHOLD,
        "analysis_threshold": detection.ANALYSIS_THRESHOLD,
        "queue_idle": worker.idle(), "min_samplerate": MIN_SAMPLERATE,
    }


@app.get("/api/groups")
def groups():
    """Table espèce → groupe, utile à l'interface pour les légendes."""
    return analysis.GROUPS


# ---------- Campagnes ----------
@app.get("/api/campaigns")
def list_campaigns():
    with get_conn() as c:
        rows = c.execute(
            """SELECT ca.*,
                      (SELECT COUNT(*) FROM recordings r WHERE r.campaign_id=ca.id) AS n_recordings,
                      (SELECT COUNT(*) FROM sites s WHERE s.campaign_id=ca.id) AS n_sites
               FROM campaigns ca ORDER BY ca.id DESC"""
        ).fetchall()
    return [_row(r) for r in rows]


@app.post("/api/campaigns", status_code=201)
def create_campaign(body: CampaignIn):
    start = body.festival_start.isoformat() if body.festival_start else None
    end = body.festival_end.isoformat() if body.festival_end else None
    _check_dates(start, end)
    with get_conn() as c:
        cur = c.execute(
            "INSERT INTO campaigns(name, description, festival_start, festival_end) VALUES (?,?,?,?)",
            (body.name.strip(), body.description, start, end),
        )
        return _row(c.execute("SELECT * FROM campaigns WHERE id=?", (cur.lastrowid,)).fetchone())


@app.get("/api/campaigns/{cid}")
def get_campaign(cid: int):
    with get_conn() as c:
        camp = _campaign_or_404(c, cid)
        sites = c.execute("SELECT * FROM sites WHERE campaign_id=? ORDER BY is_control, id", (cid,)).fetchall()
    return {**_row(camp), "sites": [_row(s) for s in sites]}


@app.patch("/api/campaigns/{cid}")
def update_campaign(cid: int, body: CampaignPatch):
    """Modifie une campagne. Changer les dates du festival reclasse les fichiers en phase « auto »."""
    data = body.model_dump(exclude_unset=True)
    with get_conn() as c:
        camp = _row(_campaign_or_404(c, cid))
        for k in ("festival_start", "festival_end"):
            if k in data:
                data[k] = data[k].isoformat() if data[k] else None
        merged = {**camp, **data}
        _check_dates(merged["festival_start"], merged["festival_end"])
        for k, v in data.items():
            c.execute(f"UPDATE campaigns SET {k}=? WHERE id=?", (v, cid))
        moved = _apply_auto_phases(c, cid) if {"festival_start", "festival_end"} & data.keys() else 0
        out = _row(c.execute("SELECT * FROM campaigns WHERE id=?", (cid,)).fetchone())
    return {**out, "reclassified": moved}


@app.delete("/api/campaigns/{cid}", status_code=204)
def delete_campaign(cid: int):
    with get_conn() as c:
        _campaign_or_404(c, cid)
        paths = [r["path"] for r in c.execute("SELECT path FROM recordings WHERE campaign_id=?", (cid,))]
        c.execute("DELETE FROM campaigns WHERE id=?", (cid,))
    _unlink(paths)  # on supprime aussi les WAV du disque
    return Response(status_code=204)


# ---------- Sites ----------
@app.post("/api/campaigns/{cid}/sites", status_code=201)
def create_site(cid: int, body: SiteIn):
    with get_conn() as c:
        _campaign_or_404(c, cid)
        cur = c.execute(
            "INSERT INTO sites(campaign_id, name, is_control, notes) VALUES (?,?,?,?)",
            (cid, body.name.strip(), int(body.is_control), body.notes),
        )
        return _row(c.execute("SELECT * FROM sites WHERE id=?", (cur.lastrowid,)).fetchone())


@app.patch("/api/sites/{sid}")
def update_site(sid: int, body: SitePatch):
    data = body.model_dump(exclude_unset=True)
    if "is_control" in data:
        data["is_control"] = int(data["is_control"])
    with get_conn() as c:
        if not c.execute("SELECT 1 FROM sites WHERE id=?", (sid,)).fetchone():
            raise HTTPException(404, "Site introuvable")
        for k, v in data.items():
            c.execute(f"UPDATE sites SET {k}=? WHERE id=?", (v, sid))
        return _row(c.execute("SELECT * FROM sites WHERE id=?", (sid,)).fetchone())


@app.delete("/api/sites/{sid}", status_code=204)
def delete_site(sid: int):
    with get_conn() as c:
        if not c.execute("SELECT 1 FROM sites WHERE id=?", (sid,)).fetchone():
            raise HTTPException(404, "Site introuvable")
        paths = [r["path"] for r in c.execute("SELECT path FROM recordings WHERE site_id=?", (sid,))]
        c.execute("DELETE FROM sites WHERE id=?", (sid,))
    _unlink(paths)
    return Response(status_code=204)


# ---------- Enregistrements ----------
@app.post("/api/campaigns/{cid}/recordings", status_code=201)
def upload_recordings(
    cid: int,
    site_id: int = Form(...),
    phase: str = Form(...),
    files: list[UploadFile] = File(...),
):
    """
    Dépôt d'un ou plusieurs WAV. phase = avant | pendant | apres | auto.
    'auto' : la phase est déduite de la date dans le nom du fichier et des dates du festival.
    Chaque fichier accepté est enregistré sur le disque puis mis dans la file d'analyse.
    Les fichiers refusés sont listés dans `skipped` avec la raison, sans bloquer les autres.
    (Fonction « def » et non « async def » : FastAPI l'exécute à part, les gros fichiers ne bloquent pas le serveur.)
    """
    if phase not in (*PHASES, "auto"):
        raise HTTPException(400, f"phase doit être l'une de {PHASES} ou 'auto'")
    with get_conn() as c:
        camp = _campaign_or_404(c, cid)
        if not c.execute("SELECT 1 FROM sites WHERE id=? AND campaign_id=?", (site_id, cid)).fetchone():
            raise HTTPException(404, "Site introuvable dans cette campagne")
        already = {r["filename"] for r in c.execute("SELECT filename FROM recordings WHERE site_id=?", (site_id,))}

    created, skipped = [], []
    for up in files:
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

        # Nom unique sur le disque pour éviter les collisions entre fichiers de même nom
        dest = UPLOAD_DIR / f"{cid}_{site_id}_{uuid.uuid4().hex[:8]}_{name}"
        with dest.open("wb") as out:
            shutil.copyfileobj(up.file, out, length=1024 * 1024)

        def refuse(reason: str) -> None:
            dest.unlink(missing_ok=True)
            skipped.append({"filename": name, "reason": reason})

        try:
            duration, sr = detection.audio_info(str(dest))
        except Exception:
            refuse("WAV illisible ou abîmé")
            continue
        if sr < MIN_SAMPLERATE:
            refuse(f"échantillonnage {sr / 1000:g} kHz trop bas pour des ultrasons (minimum {MIN_SAMPLERATE // 1000} kHz)")
            continue
        if duration <= 0:
            refuse("fichier vide")
            continue

        # Heure de l'enregistrement : d'abord celle écrite DANS le fichier (avec son fuseau, convertie en
        # heure française), sinon celle du nom du fichier (fuseau inconnu, UTC par défaut sur AudioMoth).
        dt, time_source = metadata.recording_time(str(dest))
        if dt is not None:
            recorded_at = metadata.to_local(dt)
        else:
            recorded_at = analysis.parse_date(name)
            time_source = "nom du fichier" if recorded_at else None
        night = analysis.night_of(recorded_at)

        rec_phase, source = phase, "manuel"
        if phase == "auto":
            rec_phase, source = analysis.phase_for(night, camp["festival_start"], camp["festival_end"]), "auto"
            if rec_phase is None:
                refuse("dates du festival non renseignées dans la campagne" if night
                       else "pas de date dans le fichier ni dans son nom (attendu : AAAAMMJJ_HHMMSS)")
                continue

        with get_conn() as c:
            cur = c.execute(
                """INSERT INTO recordings(campaign_id,site_id,phase,phase_source,filename,path,recorded_at,time_source,night,duration,samplerate)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (cid, site_id, rec_phase, source, name, str(dest), recorded_at, time_source, night, duration, sr),
            )
            created.append(cur.lastrowid)
        already.add(name)
        worker.enqueue(created[-1])

    if not created and not skipped:
        raise HTTPException(400, "Aucun fichier reçu")
    with get_conn() as c:
        rows = c.execute(
            f"SELECT * FROM recordings WHERE id IN ({','.join('?' * len(created))})", created
        ).fetchall() if created else []
    return {"created": [_row(r) for r in rows], "skipped": skipped}


@app.get("/api/campaigns/{cid}/recordings")
def list_recordings(cid: int):
    with get_conn() as c:
        _campaign_or_404(c, cid)
        rows = c.execute(
            """SELECT r.*, s.name AS site_name, s.is_control
               FROM recordings r JOIN sites s ON s.id=r.site_id
               WHERE r.campaign_id=? ORDER BY r.phase, s.id, r.recorded_at, r.id""",
            (cid,),
        ).fetchall()
        grp = _groups_by_recording(c, [r["id"] for r in rows if r["status"] == "done"])
    return [{**_row(r), "groups": grp.get(r["id"], [])} for r in rows]


@app.get("/api/recordings/{rid}")
def get_recording(rid: int):
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
        if body.site_id is not None:
            if not c.execute("SELECT 1 FROM sites WHERE id=? AND campaign_id=?", (body.site_id, rec["campaign_id"])).fetchone():
                raise HTTPException(404, "Site introuvable dans cette campagne")
            c.execute("UPDATE recordings SET site_id=? WHERE id=?", (body.site_id, rid))
        if body.phase == "auto":
            camp = c.execute("SELECT * FROM campaigns WHERE id=?", (rec["campaign_id"],)).fetchone()
            p = analysis.phase_for(rec["night"], camp["festival_start"], camp["festival_end"])
            if p is None:
                raise HTTPException(400, "Impossible de calculer la phase : date du fichier ou dates du festival manquantes")
            c.execute("UPDATE recordings SET phase=?, phase_source='auto' WHERE id=?", (p, rid))
        elif body.phase is not None:
            c.execute("UPDATE recordings SET phase=?, phase_source='manuel' WHERE id=?", (body.phase, rid))
        return _row(c.execute("SELECT * FROM recordings WHERE id=?", (rid,)).fetchone())


@app.delete("/api/recordings/{rid}", status_code=204)
def delete_recording(rid: int):
    with get_conn() as c:
        rec = _recording_or_404(c, rid)
        c.execute("DELETE FROM recordings WHERE id=?", (rid,))
    _unlink([rec["path"]])
    return Response(status_code=204)


@app.post("/api/recordings/{rid}/reprocess", status_code=202)
def reprocess(rid: int):
    """Relance l'analyse (utile après une erreur)."""
    with get_conn() as c:
        _recording_or_404(c, rid)
        c.execute("UPDATE recordings SET status='pending', progress=0, error='' WHERE id=?", (rid,))
    worker.enqueue(rid)
    return {"queued": rid}


def _wav_path_or_410(rec) -> str:
    if not Path(rec["path"]).exists():
        raise HTTPException(410, "Le fichier WAV n'est plus sur le disque")
    return rec["path"]


@app.get("/api/recordings/{rid}/spectrogram.png")
def spectrogram(rid: int, t0: float = 0.0, t1: Optional[float] = None, min_prob: float = 0.0, hl: Optional[int] = None,
                w: int = 1200, h: int = 360, dpr: float = 1.0, theme: str = "light"):
    """
    Image PNG du spectrogramme entre t0 et t1 (5 s max) avec les boîtes des cris dont det_prob >= min_prob.
    hl = id d'un cri à surligner en jaune.
    w, h = taille d'affichage en pixels CSS (bornées), dpr = densité de l'écran (1 à 3).
    theme = "light" (fond blanc, cris en noir) ou "dark" (fond sombre, cris en clair).
    """
    dpr = min(max(dpr, 1.0), 3.0)
    w = min(max(w, 280), 3000)
    h = min(max(h, 160), 2000)
    # On plafonne la taille réelle de l'image (~4,5 millions de pixels) pour garder un rendu rapide
    dpr = min(dpr, (4_500_000 / (w * h)) ** 0.5)
    with get_conn() as c:
        rec = _recording_or_404(c, rid)
        calls = [_row(k) for k in c.execute(
            "SELECT * FROM calls WHERE recording_id=? AND det_prob>? AND end_time>=? AND start_time<=?",
            (rid, min_prob, t0, (t1 if t1 is not None else t0 + spectro.MAX_SPAN)),
        )]
    png = spectro.render(_wav_path_or_410(rec), calls, t0=max(t0, 0.0), t1=t1, highlight=hl, width=w, height=h, dpr=dpr,
                         dark=(theme == "dark"))
    # L'image d'une fenêtre ne change pas tant que les détections ne changent pas : le navigateur peut la garder
    return Response(content=png, media_type="image/png", headers={"Cache-Control": "private, max-age=300"})


@app.get("/api/recordings/{rid}/audio.wav")
def audio(rid: int, t0: float = 0.0, t1: Optional[float] = None, slow: int = 10):
    """Extrait sonore ralenti (×10 par défaut) entre t0 et t1 (10 s max) : les ultrasons deviennent audibles."""
    if not 1 <= slow <= 40:
        raise HTTPException(400, "slow doit être entre 1 et 40")
    with get_conn() as c:
        rec = _recording_or_404(c, rid)
    wav = spectro.audio_clip(_wav_path_or_410(rec), max(t0, 0.0), t1 if t1 is not None else t0 + 5, slow=slow)
    return Response(content=wav, media_type="audio/wav")


# ---------- Synthèse d'une campagne ----------
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
    with get_conn() as c:
        _campaign_or_404(c, cid)
        sites = [_row(s) for s in c.execute("SELECT * FROM sites WHERE campaign_id=? ORDER BY is_control, id", (cid,))]
        recs = [_row(r) for r in c.execute("SELECT * FROM recordings WHERE campaign_id=? AND status='done'", (cid,))]
        grp = _groups_by_recording(c, [r["id"] for r in recs])
        for r in recs:
            r["groups"] = grp.get(r["id"], [])
        # Répartition des cris par groupe et par phase (pour le graphique de diversité)
        grp_rows = c.execute(
            """SELECT r.phase, k.grp, COUNT(*) AS n
               FROM calls k JOIN recordings r ON r.id=k.recording_id
               WHERE r.campaign_id=? AND r.status='done' AND k.det_prob>?
               GROUP BY r.phase, k.grp""",
            (cid, detection.DEFAULT_THRESHOLD),
        ).fetchall()
        pending = c.execute(
            "SELECT COUNT(*) FROM recordings WHERE campaign_id=? AND status IN ('pending','processing')", (cid,)
        ).fetchone()[0]

    by_phase = {p: analysis.summarize_phase([r for r in recs if r["phase"] == p]) for p in PHASES}
    # Design BACI : on ne mélange JAMAIS les sites du festival (« impact ») et le témoin (« control »).
    control_ids = {s["id"] for s in sites if s["is_control"]}
    by_type = {
        kind: {p: analysis.summarize_phase([r for r in recs if r["phase"] == p and ((r["site_id"] in control_ids) == (kind == "control"))])
               for p in PHASES}
        for kind in ("impact", "control")
    }
    by_site = [
        {"site": s, "phases": {p: analysis.summarize_phase([r for r in recs if r["phase"] == p and r["site_id"] == s["id"]]) for p in PHASES}}
        for s in sites
    ]
    calls_by_group = {p: {} for p in PHASES}
    for g in grp_rows:
        calls_by_group[g["phase"]][g["grp"]] = g["n"]

    # Une ligne par site × nuit (les fichiers sans date sont regroupés sous night = null)
    nights = {}
    for r in recs:
        key = (r["site_id"], r["night"], r["phase"])
        nights.setdefault(key, []).append(r)
    by_night = sorted(
        ({"site_id": k[0], "night": k[1], "phase": k[2], **analysis.summarize_phase(v)} for k, v in nights.items()),
        key=lambda x: (x["site_id"], x["night"] or ""),
    )

    return {"phases": by_phase, "by_type": by_type, "sites": by_site, "nights": by_night,
            "calls_by_group": calls_by_group, "pending": pending}


# ---------- Interface web (frontend compilé) ----------
# Si frontend/dist existe (après `npm run build`), le serveur la sert sur http://localhost:8000/
if FRONT_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONT_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(404, "Route API inconnue")
        # Toute autre URL renvoie index.html : c'est React qui gère la navigation
        return FileResponse(FRONT_DIST / "index.html")
