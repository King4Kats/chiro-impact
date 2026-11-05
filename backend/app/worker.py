"""
File d'attente des analyses (worker.py).

RÔLE DANS L'APPLI
Analyser un WAV avec BatDetect2 peut prendre longtemps (plusieurs minutes pour un fichier
de plusieurs heures). On ne peut pas faire attendre la page web pendant ce temps.
Ce fichier fait donc tourner les analyses « en arrière-plan » :
1. main.py dépose un enregistrement et appelle enqueue(id) : la réponse part tout de suite.
2. Un « ouvrier » (thread) prend les enregistrements un par un, dans l'ordre d'arrivée,
   et lance l'analyse.
3. Le résultat est écrit en base ; l'interface le voit en relisant la base.

Vocabulaire :
- Thread (fil d'exécution) : un morceau du programme qui tourne en parallèle du reste,
  dans le même processus. Ici, le serveur web répond aux requêtes pendant que le thread analyse.
- File (Queue) : une liste d'attente « premier arrivé, premier servi ». Plusieurs threads
  peuvent y déposer ou y prendre des éléments sans se marcher dessus.

Un seul ouvrier : BatDetect2 utilise déjà plusieurs cœurs, en lancer deux en parallèle ralentirait tout.

Au démarrage du serveur, tout ce qui était « en attente » ou « en cours » (serveur coupé
pendant une analyse) est remis dans la file : rien ne se perd.

AVEC QUI IL PARLE
- main.py      : appelle enqueue(), resume_pending() et idle().
- detection.py : detect() lance BatDetect2 sur le fichier ; counted() applique le seuil de score.
- analysis.py  : contacts() compte les contacts à partir des cris détectés.
- db.py        : get_conn() pour lire / écrire en base.

SOMMAIRE
1. Variables partagées (la file, le thread, le verrou)
2. enqueue(), start()          : ajouter à la file, démarrer l'ouvrier
3. resume_pending()            : reprendre les analyses après un redémarrage
4. idle(), wait_idle()         : savoir si tout est fini (utilisé par les tests)
5. _run()                      : la boucle de l'ouvrier
6. process()                   : l'analyse d'UN enregistrement
"""
# `logging` écrit des messages dans le journal du serveur (console)
import logging
# `queue` fournit la file d'attente utilisable entre threads
import queue
# `threading` permet de créer des threads et des verrous
import threading
import time

from . import analysis, detection
from .db import get_conn

# Un « logger » nommé : ses messages apparaissent préfixés par « chiro.worker » dans le journal
log = logging.getLogger("chiro.worker")

# ---------- 1. Variables partagées ----------
# Ces trois variables sont au niveau du module : il n'en existe qu'un exemplaire,
# partagé par tout le programme. Le tiret bas = « interne à ce fichier ».

# La file des identifiants d'enregistrements à analyser.
# L'annotation entre guillemets dit : « une file qui contient des entiers (int) ».
_queue: "queue.Queue[int]" = queue.Queue()
# Le thread ouvrier. `threading.Thread | None` veut dire « un Thread, ou None (rien) » :
# au départ il n'existe pas encore.
_thread: threading.Thread | None = None
# Un verrou (Lock) : un seul thread à la fois peut « tenir » le verrou. Ça sert à éviter
# que deux requêtes simultanées créent chacune leur ouvrier (voir start()).
_lock = threading.Lock()


# ---------- 2. Ajouter à la file / démarrer l'ouvrier ----------
def enqueue(rec_id: int) -> None:
    """Ajoute un enregistrement à la file (et démarre l'ouvrier si besoin)."""
    # On s'assure d'abord que l'ouvrier tourne, puis on dépose l'identifiant dans la file.
    # `put` ne bloque pas : la fonction rend la main tout de suite.
    start()
    _queue.put(rec_id)


def start() -> None:
    """Démarre l'ouvrier une seule fois."""
    # `global` : on veut modifier la variable _thread du module, pas créer une variable locale
    global _thread
    # `with _lock:` prend le verrou au début du bloc et le relâche à la fin (même en cas d'erreur).
    # Pendant ce temps, un autre thread qui appelle start() attend son tour.
    with _lock:
        # On crée un nouvel ouvrier seulement s'il n'y en a pas, ou si le précédent s'est arrêté.
        # - target=_run : la fonction que le thread exécute.
        # - daemon=True : thread « démon », il ne bloque pas l'arrêt du programme
        #   (quand le serveur s'arrête, le thread s'arrête avec lui).
        if _thread is None or not _thread.is_alive():
            _thread = threading.Thread(target=_run, name="chiro-worker", daemon=True)
            _thread.start()


# ---------- 3. Reprise après redémarrage ----------
def resume_pending() -> int:
    """Remet dans la file les enregistrements non terminés (appelé au démarrage). Renvoie leur nombre."""
    with get_conn() as c:
        # Un enregistrement resté « processing » vient d'une analyse coupée par l'arrêt du serveur :
        # on le repasse en « pending » (en attente) et on remet son avancement à 0.
        c.execute("UPDATE recordings SET status='pending', progress=0 WHERE status='processing'")
        # Puis on récupère tous les identifiants en attente, du plus ancien au plus récent.
        # La forme [... for r in ...] est une compréhension de liste : elle construit une liste en une ligne.
        ids = [r["id"] for r in c.execute("SELECT id FROM recordings WHERE status='pending' ORDER BY id")]
    # On les remet dans la file, dans le même ordre
    for i in ids:
        enqueue(i)
    return len(ids)


# ---------- 4. Savoir si tout est fini ----------
def idle() -> bool:
    """Vrai si plus rien n'est à analyser (utile pour les tests)."""
    # `unfinished_tasks` compte les éléments déposés dans la file et pas encore marqués « terminés »
    # par task_done() (voir _run). Il inclut donc l'enregistrement en cours d'analyse.
    return _queue.unfinished_tasks == 0


def wait_idle(timeout: float = 300) -> bool:
    """Attend que la file soit vide. Renvoie False si le délai est dépassé."""
    # On calcule l'heure limite (maintenant + timeout secondes), puis on vérifie
    # tous les dixièmes de seconde si la file est vide.
    end = time.time() + timeout
    while not idle():
        if time.time() > end:
            return False
        time.sleep(0.1)
    return True


# ---------- 5. La boucle de l'ouvrier ----------
def _run() -> None:
    """Boucle sans fin exécutée par le thread ouvrier : prendre un id, l'analyser, recommencer."""
    while True:
        # `get()` attend (bloque) tant que la file est vide, puis renvoie le prochain identifiant.
        # Le thread dort donc sans consommer de processeur quand il n'y a rien à faire.
        rec_id = _queue.get()
        # On attrape toute erreur pour que l'ouvrier continue avec le fichier suivant.
        # `finally` : quoi qu'il arrive, on signale à la file que cet élément est traité
        # (sinon idle() ne deviendrait jamais vrai).
        try:
            process(rec_id)
        except Exception:  # l'ouvrier ne doit jamais mourir
            # `log.exception` écrit le message ET le détail de l'erreur (la pile d'appels)
            log.exception("Analyse %s : erreur inattendue", rec_id)
        finally:
            _queue.task_done()


# ---------- 6. Analyse d'un enregistrement ----------
def process(rec_id: int) -> None:
    """Détection + calcul des contacts pour un enregistrement, puis mise à jour de la base."""
    # Étape 1 : lire l'enregistrement et le marquer « en cours ».
    # Le `?` dans la requête est un paramètre : la valeur (rec_id) est passée à part, dans un tuple.
    # C'est une requête paramétrée : SQLite traite la valeur comme une donnée, jamais comme du
    # code SQL. C'est ce qui protège de l'injection SQL (un texte piégé qui modifierait la requête).
    # `(rec_id,)` avec une virgule : c'est un tuple d'un seul élément.
    with get_conn() as c:
        rec = c.execute("SELECT * FROM recordings WHERE id=?", (rec_id,)).fetchone()
        if not rec or rec["status"] == "done":  # supprimé entre-temps, ou déjà fait (doublon dans la file)
            return
        c.execute("UPDATE recordings SET status='processing', progress=0, error='' WHERE id=?", (rec_id,))
    # En sortant du `with`, le commit a eu lieu : l'interface voit déjà « processing ».

    # Dernier avancement écrit en base. C'est une liste d'un élément (et pas un simple nombre)
    # pour que la fonction on_progress ci-dessous puisse modifier son contenu : une fonction
    # imbriquée peut modifier le contenu d'une liste extérieure, mais pas réaffecter
    # une variable extérieure sans le mot-clé `nonlocal`.
    last = [0.0]

    # Fonction « de rappel » (callback) : on la donne à detection.detect(), qui l'appelle
    # au fil de l'analyse avec la fraction déjà traitée (de 0 à 1).
    def on_progress(frac: float) -> None:
        # On n'écrit en base que tous les 5 % pour ne pas la marteler
        if frac - last[0] >= 0.05 or frac >= 1:
            last[0] = frac
            with get_conn() as c:
                c.execute("UPDATE recordings SET progress=? WHERE id=?", (round(frac, 3), rec_id))

    # Étape 2 : l'analyse proprement dite, dans un try pour pouvoir enregistrer l'erreur si elle échoue.
    try:
        # Détecte les cris avec BatDetect2 (liste de dictionnaires, un par cri),
        # puis compte les contacts (tranches de 5 s avec au moins un cri retenu, voir analysis.py).
        calls = detection.detect(rec["path"], on_progress=on_progress)
        n_contacts = analysis.contacts(calls)

        # Étape 3 : enregistrer le résultat, en une seule transaction (tout ou rien).
        with get_conn() as c:
            # L'utilisateur a pu supprimer le fichier pendant l'analyse : dans ce cas on n'écrit rien.
            if not c.execute("SELECT 1 FROM recordings WHERE id=?", (rec_id,)).fetchone():
                return  # supprimé pendant l'analyse
            # On efface les anciens cris de cet enregistrement (cas d'une ré-analyse)
            # pour ne pas les avoir en double.
            c.execute("DELETE FROM calls WHERE recording_id=?", (rec_id,))
            # `executemany` exécute la même requête INSERT pour chaque élément de la liste :
            # une ligne par cri détecté. La liste est construite par compréhension de liste,
            # chaque tuple donnant les 9 valeurs dans l'ordre des 9 `?`.
            c.executemany(
                """INSERT INTO calls(recording_id,start_time,end_time,low_freq,high_freq,species,grp,det_prob,class_prob)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                [(rec_id, k["start_time"], k["end_time"], k["low_freq"], k["high_freq"],
                  k["species"], k["grp"], k["det_prob"], k["class_prob"]) for k in calls],
            )
            # n_calls = cris au-dessus du seuil par défaut (ce que montrent la liste et la synthèse).
            # `sum(1 for ...)` compte les éléments qui passent le test.
            n_calls = sum(1 for k in calls if detection.counted(k["det_prob"]))
            # Enfin, on marque l'enregistrement « done » avec ses chiffres.
            c.execute(
                "UPDATE recordings SET status='done', progress=1, n_calls=?, n_contacts=?, error='' WHERE id=?",
                (n_calls, n_contacts, rec_id),
            )
    except Exception as e:  # on garde l'erreur en base pour l'afficher dans l'interface
        log.exception("Analyse %s : échec", rec_id)
        # Statut « error » + message, coupé à 500 caractères (`[:500]`) pour rester lisible.
        with get_conn() as c:
            c.execute("UPDATE recordings SET status='error', error=? WHERE id=?", (str(e)[:500], rec_id))
