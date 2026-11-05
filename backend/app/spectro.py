"""
Spectrogrammes et extraits sonores d'un WAV, servis à l'interface par l'API.

Rôle du fichier
---------------
L'interface montre chaque enregistrement sous forme d'image (le spectrogramme) et permet d'écouter
les cris. Ce fichier fabrique ces deux choses à la demande, à partir du WAV sur le disque.

Qui l'utilise ?
- main.py : les routes /api/recordings/{id}/spectrogram.png et /api/recordings/{id}/audio.wav
  appellent render() et audio_clip(), et utilisent MAX_SPAN.

Sommaire
- read_window()     : lit seulement un morceau [t0, t1] du fichier
- _spectrogram_db() : calcule le spectrogramme en décibels
- render()          : image PNG temps × fréquence d'une fenêtre (5 s max), avec les boîtes de détection
- audio_clip()      : extrait WAV ralenti (×10 par défaut) pour ENTENDRE les cris : 45 kHz ÷ 10 = 4,5 kHz

Notions utiles
- Spectrogramme : image du son. Axe horizontal = temps, axe vertical = fréquence (grave en bas,
  aigu en haut), couleur = intensité. Un cri de chauve-souris y apparaît comme un petit trait.
- FFT (transformée de Fourier rapide) : calcul qui décompose un petit morceau de son en fréquences
  (« combien de 40 kHz, combien de 41 kHz… »). On la répète sur des fenêtres successives :
  c'est la « transformée de Fourier à court terme ». Chaque fenêtre donne une colonne de l'image.
- Décibels (dB) : échelle logarithmique, proche de la perception. Chaque fois que l'amplitude est
  multipliée par 10, on ajoute 20 dB. Permet de voir à la fois des sons forts et des sons faibles.
- matplotlib : bibliothèque de dessin de graphiques. `fig` = la feuille entière, `ax` = la zone de
  dessin avec ses axes ; imshow() affiche un tableau de nombres comme une image ; une « colormap »
  (cmap) est l'échelle de couleurs qui transforme chaque nombre en couleur.
"""
# Imports
# - io : io.BytesIO est un « faux fichier » en mémoire. On y écrit l'image ou le son, puis on
#   récupère les octets pour les envoyer au navigateur, sans rien écrire sur le disque.
# - matplotlib / numpy / soundfile : dessin, calcul, lecture des WAV.
import io
from typing import Optional

import matplotlib
import matplotlib.ticker
import numpy as np
import soundfile as sf

# Choix du « moteur de rendu » de matplotlib. Doit être fait AVANT d'importer pyplot.
matplotlib.use("Agg")  # rendu hors écran (pas de fenêtre), indispensable sur un serveur
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402
# « noqa: E402 » demande à l'outil de vérification du style (flake8) d'ignorer la règle
# « import en haut du fichier » : ici, l'ordre est voulu (voir la ligne matplotlib.use).

# Couleurs de la charte Lagom Natura
GREEN = "#5aa876"
ORANGE = "#e8892f"   # cri à vérifier (score < 0,5), même code couleur que le tableau
YELLOW = "#fbcf38"   # cri sélectionné dans l'interface
SLATE = "#44405a"
# Taille de police par défaut de tous les graphiques (en points).
plt.rcParams.update({"font.size": 9})

# Deux thèmes, comme l'interface. Clair : fond blanc, cris en noir (le rendu d'origine).
# Sombre : la même échelle inversée, du fond de l'interface sombre vers le blanc.
# - "Greys" est une colormap fournie par matplotlib (du blanc au noir).
# - LinearSegmentedColormap.from_list fabrique une colormap dégradée entre deux couleurs.
# - "bg" = couleur de fond, "ink" = couleur des axes et du texte.
# La clé du dict est un booléen : THEMES[False] = clair, THEMES[True] = sombre.
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402
THEMES = {
    False: {"cmap": "Greys", "bg": "white", "ink": SLATE},
    True: {"cmap": LinearSegmentedColormap.from_list("chiro_dark", ["#22202d", "#ffffff"]), "bg": "#22202d", "ink": "#c9c6d8"},
}

# Réglages de l'image.
# - N_FFT : nombre d'échantillons dans chaque fenêtre de FFT. Plus il est grand, plus les fréquences
#   sont précises mais plus le temps est flou (et inversement).
# - HOP : décalage entre deux fenêtres successives. 128 < 512 : les fenêtres se chevauchent,
#   ce qui donne plus de colonnes et une image plus fluide.
MAX_SPAN = 5.0        # secondes affichées au plus (au-delà l'image devient illisible et lente)
MAX_AUDIO_SPAN = 10.0  # secondes d'audio au plus par extrait (×10 = 100 s d'écoute)
F_MIN = 10_000         # bas de l'axe vertical : 10 kHz (en dessous : bruit, vent, musique…)
F_MAX = 125_000        # haut de l'axe vertical, au plus 125 kHz (le modèle voit jusqu'à 120 kHz)
N_FFT = 512            # taille de la fenêtre d'analyse (≈ 1,3 ms à 384 kHz)
HOP = 128              # pas entre deux fenêtres
TARGET_COLUMNS = 1600  # largeur utile de l'image, en colonnes
# (En Python, 10_000 s'écrit avec « _ » pour la lisibilité : c'est le nombre 10000.)


def read_window(path: str, t0: float, t1: float) -> tuple[np.ndarray, int]:
    """Lit uniquement [t0, t1] sur le disque (sans charger le reste du fichier). Renvoie (signal mono, fréquence)."""
    with sf.SoundFile(path) as f:
        sr = f.samplerate
        # Position de départ en échantillons (temps × fréquence), bornée entre 0 et la fin du fichier :
        # une demande au-delà de la fin donne simplement un signal vide, pas une erreur.
        start = min(max(int(t0 * sr), 0), f.frames)
        # seek() place la tête de lecture à cet endroit, sans lire ce qui précède.
        f.seek(start)
        # On lit (t1 - t0) secondes ; [:, 0] garde la première voie (mono).
        y = f.read(max(int((t1 - t0) * sr), 0), dtype="float32", always_2d=True)[:, 0]
    return y, sr


def _spectrogram_db(y: np.ndarray, sr: int) -> np.ndarray:
    """
    Transformée de Fourier à court terme → matrice fréquence × temps, en décibels (0 = le plus fort).
    Sur 5 s à 384 kHz on obtient ~15 000 colonnes : on les regroupe en gardant le MAXIMUM de chaque
    groupe, pour qu'un cri de 3 ms reste visible même quand l'image est réduite.
    """
    # Signal trop court pour une seule fenêtre : on le complète avec des zéros (silence).
    # np.pad(y, (0, k)) ajoute k zéros à la fin.
    if len(y) < N_FFT:
        y = np.pad(y, (0, N_FFT - len(y)))
    # Découpage en fenêtres qui se chevauchent, sans copier les données :
    # - sliding_window_view(y, N_FFT) crée une « vue » de toutes les fenêtres de 512 échantillons
    #   (une par échantillon de départ possible) ;
    # - [::HOP] en garde une sur 128 ; [:n_frames] coupe au nombre exact de fenêtres complètes.
    # Résultat : un tableau 2D (fenêtres, 512).
    n_frames = 1 + (len(y) - N_FFT) // HOP
    frames = np.lib.stride_tricks.sliding_window_view(y, N_FFT)[::HOP][:n_frames]
    # FFT de toutes les fenêtres d'un coup (opération vectorisée, sans boucle Python) :
    # - np.hanning(N_FFT) : « fenêtre de Hann », courbe en cloche qui adoucit les bords de chaque
    #   morceau pour éviter de fausses fréquences dues à la coupure ;
    # - rfft : FFT pour un signal réel, axis=1 = le long de chaque fenêtre ;
    # - np.abs : on garde l'amplitude (la FFT donne des nombres complexes) ;
    # - .T : transposée (lignes ↔ colonnes), pour avoir les fréquences en lignes et le temps en colonnes.
    mag = np.abs(np.fft.rfft(frames * np.hanning(N_FFT), axis=1)).T  # (fréquences, temps)
    # Réduction du nombre de colonnes par « max-pooling » : on regroupe les colonnes par paquets
    # de `group` et on garde la valeur MAXIMALE de chaque paquet. Une moyenne effacerait un cri
    # très bref ; le maximum le conserve.
    group = max(1, mag.shape[1] // TARGET_COLUMNS)
    if group > 1:
        # On coupe les colonnes en trop pour avoir un multiple exact de `group`,
        # puis reshape range chaque paquet dans une 3e dimension et max(axis=2) la réduit.
        cut = mag.shape[1] // group * group
        mag = mag[:, :cut].reshape(mag.shape[0], -1, group).max(axis=2)
    # Passage en décibels, relatif au point le plus fort de l'image :
    # - mag / mag.max() ramène tout entre 0 et 1 (le plus fort = 1 = 0 dB) ;
    # - les petits « + 1e-12 » et « + 1e-6 » évitent une division par zéro et le log de 0
    #   (sur un silence total), qui donneraient une erreur ou -infini.
    return 20 * np.log10(mag / (mag.max() + 1e-12) + 1e-6)


def render(path: str, calls: list[dict], t0: float = 0.0, t1: Optional[float] = None,
           highlight: Optional[int] = None, width: int = 1200, height: int = 360, dpr: float = 1.0,
           dark: bool = False) -> bytes:
    """
    Dessine le spectrogramme de [t0, t1] (au plus MAX_SPAN secondes) et entoure chaque cri de `calls`
    qui tombe dans la fenêtre. `highlight` = id d'un cri à mettre en évidence. Renvoie les octets PNG.

    width / height = taille d'affichage à l'écran (pixels CSS), dpr = densité de l'écran (2 sur un
    téléphone récent). L'image est dessinée à la taille exacte où elle sera vue : le texte des axes
    reste lisible sur un téléphone comme en plein écran sur un grand moniteur.
    dark = True : version pour le thème sombre de l'interface (mêmes données, couleurs inversées).
    """
    # Choix du thème et de la fenêtre de temps.
    # Sans fin demandée (ou fin avant le début), on affiche MAX_SPAN secondes ; jamais plus.
    th = THEMES[bool(dark)]
    if t1 is None or t1 <= t0:
        t1 = t0 + MAX_SPAN
    t1 = min(t1, t0 + MAX_SPAN)
    # Lecture du morceau de son et calcul du spectrogramme.
    y, sr = read_window(path, t0, t1)
    span = max(len(y) / sr, 1e-3)  # durée réellement lue (la fin du fichier peut arriver avant t1)
    D = _spectrogram_db(y, sr)
    # Fréquence la plus haute affichée : la limite de Nyquist du fichier (sr / 2), sans dépasser F_MAX.
    top = min(sr / 2, F_MAX)

    # Création de la figure. matplotlib raisonne en pouces et en points par pouce (dpi) :
    # figsize = (largeur / 100, hauteur / 100) pouces à 100 × dpr dpi donne exactement
    # width × dpr pixels de large et height × dpr de haut.
    fig, ax = plt.subplots(figsize=(width / 100, height / 100), dpi=100 * dpr)
    # Couleur du cadre, des graduations et des titres d'axes selon le thème.
    for spine in ax.spines.values():
        spine.set_color(th["ink"])
    ax.tick_params(colors=th["ink"])
    ax.xaxis.label.set_color(th["ink"])
    ax.yaxis.label.set_color(th["ink"])
    # Affichage du tableau D comme une image :
    # - origin="lower" : la ligne 0 (basses fréquences) en bas ;
    # - aspect="auto" : l'image s'étire pour remplir la zone ;
    # - vmin / vmax : de -55 dB (couleur la plus claire) à 0 dB (la plus foncée) ;
    # - extent : coordonnées réelles des bords (temps de 0 à span, fréquence de 0 à sr / 2).
    ax.imshow(D, origin="lower", aspect="auto", cmap=th["cmap"], vmin=-55, vmax=0,  # même contraste que la v0.1
              extent=(0, span, 0, sr / 2), interpolation="antialiased")
    # Axe vertical : de F_MIN à top, une graduation tous les 20 kHz, affichée en kHz.
    ax.set_ylim(F_MIN, top)
    ticks = list(range(20_000, int(top) + 1, 20_000))
    ax.set_yticks(ticks)
    ax.set_yticklabels([str(f // 1000) for f in ticks])
    ax.set_ylabel("kHz")
    # Axe horizontal : il part de 0, le titre rappelle l'heure réelle du début (t0).
    ax.set_xlabel(f"secondes (à partir de {t0:.2f} s)")
    ax.set_xlim(0, span)

    # Boîtes de détection (décalées de t0 car l'axe commence à 0)
    for c in calls:
        # Cri entièrement hors de la fenêtre affichée : on passe au suivant.
        if c["end_time"] < t0 or c["start_time"] > t0 + span:
            continue
        # Couleur : jaune si c'est le cri sélectionné, orange si le score est sous 0,5, vert sinon.
        sel = highlight is not None and c.get("id") == highlight
        color = YELLOW if sel else (ORANGE if c["det_prob"] < 0.5 else GREEN)
        # Rectangle((x, y), largeur, hauteur) : coin bas-gauche = (début, fréquence basse),
        # largeur = durée du cri, hauteur = étendue en fréquence. Seulement le contour (fill=False).
        ax.add_patch(Rectangle(
            (c["start_time"] - t0, c["low_freq"]),
            c["end_time"] - c["start_time"],
            c["high_freq"] - c["low_freq"],
            fill=False, edgecolor=color, linewidth=2.4 if sel else 1.3,
        ))

    # Petit écran : moins de graduations pour qu'elles ne se chevauchent pas
    ax.xaxis.set_major_locator(matplotlib.ticker.MaxNLocator(nbins=max(3, width // 90)))
    # Finition et export :
    # - tight_layout réduit les marges blanches ;
    # - savefig écrit le PNG dans le faux fichier en mémoire (buf) ;
    # - plt.close(fig) libère la mémoire de la figure (sinon elle s'accumule sur le serveur).
    fig.tight_layout(pad=0.4)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=th["bg"])
    plt.close(fig)
    return buf.getvalue()


def audio_clip(path: str, t0: float, t1: float, slow: int = 10) -> bytes:
    """
    Extrait [t0, t1] (au plus MAX_AUDIO_SPAN s) rejoué `slow` fois plus lentement : on garde les mêmes
    échantillons mais on déclare une fréquence divisée par `slow`. Tout descend dans l'audible.
    Le volume est normalisé pour que les cris faibles s'entendent.

    Exemple : 0,5 s enregistré à 384 kHz, déclaré à 38,4 kHz, dure 5 s à l'écoute,
    et un cri à 45 kHz s'entend à 4,5 kHz.
    """
    # On limite la durée de l'extrait, puis on lit ce morceau.
    t1 = min(t1, t0 + MAX_AUDIO_SPAN)
    y, sr = read_window(path, t0, t1)
    # Normalisation : on divise par le pic pour que le son le plus fort atteigne 90 % du maximum.
    # Le test « if peak > 0 » évite une division par zéro sur un silence ou un extrait vide.
    peak = float(np.abs(y).max()) if len(y) else 0.0
    if peak > 0:
        y = y / peak * 0.9
    # Nouvelle fréquence déclarée = fréquence d'origine ÷ slow. max(slow, 1) évite une division
    # par 0 ; la fréquence déclarée ne descend jamais sous 3000 Hz.
    out_sr = max(int(sr // max(slow, 1)), 3000)
    # Écriture du WAV en mémoire, en entiers 16 bits (PCM_16).
    buf = io.BytesIO()
    sf.write(buf, y, out_sr, format="WAV", subtype="PCM_16")
    return buf.getvalue()
