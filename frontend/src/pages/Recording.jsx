import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, phaseLabel } from '../api'
import Help from '../components/Help'
import { fmtDate, fmtDur } from './Campaign'
import { useTheme } from '../theme'

const ZOOMS = [0.5, 1, 2, 5]   // largeurs de fenêtre proposées, en secondes (5 s = maximum du serveur)
const DEFAULT_ZOOM = 1         // 1 s : les cris (3 à 50 ms) restent lisibles
const FOCUS_ZOOM = 0.5         // clic sur un cri : on zoome à 0,5 s autour de lui
const CONTACT_WINDOW = 5       // même règle que le backend : 1 contact = tranche de 5 s avec au moins un cri

// Page de détail d'un enregistrement : spectrogramme navigable (zoom, plein écran, écoute),
// seuil de confiance, espèces, liste des cris.
export default function Recording() {
  const { id } = useParams()
  const [rec, setRec] = useState(null)
  const [error, setError] = useState('')
  const [thr, setThr] = useState(0.3)
  const [t0, setT0] = useState(0)
  const [zoom, setZoom] = useState(DEFAULT_ZOOM)
  const [selected, setSelected] = useState(null) // id du cri cliqué (surligné partout)
  const [full, setFull] = useState(false)        // spectrogramme en plein écran
  const { theme } = useTheme()                    // le spectrogramme suit le thème clair / sombre
  const specCard = useRef(null)

  const load = useCallback(() => {
    api.recording(id).then(setRec).catch((e) => setError(e.message))
  }, [id])
  useEffect(() => { load() }, [load])

  // Tant que l'analyse tourne, on recharge toutes les 3 s
  const working = rec && (rec.status === 'pending' || rec.status === 'processing')
  useEffect(() => {
    if (!working) return
    const t = setInterval(load, 3000)
    return () => clearInterval(t)
  }, [working, load])

  // Le spectrogramme est une image calculée par le serveur : on attend que le curseur
  // se stabilise (300 ms) avant de la redemander, pour ne pas en générer une à chaque cran.
  const imgThr = useDebounced(thr, 300)

  // Cris au-dessus du seuil, triés dans le temps
  const calls = useMemo(
    () => (rec?.calls || []).filter((c) => c.det_prob > thr).sort((a, b) => a.start_time - b.start_time),
    [rec, thr],
  )

  const duration = rec?.duration || 0
  const span = Math.min(zoom, duration || zoom)
  const t1 = Math.min(t0 + span, duration || t0 + span)
  const maxT0 = Math.max(0, duration - span)
  const clampT0 = useCallback((t) => Math.min(Math.max(0, t), maxT0), [maxT0])

  // À l'ouverture : si le début du fichier est silencieux, on se place directement sur le premier cri
  const positioned = useRef(false)
  useEffect(() => {
    if (positioned.current || !rec || rec.status !== 'done') return
    positioned.current = true
    const first = calls[0]
    if (first && first.start_time > span) setT0(clampT0(first.start_time - span * 0.1))
  }, [rec, calls, span, clampT0])

  // Changer de zoom en gardant le même centre
  const changeZoom = useCallback((z) => {
    const center = t0 + span / 2
    const ns = Math.min(z, duration || z)
    setZoom(z)
    setT0(Math.min(Math.max(0, center - ns / 2), Math.max(0, duration - ns)))
  }, [t0, span, duration])

  // Passage suivant / précédent : premier cri après la fenêtre (ou avant), pour sauter les silences
  const nextCall = calls.find((c) => c.start_time > t1)
  const prevCall = [...calls].reverse().find((c) => c.end_time < t0)
  const goTo = useCallback((c) => c && setT0(clampT0(c.start_time - span * 0.1)), [clampT0, span])

  // Plein écran : vrai plein écran du navigateur quand il existe, sinon (iPhone) le bloc couvre la page
  const toggleFull = useCallback(() => {
    if (full) {
      if (document.fullscreenElement) document.exitFullscreen?.()
      setFull(false)
    } else {
      setFull(true)
      specCard.current?.requestFullscreen?.().catch(() => {})
    }
  }, [full])
  useEffect(() => {
    const onChange = () => { if (!document.fullscreenElement) setFull(false) }
    document.addEventListener('fullscreenchange', onChange)
    return () => document.removeEventListener('fullscreenchange', onChange)
  }, [])
  useEffect(() => {
    // Sans vrai plein écran, la page ne doit pas défiler sous le spectrogramme
    document.body.style.overflow = full ? 'hidden' : ''
    return () => { document.body.style.overflow = '' }
  }, [full])

  // Raccourcis clavier : ← → fenêtre précédente / suivante, + − zoom, F plein écran, Échap quitte
  useEffect(() => {
    function onKey(e) {
      if (e.target.closest?.('input, select, textarea') || e.ctrlKey || e.metaKey || e.altKey) return
      const i = ZOOMS.indexOf(zoom)
      if (e.key === 'ArrowRight') setT0(clampT0(t0 + span))
      else if (e.key === 'ArrowLeft') setT0(clampT0(t0 - span))
      else if (e.key === '+' || e.key === '=') i > 0 && changeZoom(ZOOMS[i - 1])
      else if (e.key === '-') i < ZOOMS.length - 1 && changeZoom(ZOOMS[i + 1])
      else if (e.key === 'f' || e.key === 'F') toggleFull()
      else if (e.key === 'Escape' && full) toggleFull()
      else return
      e.preventDefault()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [t0, span, zoom, full, clampT0, changeZoom, toggleFull])

  if (error) return <p className="text-red-600 dark:text-red-400">{error}</p>
  if (!rec) return <p className="text-slate-light">Chargement…</p>

  // Clic sur un cri : on zoome à 0,5 s et on centre la fenêtre dessus
  function focusCall(c) {
    setSelected(c.id)
    const z = Math.min(zoom, FOCUS_ZOOM)
    const ns = Math.min(z, duration)
    setZoom(z)
    setT0(Math.min(Math.max(0, (c.start_time + c.end_time) / 2 - ns / 2), Math.max(0, duration - ns)))
  }

  // Indicateurs calculés côté navigateur pour suivre le seuil en direct
  const nContacts = new Set(calls.map((c) => Math.floor(c.start_time / CONTACT_WINDOW))).size
  const species = countBy(calls, (c) => c.species)
  const groups = countBy(calls, (c) => c.grp)

  return (
    <div className="grid gap-5 sm:gap-6">
      {/* En-tête */}
      <div className="min-w-0">
        <Link to={`/campaigns/${rec.campaign_id}`} className="text-sm text-slate-light hover:text-slate">← Retour à la campagne</Link>
        <h2 className="text-xl sm:text-2xl font-bold break-all">{rec.filename}</h2>
        <p className="text-slate-light text-sm">
          {rec.site_name}{rec.is_control ? ' (témoin)' : ''} · phase <b className="text-slate font-medium">{phaseLabel(rec.phase)}</b>
          {rec.recorded_at && <> · {fmtDate(rec.recorded_at)}{rec.time_source === 'nom du fichier'
            ? <span className="text-orange-600 dark:text-orange-400" title="Heure lue dans le nom du fichier : son fuseau est inconnu. L'AudioMoth nomme ses fichiers en UTC par défaut (2 h de moins que l'heure française en été)."> (heure du nom de fichier, fuseau non vérifié)</span>
            : <span title={`Heure lue dans le fichier (${rec.time_source}), convertie en heure française`}> (heure française)</span>}</>}
          {' · '}{fmtDur(rec.duration)}{rec.samplerate ? ` · ${rec.samplerate / 1000} kHz` : ''}
        </p>
      </div>

      {working && <p className="text-sm bg-yellow/20 px-3 py-2 rounded-sm">Analyse en cours{rec.progress > 0 ? ` (${Math.round(rec.progress * 100)} %)` : ''}… la page se mettra à jour toute seule.</p>}
      {rec.status === 'error' && (
        <div className="text-sm bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-300 px-3 py-2 rounded-sm flex flex-wrap items-center gap-3">
          <span className="flex-1 min-w-0 break-words">L’analyse a échoué : {rec.error || 'erreur inconnue'}</span>
          <button className="btn btn-ghost" onClick={() => api.reprocess(rec.id).then(load)}>Relancer l’analyse</button>
        </div>
      )}

      {/* Tuiles */}
      <div className="grid gap-3 grid-cols-2 lg:grid-cols-4">
        <Tile label="Cris détectés" value={calls.length}
          help={`Nombre de cris dont le score dépasse le seuil affiché (${thr.toFixed(2).replace('.', ',')}). ${rec.calls.length} cris gardés au total (score ≥ 0,1). Un cri n'est pas une chauve-souris : une chauve-souris qui passe émet des dizaines de cris.`} />
        <Tile label="Contacts" value={nContacts}
          help={`Tranches de 5 secondes contenant au moins un cri (au seuil affiché, ${thr.toFixed(2).replace('.', ',')}). C'est l'unité de mesure de l'activité : 30 cris en 2 secondes = 1 seul contact. La synthèse de la campagne compte toujours au seuil 0,3.`} />
        <Tile label="Groupes" value={Object.keys(groups).length}
          help="Nombre de groupes d'espèces différents (Pipistrelles, Myotis, Noctules / Sérotines, Oreillards, Barbastelle, Rhinolophes). Le modèle est fiable à ce niveau, beaucoup moins à l'espèce." />
        <Tile label="Audio analysé" value={fmtDur(rec.duration)}
          help="Durée totale du fichier. Pour l'activité, on divise les contacts par ce temps d'écoute (contacts par heure)." />
      </div>

      {/* Spectrogramme (normal ou plein écran) */}
      <div ref={specCard}
        className={full
          ? 'fixed inset-0 z-50 bg-surface flex flex-col gap-2 p-2 sm:p-4'
          : 'card p-2 sm:p-3 flex flex-col gap-2'}>
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="font-bold flex items-center gap-2 mr-auto">
            Spectrogramme
            <Help text="Une image du son : le temps de gauche à droite, la fréquence (hauteur du son, en kHz) de bas en haut, le noir = l'intensité. Chaque cadre est un cri détecté par le modèle (qui peut se tromper : insectes, bruits). Cadres verts : score ≥ 0,5 ; orange : sous 0,5, à vérifier ; jaune : le cri sélectionné. Zoom 0,5 s pour bien voir la forme des cris, 5 s pour repérer les passages. Clavier : ← → pour avancer, + − pour zoomer, F pour le plein écran." />
          </h3>
          {rec.status === 'done' && <Listen src={api.audioUrl(rec.id, t0.toFixed(3), t1.toFixed(3))} />}
          <button className="btn btn-ghost py-1 px-3" onClick={toggleFull} aria-pressed={full} title="Plein écran (touche F)">
            {full ? '✕ Quitter' : '⛶ Plein écran'}
          </button>
        </div>

        {/* Navigation + zoom */}
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <div className="flex items-center gap-1">
            <button className="btn btn-ghost py-1 px-2.5" disabled={t0 <= 0} onClick={() => setT0(clampT0(t0 - span))} aria-label="Fenêtre précédente">←</button>
            <span className="text-sm tabular-nums text-slate-light text-center min-w-[9.5rem]">
              {fmtT(t0)} – {fmtT(t1)} <span className="hidden sm:inline">sur {fmtT(duration)}</span>
            </span>
            <button className="btn btn-ghost py-1 px-2.5" disabled={t0 >= maxT0} onClick={() => setT0(clampT0(t0 + span))} aria-label="Fenêtre suivante">→</button>
          </div>
          <div className="flex items-center gap-1 text-sm">
            <button className="btn btn-ghost py-1 px-2.5" disabled={!prevCall} onClick={() => goTo(prevCall)} title="Cri précédent hors de la fenêtre">⏮</button>
            <button className="btn btn-ghost py-1 px-2.5" disabled={!nextCall} onClick={() => goTo(nextCall)} title="Cri suivant hors de la fenêtre">⏭</button>
            <Help text="Sauter au passage précédent / suivant : la fenêtre se place sur le prochain cri détecté, en passant les silences. Pratique sur une nuit entière." />
          </div>
          <div className="flex items-center gap-1.5">
            <div className="inline-flex border border-line rounded-sm overflow-hidden" role="group" aria-label="Zoom">
              {ZOOMS.filter((z) => z <= Math.max(duration, ZOOMS[0])).map((z) => (
                <button key={z} onClick={() => changeZoom(z)} aria-pressed={zoom === z}
                  className={`px-2.5 py-1 text-sm tabular-nums border-l first:border-l-0 border-line ${zoom === z ? 'bg-green-dark text-white' : 'bg-surface hover:bg-green-soft'}`}>
                  {String(z).replace('.', ',')} s
                </button>
              ))}
            </div>
            <Help text="Largeur de la fenêtre affichée. 0,5 s : on voit la forme de chaque cri (c'est ce qui permet de reconnaître un groupe). 5 s : vue large pour repérer les passages." />
          </div>
        </div>

        {rec.status === 'done' ? (
          <Spectrogram full={full}
            url={(size) => api.spectrogramUrl(rec.id, t0.toFixed(3), t1.toFixed(3), imgThr, selected, size, theme)}
            alt={`Spectrogramme de ${rec.filename} entre ${t0.toFixed(2)} et ${t1.toFixed(2)} s`} />
        ) : (
          <div className="h-48 grid place-items-center text-slate-light text-sm bg-page rounded">Le spectrogramme apparaîtra une fois l’analyse terminée.</div>
        )}
        {duration > span && <Timeline duration={duration} t0={t0} span={span} calls={calls} selected={selected} onSeek={(t) => setT0(clampT0(t - span / 2))} />}

        {/* Seuil : dans le bloc du spectrogramme, car il change les cadres affichés */}
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm pt-1">
          <label htmlFor="thr" className="font-medium whitespace-nowrap">Seuil de confiance <span className="tabular-nums">{thr.toFixed(2)}</span></label>
          <input id="thr" type="range" min="0.1" max="0.95" step="0.05" value={thr}
            onChange={(e) => setThr(parseFloat(e.target.value))} className="w-full sm:w-52 accent-green-dark order-last sm:order-none" />
          <Help text="Le modèle donne un score de 0 à 1 à chaque cri détecté. Ce curseur ne change que l'AFFICHAGE de cette page. L'analyse garde les cris dès 0,1 : en descendant sous 0,3, tu vois les cris faibles (cris lointains… ou bruits) pour vérifier. Tous les chiffres de la campagne (cris, contacts, groupes, synthèse) sont calculés à 0,3, quelle que soit la position du curseur. 0,3 est un choix (la valeur des exemples de BatDetect2), pas un réglage d'origine du modèle." />
          <span className="tabular-nums text-slate-light">{calls.length} cris sur {rec.calls.length}</span>
        </div>
      </div>

      {/* Espèces proposées */}
      {calls.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          {Object.entries(species).sort((a, b) => b[1] - a[1]).map(([s, n]) => (
            <span key={s} className="text-sm border border-line rounded-sm px-2.5 py-1 bg-surface">
              <i>{s}</i> <b className="text-green-dark">{n}</b>
            </span>
          ))}
          <Help text="Répartition des espèces proposées par le modèle pour ce fichier. Indication seulement : le modèle a été entraîné au Royaume-Uni et ne connaît pas toutes les espèces françaises. On raisonne en groupes, pas en espèces, et un spécialiste doit confirmer." />
        </div>
      )}

      {/* Liste des cris : tableau sur ordinateur / tablette, cartes sur téléphone */}
      {calls.length === 0
        ? <div className="card p-6 text-slate-light">Aucun cri au-dessus de ce seuil.</div>
        : <>
            <CallsTable calls={calls} selected={selected} t0={t0} t1={t1} onPick={focusCall} />
            <CallsCards calls={calls} selected={selected} t0={t0} t1={t1} onPick={focusCall} />
          </>}

      <p className="text-sm border-l-4 border-yellow bg-surface px-4 py-3 rounded-r max-w-3xl">
        Touche un cri dans la liste pour zoomer dessus dans le spectrogramme. L’analyse garde les cris dont le score dépasse 0,1 ;
        le curseur ne fait que masquer ceux sous la valeur choisie. Les chiffres de la campagne sont toujours calculés à 0,3.
      </p>
    </div>
  )
}

// ---------- Morceaux de la page ----------

// Bouton d'écoute : la fenêtre affichée, rejouée 10 fois plus lentement (45 kHz → 4,5 kHz, audible).
function Listen({ src }) {
  const audio = useRef(null)
  const [playing, setPlaying] = useState(false)
  useEffect(() => () => audio.current?.pause(), [])
  useEffect(() => { audio.current?.pause(); setPlaying(false) }, [src]) // la fenêtre a changé
  function toggle() {
    if (playing) { audio.current.pause(); setPlaying(false); return }
    audio.current = new Audio(src)
    audio.current.onended = () => setPlaying(false)
    audio.current.play().then(() => setPlaying(true)).catch(() => setPlaying(false))
  }
  return (
    <span className="inline-flex items-center gap-1.5">
      <button className="btn btn-ghost py-1 px-3" onClick={toggle}>{playing ? '■ Stop' : '▶ Écouter ×10'}</button>
      <Help text="Les cris sont trop aigus pour l'oreille humaine. On rejoue la fenêtre affichée 10 fois plus lentement : tout descend de 10 fois en fréquence (un cri à 45 kHz devient un « tic » à 4,5 kHz). 1 s d'enregistrement = 10 s d'écoute." />
    </span>
  )
}

function Tile({ label, value, help }) {
  return (
    <div className="card p-3 sm:p-4 border-t-4 border-t-green min-w-0">
      <div className="text-xs text-slate-light flex items-center gap-1.5">{label} <Help text={help} /></div>
      <div className="text-2xl sm:text-3xl font-bold tabular-nums leading-tight truncate">{value}</div>
    </div>
  )
}

// Image du spectrogramme, demandée au serveur à la taille exacte de son cadre (et à la densité
// de l'écran) : texte des axes lisible sur téléphone, image nette en plein écran.
function Spectrogram({ url, alt, full }) {
  const box = useRef(null)
  const [size, setSize] = useState(null)

  useEffect(() => {
    const el = box.current
    if (!el) return
    const measure = () => {
      const w = el.clientWidth
      // Normal : hauteur proportionnelle à la largeur (entre 240 et 460 px) ; plein écran : toute la place
      const h = full ? el.clientHeight : Math.round(Math.min(460, Math.max(240, w * 0.34)))
      const dpr = Math.min(window.devicePixelRatio || 1, 2)
      // Arrondi à 20 px : un petit redimensionnement ne redemande pas d'image
      setSize({ w: Math.round(w / 20) * 20, h: Math.round(h / 20) * 20, dpr: Math.round(dpr * 4) / 4 })
    }
    measure()
    const ro = new ResizeObserver(() => { clearTimeout(ro.t); ro.t = setTimeout(measure, 150) })
    ro.observe(el)
    return () => { ro.disconnect(); clearTimeout(ro.t) }
  }, [full])

  const src = size && size.w > 0 && size.h > 0 ? url(size) : null
  const [loaded, setLoaded] = useState(null)
  const [failed, setFailed] = useState(false)
  useEffect(() => setFailed(false), [src])
  const loading = src && loaded !== src

  return (
    <div ref={box} className={`relative bg-page rounded overflow-hidden ${full ? 'flex-1 min-h-0' : ''}`}
      style={full ? undefined : { height: size ? size.h : 280 }}>
      {src && <img src={src} alt={alt} className="absolute inset-0 w-full h-full object-fill"
        onLoad={() => setLoaded(src)} onError={() => { setLoaded(src); setFailed(true) }} />}
      {loading && <div className="absolute inset-0 bg-surface/50 grid place-items-center text-sm text-slate-light">Calcul du spectrogramme…</div>}
      {failed && <div className="absolute inset-0 grid place-items-center text-sm text-red-700 dark:text-red-300">Impossible de générer le spectrogramme.</div>}
    </div>
  )
}

// Frise sous le spectrogramme : toute la durée du fichier, un trait par cri, la fenêtre affichée en vert pâle.
// Clic (ou toucher) = on y déplace la fenêtre. Indispensable pour les fichiers longs (une nuit entière).
function Timeline({ duration, t0, span, calls, selected, onSeek }) {
  const sel = calls.find((c) => c.id === selected)
  return (
    <div className="grid gap-1">
      <div
        role="slider" aria-label="Position dans le fichier" aria-valuemin={0} aria-valuemax={Math.round(duration)} aria-valuenow={Math.round(t0)} tabIndex={0}
        className="relative h-7 bg-page border border-line rounded-sm cursor-pointer touch-none"
        onPointerDown={(e) => { const r = e.currentTarget.getBoundingClientRect(); onSeek(((e.clientX - r.left) / r.width) * duration) }}
      >
        <div className="absolute inset-y-0 bg-green-soft border-x-2 border-green" style={{ left: `${(t0 / duration) * 100}%`, width: `${Math.max((span / duration) * 100, 0.6)}%` }} />
        {calls.map((c) => (
          <div key={c.id} className="absolute top-1 bottom-1 w-px bg-slate/50" style={{ left: `${(c.start_time / duration) * 100}%` }} />
        ))}
        {sel && <div className="absolute -top-0.5 -bottom-0.5 w-0.5 bg-yellow" style={{ left: `${(sel.start_time / duration) * 100}%` }} />}
      </div>
      <p className="text-xs text-slate-light">Vue d’ensemble du fichier : chaque trait est un cri, le cadre vert la fenêtre affichée. Touche la frise pour t’y déplacer.</p>
    </div>
  )
}

const COLS = [
  ['#', null, ''],
  ['Début (s)', "Instant où le cri commence, en secondes depuis le début du fichier.", 'r'],
  ['Fin (s)', 'Instant où le cri se termine. Un cri de chauve-souris dure quelques millisecondes.', 'r'],
  ['Durée (ms)', "Fin moins début, en millisecondes. Pipistrelle : 3 à 8 ms. Grand rhinolophe : jusqu'à 50 ms et plus. C'est un indice d'espèce.", 'r'],
  ['F. basse (kHz)', "Bas de la boîte de détection, en kilohertz : à peu près la fréquence la plus basse du cri. L'oreille humaine s'arrête vers 20 kHz ; en Europe les chauves-souris crient à peu près entre 15 et 120 kHz.", 'r'],
  ['F. haute (kHz)', "Haut de la boîte de détection : à peu près la fréquence la plus haute du cri. Ce n'est pas la « fréquence caractéristique » qu'utilisent les naturalistes (fréquence où le cri est le plus fort, ex. ~45 kHz pour la Pipistrelle commune, ~82 kHz pour le Grand rhinolophe).", 'r'],
  ['Espèce proposée', "Espèce la plus probable selon le modèle, parmi les 17 espèces britanniques qu'il connaît. Il ne connaît pas par exemple la Pipistrelle de Kuhl, très commune en France : ses cris seront attribués à une autre espèce. Le groupe est plus robuste que l'espèce, mais n'a pas été évalué sur des données françaises.", 'l'],
  ['Groupe', "Groupe acoustique de l'espèce proposée. C'est ce niveau qui sert à mesurer la diversité.", 'l'],
  ['Confiance cri', "Score du modèle (det_prob, de 0 à 1) : plus il est haut, plus le modèle est sûr que la boîte contient un cri de chauve-souris. Ce n'est pas une vraie probabilité et le modèle peut se tromper (insectes, bruits électroniques). En orange : sous 0,5, à vérifier à l'œil ou à l'oreille.", 'r'],
  ['Confiance espèce', "Score de l'espèce proposée (class_prob). Le modèle a été entraîné au Royaume-Uni sur 17 espèces : à prendre avec beaucoup de recul, il n'a pas été évalué sur des données françaises.", 'r'],
]

// Fait défiler la liste jusqu'au cri sélectionné (quand on le choisit ailleurs, ex. depuis la frise)
function useScrollToSelected(selected) {
  const box = useRef(null)
  useEffect(() => {
    const el = box.current?.querySelector('[data-selected="true"]')
    if (el && box.current.offsetParent !== null) el.scrollIntoView({ block: 'nearest' })
  }, [selected])
  return box
}

function CallsTable({ calls, selected, t0, t1, onPick }) {
  const box = useScrollToSelected(selected)
  return (
    <div ref={box} className="hidden md:block card overflow-auto max-h-[36rem]">
      <table className="w-full text-sm">
        <thead className="sticky top-0 bg-surface z-10">
          <tr>
            {COLS.map(([label, help, align]) => (
              <th key={label} className={`th !whitespace-normal align-bottom ${align === 'r' ? 'text-right' : ''}`}>
                <span className={`inline-flex items-center gap-1 ${align === 'r' ? 'justify-end' : ''}`}>
                  {label}
                  {help && <Help text={help} />}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {calls.map((c, i) => {
            const inView = c.end_time >= t0 && c.start_time <= t1
            const low = c.det_prob < 0.5
            return (
              <tr key={c.id} onClick={() => onPick(c)} title="Zoomer le spectrogramme sur ce cri" data-selected={c.id === selected}
                className={`cursor-pointer ${c.id === selected ? 'bg-yellow/25' : inView ? 'bg-green-soft/60' : ''} hover:bg-green-soft`}>
                <td className="td text-slate-light">{i + 1}</td>
                <td className="td text-right">{c.start_time.toFixed(4)}</td>
                <td className="td text-right">{c.end_time.toFixed(4)}</td>
                <td className="td text-right">{((c.end_time - c.start_time) * 1000).toFixed(1)}</td>
                <td className="td text-right">{(c.low_freq / 1000).toFixed(1)}</td>
                <td className="td text-right">{(c.high_freq / 1000).toFixed(1)}</td>
                <td className="td"><i>{c.species}</i></td>
                <td className="td">{c.grp}</td>
                <td className={`td text-right ${low ? 'text-orange-600 dark:text-orange-400' : ''}`}><Bar p={c.det_prob} />{c.det_prob.toFixed(3)}</td>
                <td className="td text-right">{c.class_prob.toFixed(3)}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

// Version téléphone : une carte compacte par cri (les 10 colonnes ne tiennent pas sur 375 px)
function CallsCards({ calls, selected, t0, t1, onPick }) {
  const box = useScrollToSelected(selected)
  return (
    <div className="md:hidden grid gap-2">
      <p className="text-xs text-slate-light flex items-center gap-1.5">
        Début · durée · fréquences, puis espèce proposée et confiance du cri
        <Help text="Début : instant du cri dans le fichier. Durée en millisecondes (pipistrelle 3 à 8 ms, rhinolophe jusqu'à 50 ms). Fréquences basse → haute en kHz. La barre = score du modèle « c'est un cri de chauve-souris » (orange sous 0,5 : à vérifier). Le pourcentage à droite de l'espèce = score de l'espèce, à prendre avec beaucoup de recul." />
      </p>
      <ul ref={box} className="card divide-y divide-line max-h-[28rem] overflow-auto">
        {calls.map((c, i) => {
          const inView = c.end_time >= t0 && c.start_time <= t1
          const low = c.det_prob < 0.5
          return (
            <li key={c.id} data-selected={c.id === selected}>
              <button onClick={() => onPick(c)}
                className={`w-full text-left px-3 py-2 grid gap-0.5 ${c.id === selected ? 'bg-yellow/25' : inView ? 'bg-green-soft/60' : ''}`}>
                <span className="flex items-baseline gap-2 text-sm tabular-nums">
                  <span className="text-slate-light text-xs w-7">#{i + 1}</span>
                  <b className="font-medium">{c.start_time.toFixed(3)} s</b>
                  <span className="text-slate-light">· {((c.end_time - c.start_time) * 1000).toFixed(1)} ms · {(c.low_freq / 1000).toFixed(0)}–{(c.high_freq / 1000).toFixed(0)} kHz</span>
                </span>
                <span className="flex items-center gap-2 text-sm pl-9">
                  <span className="flex-1 min-w-0 truncate"><i>{c.species}</i> <span className="text-slate-light text-xs">{Math.round(c.class_prob * 100)} %</span></span>
                  <span className={`tabular-nums text-xs whitespace-nowrap ${low ? 'text-orange-600 dark:text-orange-400' : ''}`}><Bar p={c.det_prob} />{c.det_prob.toFixed(2)}</span>
                </span>
              </button>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

// Barre de confiance : verte, orange si < 0,5 (à vérifier)
function Bar({ p }) {
  return <span className={`inline-block h-2 rounded-sm align-middle mr-2 ${p < 0.5 ? 'bg-orange-400' : 'bg-green'}`} style={{ width: Math.round(p * 48) }} />
}

// ---------- Petits utilitaires ----------

function countBy(list, key) {
  const out = {}
  for (const x of list) out[key(x)] = (out[key(x)] || 0) + 1
  return out
}

// 3,25 → « 3,25 s » ; 75 → « 1 min 15,00 s » (les nuits entières se comptent en heures)
function fmtT(s) {
  if (s < 60) return `${s.toFixed(2).replace('.', ',')} s`
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), r = (s % 60).toFixed(1).replace('.', ',')
  return h ? `${h} h ${String(m).padStart(2, '0')} min ${r} s` : `${m} min ${r} s`
}

// Renvoie `value`, mais seulement une fois qu'elle n'a pas bougé pendant `delay` ms
function useDebounced(value, delay) {
  const [v, setV] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setV(value), delay)
    return () => clearTimeout(t)
  }, [value, delay])
  return v
}
