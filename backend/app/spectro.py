"""
Spectrogrammes et extraits sonores d'un WAV, servis à l'interface par l'API.

- render()     : image PNG temps × fréquence d'une fenêtre (5 s max), avec les boîtes de détection
- audio_clip() : extrait WAV ralenti (×10 par défaut) pour ENTENDRE les cris : 45 kHz ÷ 10 = 4,5 kHz
"""
import io
from typing import Optional

import matplotlib
import matplotlib.ticker
import numpy as np
import soundfile as sf

matplotlib.use("Agg")  # rendu hors écran (pas de fenêtre), indispensable sur un serveur
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

# Couleurs de la charte Lagom Natura
GREEN = "#5aa876"
ORANGE = "#e8892f"   # cri à vérifier (confiance < 0,5), même code couleur que le tableau
YELLOW = "#fbcf38"   # cri sélectionné dans l'interface
SLATE = "#44405a"
plt.rcParams.update({"font.size": 9})

# Deux thèmes, comme l'interface. Clair : fond blanc, cris en noir (le rendu d'origine).
# Sombre : la même échelle inversée, du fond de l'interface sombre vers le blanc.
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402
THEMES = {
    False: {"cmap": "Greys", "bg": "white", "ink": SLATE},
    True: {"cmap": LinearSegmentedColormap.from_list("chiro_dark", ["#22202d", "#ffffff"]), "bg": "#22202d", "ink": "#c9c6d8"},
}

MAX_SPAN = 5.0        # secondes affichées au plus (au-delà l'image devient illisible et lente)
MAX_AUDIO_SPAN = 10.0  # secondes d'audio au plus par extrait (×10 = 100 s d'écoute)
F_MIN = 10_000         # en dessous de 10 kHz : bruit, vent, musique… pas de chauves-souris
F_MAX = 125_000        # au-dessus : plus aucune espèce européenne
N_FFT = 512            # taille de la fenêtre d'analyse (≈ 1,3 ms à 384 kHz)
HOP = 128              # pas entre deux fenêtres
TARGET_COLUMNS = 1600  # largeur utile de l'image, en colonnes


def read_window(path: str, t0: float, t1: float) -> tuple[np.ndarray, int]:
    """Lit uniquement [t0, t1] sur le disque (sans charger le reste du fichier). Renvoie (signal mono, fréquence)."""
    with sf.SoundFile(path) as f:
        sr = f.samplerate
        start = min(max(int(t0 * sr), 0), f.frames)
        f.seek(start)
        y = f.read(max(int((t1 - t0) * sr), 0), dtype="float32", always_2d=True)[:, 0]
    return y, sr


def _spectrogram_db(y: np.ndarray, sr: int) -> np.ndarray:
    """
    Transformée de Fourier à court terme → matrice fréquence × temps, en décibels (0 = le plus fort).
    Sur 5 s à 384 kHz on obtient ~15 000 colonnes : on les regroupe en gardant le MAXIMUM de chaque
    groupe, pour qu'un cri de 3 ms reste visible même quand l'image est réduite.
    """
    if len(y) < N_FFT:
        y = np.pad(y, (0, N_FFT - len(y)))
    n_frames = 1 + (len(y) - N_FFT) // HOP
    frames = np.lib.stride_tricks.sliding_window_view(y, N_FFT)[::HOP][:n_frames]
    mag = np.abs(np.fft.rfft(frames * np.hanning(N_FFT), axis=1)).T  # (fréquences, temps)
    group = max(1, mag.shape[1] // TARGET_COLUMNS)
    if group > 1:
        cut = mag.shape[1] // group * group
        mag = mag[:, :cut].reshape(mag.shape[0], -1, group).max(axis=2)
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
    th = THEMES[bool(dark)]
    if t1 is None or t1 <= t0:
        t1 = t0 + MAX_SPAN
    t1 = min(t1, t0 + MAX_SPAN)
    y, sr = read_window(path, t0, t1)
    span = max(len(y) / sr, 1e-3)  # durée réellement lue (la fin du fichier peut arriver avant t1)
    D = _spectrogram_db(y, sr)
    top = min(sr / 2, F_MAX)

    fig, ax = plt.subplots(figsize=(width / 100, height / 100), dpi=100 * dpr)
    for spine in ax.spines.values():
        spine.set_color(th["ink"])
    ax.tick_params(colors=th["ink"])
    ax.xaxis.label.set_color(th["ink"])
    ax.yaxis.label.set_color(th["ink"])
    ax.imshow(D, origin="lower", aspect="auto", cmap=th["cmap"], vmin=-55, vmax=0,  # même contraste que la v0.1
              extent=(0, span, 0, sr / 2), interpolation="antialiased")
    ax.set_ylim(F_MIN, top)
    ticks = list(range(20_000, int(top) + 1, 20_000))
    ax.set_yticks(ticks)
    ax.set_yticklabels([str(f // 1000) for f in ticks])
    ax.set_ylabel("kHz")
    ax.set_xlabel(f"secondes (à partir de {t0:.2f} s)")
    ax.set_xlim(0, span)

    # Boîtes de détection (décalées de t0 car l'axe commence à 0)
    for c in calls:
        if c["end_time"] < t0 or c["start_time"] > t0 + span:
            continue
        sel = highlight is not None and c.get("id") == highlight
        color = YELLOW if sel else (ORANGE if c["det_prob"] < 0.5 else GREEN)
        ax.add_patch(Rectangle(
            (c["start_time"] - t0, c["low_freq"]),
            c["end_time"] - c["start_time"],
            c["high_freq"] - c["low_freq"],
            fill=False, edgecolor=color, linewidth=2.4 if sel else 1.3,
        ))

    # Petit écran : moins de graduations pour qu'elles ne se chevauchent pas
    ax.xaxis.set_major_locator(matplotlib.ticker.MaxNLocator(nbins=max(3, width // 90)))
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
    """
    t1 = min(t1, t0 + MAX_AUDIO_SPAN)
    y, sr = read_window(path, t0, t1)
    peak = float(np.abs(y).max()) if len(y) else 0.0
    if peak > 0:
        y = y / peak * 0.9
    out_sr = max(int(sr // max(slow, 1)), 3000)
    buf = io.BytesIO()
    sf.write(buf, y, out_sr, format="WAV", subtype="PCM_16")
    return buf.getvalue()
