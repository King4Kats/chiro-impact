"""
File d'attente des analyses.

Un seul « ouvrier » (thread) traite les enregistrements un par un, dans l'ordre d'arrivée :
BatDetect2 utilise déjà plusieurs cœurs, en lancer deux en parallèle ralentirait tout.

Au démarrage du serveur, tout ce qui était « en attente » ou « en cours » (serveur coupé
pendant une analyse) est remis dans la file : rien ne se perd.
"""
import logging
import queue
import threading
import time

from . import analysis, detection
from .db import get_conn

log = logging.getLogger("chiro.worker")

_queue: "queue.Queue[int]" = queue.Queue()
_thread: threading.Thread | None = None
_lock = threading.Lock()


def enqueue(rec_id: int) -> None:
    """Ajoute un enregistrement à la file (et démarre l'ouvrier si besoin)."""
    start()
    _queue.put(rec_id)


def start() -> None:
    """Démarre l'ouvrier une seule fois."""
    global _thread
    with _lock:
        if _thread is None or not _thread.is_alive():
            _thread = threading.Thread(target=_run, name="chiro-worker", daemon=True)
            _thread.start()


def resume_pending() -> int:
    """Remet dans la file les enregistrements non terminés (appelé au démarrage). Renvoie leur nombre."""
    with get_conn() as c:
        c.execute("UPDATE recordings SET status='pending', progress=0 WHERE status='processing'")
        ids = [r["id"] for r in c.execute("SELECT id FROM recordings WHERE status='pending' ORDER BY id")]
    for i in ids:
        enqueue(i)
    return len(ids)


def idle() -> bool:
    """Vrai si plus rien n'est à analyser (utile pour les tests)."""
    return _queue.unfinished_tasks == 0


def wait_idle(timeout: float = 300) -> bool:
    """Attend que la file soit vide. Renvoie False si le délai est dépassé."""
    end = time.time() + timeout
    while not idle():
        if time.time() > end:
            return False
        time.sleep(0.1)
    return True


def _run() -> None:
    while True:
        rec_id = _queue.get()
        try:
            process(rec_id)
        except Exception:  # l'ouvrier ne doit jamais mourir
            log.exception("Analyse %s : erreur inattendue", rec_id)
        finally:
            _queue.task_done()


def process(rec_id: int) -> None:
    """Détection + calcul des contacts pour un enregistrement, puis mise à jour de la base."""
    with get_conn() as c:
        rec = c.execute("SELECT * FROM recordings WHERE id=?", (rec_id,)).fetchone()
        if not rec or rec["status"] == "done":  # supprimé entre-temps, ou déjà fait (doublon dans la file)
            return
        c.execute("UPDATE recordings SET status='processing', progress=0, error='' WHERE id=?", (rec_id,))

    last = [0.0]

    def on_progress(frac: float) -> None:
        # On n'écrit en base que tous les 5 % pour ne pas la marteler
        if frac - last[0] >= 0.05 or frac >= 1:
            last[0] = frac
            with get_conn() as c:
                c.execute("UPDATE recordings SET progress=? WHERE id=?", (round(frac, 3), rec_id))

    try:
        calls = detection.detect(rec["path"], on_progress=on_progress)
        n_contacts = analysis.contacts(calls)
        with get_conn() as c:
            if not c.execute("SELECT 1 FROM recordings WHERE id=?", (rec_id,)).fetchone():
                return  # supprimé pendant l'analyse
            c.execute("DELETE FROM calls WHERE recording_id=?", (rec_id,))
            c.executemany(
                """INSERT INTO calls(recording_id,start_time,end_time,low_freq,high_freq,species,grp,det_prob,class_prob)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                [(rec_id, k["start_time"], k["end_time"], k["low_freq"], k["high_freq"],
                  k["species"], k["grp"], k["det_prob"], k["class_prob"]) for k in calls],
            )
            # n_calls = cris au-dessus du seuil par défaut (ce que montrent la liste et la synthèse)
            n_calls = sum(1 for k in calls if detection.counted(k["det_prob"]))
            c.execute(
                "UPDATE recordings SET status='done', progress=1, n_calls=?, n_contacts=?, error='' WHERE id=?",
                (n_calls, n_contacts, rec_id),
            )
    except Exception as e:  # on garde l'erreur en base pour l'afficher dans l'interface
        log.exception("Analyse %s : échec", rec_id)
        with get_conn() as c:
            c.execute("UPDATE recordings SET status='error', error=? WHERE id=?", (str(e)[:500], rec_id))
