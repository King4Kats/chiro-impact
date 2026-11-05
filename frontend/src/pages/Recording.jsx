/*
 * ============================================================================
 * Recording.jsx — la page d'UN enregistrement (adresse « /recordings/:id »)
 * ============================================================================
 *
 * RÔLE DE LA PAGE
 *   Montrer en détail ce que BatDetect2 a trouvé dans un fichier WAV :
 *     - un en-tête (site, phase, date, durée, fréquence d'échantillonnage) ;
 *     - quatre tuiles de chiffres (cris, contacts, groupes, durée) ;
 *     - le spectrogramme, navigable : fenêtres de 0,5 à 5 s, flèches, saut au
 *       cri suivant, frise de tout le fichier, plein écran, écoute ralentie ×10 ;
 *     - un curseur de seuil de confiance, qui masque les cris sous la valeur
 *       choisie (affichage seulement : les chiffres de la campagne restent à 0,3) ;
 *     - les espèces proposées et la liste de tous les cris.
 *   Cliquer un cri dans la liste zoome le spectrogramme dessus et le surligne en jaune.
 *
 * DONNÉES DEMANDÉES À L'API (voir frontend/src/api.js)
 *   - api.recording(id)     → GET  /api/recordings/{id} : le fichier et tous ses cris gardés (score ≥ 0,1)
 *   - api.reprocess(id)     → POST /api/recordings/{id}/reprocess : relancer une analyse en erreur
 *   - api.spectrogramUrl(…) → adresse de l'image PNG du spectrogramme, dessinée par le serveur
 *                             pour la fenêtre affichée, à la taille exacte du cadre
 *   - api.audioUrl(…)       → adresse du son de la fenêtre affichée, ralenti 10 fois
 *   Les deux dernières ne font pas de requête elles-mêmes : elles fabriquent
 *   une adresse, que le navigateur charge ensuite via <img> ou new Audio().
 *
 * SOMMAIRE DES COMPOSANTS ET FONCTIONS DU FICHIER
 *   - Recording           : la page entière (export par défaut).
 *   - Listen              : bouton « Écouter ×10 ».
 *   - Tile                : une tuile de chiffre avec sa bulle d'aide.
 *   - Spectrogram         : l'image du spectrogramme, redemandée quand le cadre change de taille.
 *   - Timeline            : la frise de tout le fichier, sous le spectrogramme.
 *   - COLS                : titres et bulles d'aide des colonnes du tableau des cris.
 *   - useScrollToSelected : hook maison qui fait défiler la liste jusqu'au cri sélectionné.
 *   - CallsTable          : la liste des cris en tableau (à partir de 768 px).
 *   - CallsCards          : la liste des cris en cartes (téléphone).
 *   - Bar                 : petite barre de confiance colorée.
 *   - countBy, fmtT       : utilitaires de comptage et d'affichage du temps.
 *   - useDebounced        : hook maison qui attend qu'une valeur se stabilise.
 *
 * RAPPEL SUR TAILWIND
 *   Les classes (« grid gap-3 text-sm »…) sont des petits styles Tailwind.
 *   Préfixes de largeur d'écran : sm: ≥ 640 px, md: ≥ 768 px, lg: ≥ 1024 px,
 *   xl: ≥ 1280 px. `dark:` = seulement en thème sombre. `card`, `btn`, `th`,
 *   `td`… sont des raccourcis maison définis dans src/index.css.
 */

// --- Imports ---
// Les hooks React utilisés ici (chacun est expliqué la première fois qu'il sert) :
// useState, useEffect, useCallback, useMemo et useRef.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
// Link : lien interne sans rechargement de page. useParams : lit le `:id` de l'adresse.
import { Link, useParams } from 'react-router-dom'
// api : requêtes au serveur. phaseLabel : 'apres' → 'Après' (libellé avec accent).
import { api, phaseLabel } from '../api'
import Help from '../components/Help'
// Fonctions de mise en forme partagées avec la page d'une campagne.
import { fmtDate, fmtDur } from './Campaign'
// useTheme : donne le thème actuel ('light' ou 'dark'), pour dessiner le spectrogramme aux bonnes couleurs.
import { useTheme } from '../theme'

// --- Réglages de la page ---
// Constantes en MAJUSCULES regroupées en haut : on les retrouve et on les change facilement.
const ZOOMS = [0.5, 1, 2, 5]   // largeurs de fenêtre proposées, en secondes (5 s = maximum du serveur)
const DEFAULT_ZOOM = 1         // 1 s : les cris (3 à 50 ms) restent lisibles
const FOCUS_ZOOM = 0.5         // clic sur un cri : on zoome à 0,5 s autour de lui
const CONTACT_WINDOW = 5       // même règle que le backend : 1 contact = tranche de 5 s avec au moins un cri

// Page de détail d'un enregistrement : spectrogramme navigable (zoom, plein écran, écoute),
// seuil de confiance, espèces, liste des cris.
export default function Recording() {
  // useParams() lit l'adresse : pour « /recordings/12 » on obtient { id: '12' }.
  // `const { id } = …` est une déstructuration : on récupère directement la clé `id`.
  const { id } = useParams()

  // --- L'état de la page ---
  // useState garde une valeur en mémoire entre deux affichages. Il renvoie
  // [valeur, fonctionPourLaChanger]. Appeler cette fonction (setRec, setT0…)
  // change la valeur ET redessine la page : c'est un « re-rendu ».
  const [rec, setRec] = useState(null)           // l'enregistrement et ses cris (null tant que pas chargé)
  const [error, setError] = useState('')         // message d'erreur éventuel
  const [thr, setThr] = useState(0.3)            // seuil de confiance choisi avec le curseur
  const [t0, setT0] = useState(0)                // début de la fenêtre affichée, en secondes
  const [zoom, setZoom] = useState(DEFAULT_ZOOM) // largeur de fenêtre choisie, en secondes
  const [selected, setSelected] = useState(null) // id du cri cliqué (surligné partout)
  const [full, setFull] = useState(false)        // spectrogramme en plein écran
  const { theme } = useTheme()                    // le spectrogramme suit le thème clair / sombre
  // useRef crée une « boîte » qui garde une valeur SANS provoquer de re-rendu
  // quand elle change. Ici on y range l'élément HTML du bloc spectrogramme
  // (grâce à `ref={specCard}` plus bas), pour pouvoir le passer en plein écran.
  // On y accède avec specCard.current.
  const specCard = useRef(null)

  // --- Chargement de l'enregistrement ---
  // api.recording(id) renvoie une promesse (une réponse qui arrivera plus tard).
  // .then(setRec) range la réponse dans l'état ; .catch affiche l'erreur.
  // useCallback(fonction, [id]) garde la MÊME fonction tant que `id` ne change
  // pas. C'est utile parce que `load` est dans les dépendances des useEffect
  // ci-dessous : une nouvelle fonction à chaque affichage les ferait se relancer sans arrêt.
  const load = useCallback(() => {
    api.recording(id).then(setRec).catch((e) => setError(e.message))
  }, [id])
  // useEffect exécute du code APRÈS l'affichage. Son 2e argument, le « tableau
  // de dépendances », dit QUAND le relancer : ici à chaque fois que `load`
  // change, c'est-à-dire quand on arrive sur un autre enregistrement.
  useEffect(() => { load() }, [load])

  // Tant que l'analyse tourne, on recharge toutes les 3 s.
  // `rec && (…)` : si rec est encore null, working vaut null (« faux ») au lieu de planter.
  const working = rec && (rec.status === 'pending' || rec.status === 'processing')
  useEffect(() => {
    if (!working) return
    const t = setInterval(load, 3000)
    // La fonction renvoyée est la « fonction de nettoyage » : React l'appelle
    // avant de relancer l'effet, ou quand on quitte la page. Elle arrête le
    // minuteur, sinon il continuerait à tourner pour rien.
    return () => clearInterval(t)
  }, [working, load])

  // Le spectrogramme est une image calculée par le serveur : on attend que le curseur
  // se stabilise (300 ms) avant de la redemander, pour ne pas en générer une à chaque cran.
  // (La liste des cris, elle, suit `thr` immédiatement : elle est calculée dans le navigateur.)
  const imgThr = useDebounced(thr, 300)

  // Cris au-dessus du seuil, triés dans le temps.
  // useMemo(calcul, [dépendances]) garde le résultat en mémoire et ne refait le
  // calcul que si `rec` ou `thr` change. Un fichier d'une nuit entière peut
  // contenir beaucoup de cris : inutile de refiltrer et retrier à chaque
  // re-rendu (par exemple à chaque déplacement de la fenêtre).
  // `rec?.calls || []` : le `?.` (chaînage optionnel) évite une erreur quand rec
  // est null ; `|| []` donne alors un tableau vide. .filter garde les cris
  // au-dessus du seuil, .sort les range par instant de début.
  const calls = useMemo(
    () => (rec?.calls || []).filter((c) => c.det_prob > thr).sort((a, b) => a.start_time - b.start_time),
    [rec, thr],
  )

  // --- Calcul de la fenêtre affichée ---
  // duration : durée totale du fichier (0 tant qu'on ne la connaît pas).
  // span     : largeur réelle de la fenêtre ; jamais plus que le fichier lui-même
  //            (fichier de 0,8 s avec un zoom de 2 s → fenêtre de 0,8 s).
  // t1       : fin de la fenêtre, sans dépasser la fin du fichier.
  // maxT0    : début de fenêtre le plus tardif possible (la fenêtre colle alors à la fin).
  // clampT0  : « coince » un instant entre 0 et maxT0, pour ne jamais sortir du fichier.
  const duration = rec?.duration || 0
  const span = Math.min(zoom, duration || zoom)
  const t1 = Math.min(t0 + span, duration || t0 + span)
  const maxT0 = Math.max(0, duration - span)
  const clampT0 = useCallback((t) => Math.min(Math.max(0, t), maxT0), [maxT0])

  // À l'ouverture : si le début du fichier est silencieux, on se place directement sur le premier cri.
  // `positioned` est un useRef qui sert de drapeau « déjà fait » : on ne veut
  // se placer qu'UNE fois, pas à chaque re-rendu (sinon on ne pourrait plus
  // revenir au début). Modifier un ref ne redessine pas la page.
  // On attend la fin de l'analyse (status 'done') pour avoir les cris.
  // `span * 0.1` : on laisse un peu de marge à gauche du premier cri.
  const positioned = useRef(false)
  useEffect(() => {
    if (positioned.current || !rec || rec.status !== 'done') return
    positioned.current = true
    const first = calls[0]
    if (first && first.start_time > span) setT0(clampT0(first.start_time - span * 0.1))
  }, [rec, calls, span, clampT0])

  // Changer de zoom en gardant le même centre.
  // On calcule le centre de la fenêtre actuelle, puis le nouveau début pour que
  // la nouvelle fenêtre (largeur ns) soit centrée au même endroit, sans sortir du fichier.
  const changeZoom = useCallback((z) => {
    const center = t0 + span / 2
    const ns = Math.min(z, duration || z)
    setZoom(z)
    setT0(Math.min(Math.max(0, center - ns / 2), Math.max(0, duration - ns)))
  }, [t0, span, duration])

  // Passage suivant / précédent : premier cri après la fenêtre (ou avant), pour sauter les silences.
  // .find renvoie le premier élément qui vérifie la condition (ou undefined).
  // Pour le précédent, on parcourt la liste à l'envers : `[...calls]` en fait
  // une copie (« ... » étale les éléments dans un nouveau tableau), car
  // .reverse() modifierait sinon le tableau d'origine.
  // goTo : `c && …` ne fait rien quand aucun cri n'a été trouvé.
  const nextCall = calls.find((c) => c.start_time > t1)
  const prevCall = [...calls].reverse().find((c) => c.end_time < t0)
  const goTo = useCallback((c) => c && setT0(clampT0(c.start_time - span * 0.1)), [clampT0, span])

  // Plein écran : vrai plein écran du navigateur quand il existe, sinon (iPhone) le bloc couvre la page.
  // L'API plein écran du navigateur : element.requestFullscreen() pour entrer,
  // document.exitFullscreen() pour sortir, document.fullscreenElement pour
  // savoir si un élément est en plein écran. Certains navigateurs ne l'ont pas :
  // `?.()` n'appelle la fonction que si elle existe, et `.catch(() => {})`
  // ignore un refus. Dans tous les cas, l'état `full` passe à true, et les
  // classes CSS « fixed inset-0 » (plus bas) font couvrir toute la fenêtre au bloc.
  const toggleFull = useCallback(() => {
    if (full) {
      if (document.fullscreenElement) document.exitFullscreen?.()
      setFull(false)
    } else {
      setFull(true)
      specCard.current?.requestFullscreen?.().catch(() => {})
    }
  }, [full])
  // Si on quitte le plein écran par le navigateur lui-même (touche Échap,
  // geste sur tablette…), notre état `full` doit suivre. On écoute l'événement
  // 'fullscreenchange' du document. Tableau de dépendances vide : l'écouteur
  // est posé une seule fois, et la fonction de nettoyage le retire quand on quitte la page.
  useEffect(() => {
    const onChange = () => { if (!document.fullscreenElement) setFull(false) }
    document.addEventListener('fullscreenchange', onChange)
    return () => document.removeEventListener('fullscreenchange', onChange)
  }, [])
  useEffect(() => {
    // Sans vrai plein écran, la page ne doit pas défiler sous le spectrogramme
    // (overflow: hidden sur <body> bloque le défilement ; '' rend la valeur normale).
    document.body.style.overflow = full ? 'hidden' : ''
    return () => { document.body.style.overflow = '' }
  }, [full])

  // Raccourcis clavier : ← → fenêtre précédente / suivante, + − zoom, F plein écran, Échap quitte.
  // On écoute 'keydown' (touche enfoncée) sur toute la fenêtre. e.key contient
  // le nom de la touche ('ArrowRight', '+', 'f'…).
  // Les dépendances listent toutes les valeurs utilisées dans onKey : quand
  // l'une change, React retire l'ancien écouteur (nettoyage) et en pose un
  // nouveau, qui voit les valeurs à jour.
  useEffect(() => {
    function onKey(e) {
      // On ne détourne pas les touches quand on tape dans un champ (le curseur
      // de seuil, par exemple), ni les raccourcis du navigateur (Ctrl, Cmd, Alt).
      // closest(...) regarde si l'élément visé est (ou se trouve dans) un champ de saisie.
      if (e.target.closest?.('input, select, textarea') || e.ctrlKey || e.metaKey || e.altKey) return
      // Position du zoom actuel dans ZOOMS : zoomer = prendre la valeur d'avant
      // (fenêtre plus étroite), dézoomer = celle d'après.
      // `i > 0 && changeZoom(…)` : n'appelle changeZoom que si on n'est pas déjà au bout de la liste.
      const i = ZOOMS.indexOf(zoom)
      if (e.key === 'ArrowRight') setT0(clampT0(t0 + span))
      else if (e.key === 'ArrowLeft') setT0(clampT0(t0 - span))
      else if (e.key === '+' || e.key === '=') i > 0 && changeZoom(ZOOMS[i - 1])
      else if (e.key === '-') i < ZOOMS.length - 1 && changeZoom(ZOOMS[i + 1])
      else if (e.key === 'f' || e.key === 'F') toggleFull()
      else if (e.key === 'Escape' && full) toggleFull()
      // Touche non gérée : on sort sans rien bloquer.
      else return
      // Touche gérée : on empêche l'action par défaut du navigateur
      // (par exemple les flèches qui font défiler la page).
      e.preventDefault()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [t0, span, zoom, full, clampT0, changeZoom, toggleFull])

  // --- Cas particuliers : erreur ou chargement ---
  // Ces `return` anticipés viennent APRÈS tous les hooks : React exige que les
  // hooks soient appelés dans le même ordre à chaque affichage.
  if (error) return <p className="text-red-600 dark:text-red-400">{error}</p>
  if (!rec) return <p className="text-slate-light">Chargement…</p>

  // Clic sur un cri : on zoome à 0,5 s et on centre la fenêtre dessus.
  // Math.min(zoom, FOCUS_ZOOM) : si on est déjà plus zoomé que 0,5 s, on garde ce zoom.
  // Le milieu du cri est (début + fin) / 2 ; la fenêtre est placée pour qu'il soit au centre.
  function focusCall(c) {
    setSelected(c.id)
    const z = Math.min(zoom, FOCUS_ZOOM)
    const ns = Math.min(z, duration)
    setZoom(z)
    setT0(Math.min(Math.max(0, (c.start_time + c.end_time) / 2 - ns / 2), Math.max(0, duration - ns)))
  }

  // Indicateurs calculés côté navigateur pour suivre le seuil en direct.
  // Contacts : pour chaque cri on calcule le numéro de sa tranche de 5 s
  // (Math.floor(début / 5) : 0 pour 0–5 s, 1 pour 5–10 s…). Un Set ne garde
  // que les valeurs distinctes : sa taille (.size) = nombre de tranches qui
  // contiennent au moins un cri = nombre de contacts.
  // species / groups : objets { nom: nombre de cris } (voir countBy en bas du fichier).
  const nContacts = new Set(calls.map((c) => Math.floor(c.start_time / CONTACT_WINDOW))).size
  const species = countBy(calls, (c) => c.species)
  const groups = countBy(calls, (c) => c.grp)

  return (
    <div className="grid gap-5 sm:gap-6">
      {/* En-tête : lien retour, nom du fichier, puis une ligne d'informations.
          (Dans le JSX, un commentaire s'écrit entre accolades comme celui-ci.) */}
      <div className="min-w-0">
        {/* Template literal (backticks + ${…}) : construit l'adresse de la campagne, ex. "/campaigns/3". */}
        <Link to={`/campaigns/${rec.campaign_id}`} className="text-sm text-slate-light hover:text-slate">← Retour à la campagne</Link>
        <h2 className="text-xl sm:text-2xl font-bold break-all">{rec.filename}</h2>
        <p className="text-slate-light text-sm">
          {/* Site (+ « témoin » si c'est le site de contrôle) et phase. */}
          {rec.site_name}{rec.is_control ? ' (témoin)' : ''} · phase <b className="text-slate font-medium">{phaseLabel(rec.phase)}</b>
          {/* Date, seulement si elle est connue (rendu conditionnel avec &&).
              <>…</> est un « fragment » : il regroupe plusieurs morceaux sans ajouter de balise.
              Ternaire `condition ? A : B` : si l'heure vient du nom du fichier, on prévient
              en orange que le fuseau n'est pas vérifié ; sinon on indique « heure française ».
              L'attribut title s'affiche en bulle au survol. */}
          {rec.recorded_at && <> · {fmtDate(rec.recorded_at)}{rec.time_source === 'nom du fichier'
            ? <span className="text-orange-600 dark:text-orange-400" title="Heure lue dans le nom du fichier : son fuseau est inconnu. L'AudioMoth nomme ses fichiers en UTC par défaut (2 h de moins que l'heure française en été)."> (heure du nom de fichier, fuseau non vérifié)</span>
            : <span title={`Heure lue dans le fichier (${rec.time_source}), convertie en heure française`}> (heure française)</span>}</>}
          {/* Durée puis fréquence d'échantillonnage (en Hz dans la base, affichée en kHz). */}
          {' · '}{fmtDur(rec.duration)}{rec.samplerate ? ` · ${rec.samplerate / 1000} kHz` : ''}
        </p>
      </div>

      {/* Bandeaux d'état : analyse en cours (avec pourcentage), ou échec avec un bouton pour relancer. */}
      {working && <p className="text-sm bg-yellow/20 px-3 py-2 rounded-sm">Analyse en cours{rec.progress > 0 ? ` (${Math.round(rec.progress * 100)} %)` : ''}… la page se mettra à jour toute seule.</p>}
      {rec.status === 'error' && (
        <div className="text-sm bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-300 px-3 py-2 rounded-sm flex flex-wrap items-center gap-3">
          <span className="flex-1 min-w-0 break-words">L’analyse a échoué : {rec.error || 'erreur inconnue'}</span>
          {/* Relance l'analyse côté serveur, puis recharge la page (qui passera en « analyse en cours »). */}
          <button className="btn btn-ghost" onClick={() => api.reprocess(rec.id).then(load)}>Relancer l’analyse</button>
        </div>
      )}

      {/* Tuiles : 2 colonnes sur téléphone, 4 à partir de lg: (1024 px).
          Les chiffres « Cris » et « Contacts » suivent le seuil du curseur.
          thr.toFixed(2).replace('.', ',') : 0.3 → « 0,30 » (virgule à la française). */}
      <div className="grid gap-3 grid-cols-2 lg:grid-cols-4">
        <Tile label="Cris détectés" value={calls.length}
          help={`Nombre de cris dont le score dépasse le seuil affiché (${thr.toFixed(2).replace('.', ',')}). ${rec.calls.length} cris gardés au total (score ≥ 0,1). Un cri n'est pas une chauve-souris : une chauve-souris qui passe émet des dizaines de cris.`} />
        <Tile label="Contacts" value={nContacts}
          help={`Tranches de 5 secondes contenant au moins un cri (au seuil affiché, ${thr.toFixed(2).replace('.', ',')}). C'est l'unité de mesure de l'activité : 30 cris en 2 secondes = 1 seul contact. La synthèse de la campagne compte toujours au seuil 0,3.`} />
        {/* Object.keys(groups) = la liste des noms de groupes ; .length = combien il y en a. */}
        <Tile label="Groupes" value={Object.keys(groups).length}
          help="Nombre de groupes d'espèces différents (Pipistrelles, Myotis, Noctules / Sérotines, Oreillards, Barbastelle, Rhinolophes). Le modèle est fiable à ce niveau, beaucoup moins à l'espèce." />
        <Tile label="Audio analysé" value={fmtDur(rec.duration)}
          help="Durée totale du fichier. Pour l'activité, on divise les contacts par ce temps d'écoute (contacts par heure)." />
      </div>

      {/* Spectrogramme (normal ou plein écran).
          ref={specCard} : React range cet élément HTML dans specCard.current (pour requestFullscreen).
          Les classes changent selon `full` : en plein écran, `fixed inset-0 z-50` colle le bloc
          aux 4 bords de la fenêtre, au-dessus de tout le reste. */}
      <div ref={specCard}
        className={full
          ? 'fixed inset-0 z-50 bg-surface flex flex-col gap-2 p-2 sm:p-4'
          : 'card p-2 sm:p-3 flex flex-col gap-2'}>
        {/* Barre de titre : titre + aide à gauche (mr-auto pousse le reste à droite),
            bouton d'écoute (seulement une fois l'analyse finie) et bouton plein écran.
            .toFixed(3) : instants arrondis au millième de seconde dans l'adresse. */}
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="font-bold flex items-center gap-2 mr-auto">
            Spectrogramme
            <Help text="Une image du son : le temps de gauche à droite, la fréquence (hauteur du son, en kHz) de bas en haut, le noir = l'intensité. Chaque cadre est un cri détecté par le modèle (qui peut se tromper : insectes, bruits). Cadres verts : score ≥ 0,5 ; orange : sous 0,5, à vérifier ; jaune : le cri sélectionné. Zoom 0,5 s pour bien voir la forme des cris, 5 s pour repérer les passages. Clavier : ← → pour avancer, + − pour zoomer, F pour le plein écran." />
          </h3>
          {rec.status === 'done' && <Listen src={api.audioUrl(rec.id, t0.toFixed(3), t1.toFixed(3))} />}
          {/* aria-pressed : indique aux lecteurs d'écran que ce bouton est un interrupteur (activé ou non). */}
          <button className="btn btn-ghost py-1 px-3" onClick={toggleFull} aria-pressed={full} title="Plein écran (touche F)">
            {full ? '✕ Quitter' : '⛶ Plein écran'}
          </button>
        </div>

        {/* Navigation + zoom */}
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          {/* Fenêtre précédente / suivante, avec l'intervalle affiché entre les deux flèches.
              Les boutons sont désactivés (disabled) au début et à la fin du fichier. */}
          <div className="flex items-center gap-1">
            <button className="btn btn-ghost py-1 px-2.5" disabled={t0 <= 0} onClick={() => setT0(clampT0(t0 - span))} aria-label="Fenêtre précédente">←</button>
            <span className="text-sm tabular-nums text-slate-light text-center min-w-[9.5rem]">
              {fmtT(t0)} – {fmtT(t1)} <span className="hidden sm:inline">sur {fmtT(duration)}</span>
            </span>
            <button className="btn btn-ghost py-1 px-2.5" disabled={t0 >= maxT0} onClick={() => setT0(clampT0(t0 + span))} aria-label="Fenêtre suivante">→</button>
          </div>
          {/* Saut au cri précédent / suivant situé hors de la fenêtre (désactivé s'il n'y en a pas). */}
          <div className="flex items-center gap-1 text-sm">
            <button className="btn btn-ghost py-1 px-2.5" disabled={!prevCall} onClick={() => goTo(prevCall)} title="Cri précédent hors de la fenêtre">⏮</button>
            <button className="btn btn-ghost py-1 px-2.5" disabled={!nextCall} onClick={() => goTo(nextCall)} title="Cri suivant hors de la fenêtre">⏭</button>
            <Help text="Sauter au passage précédent / suivant : la fenêtre se place sur le prochain cri détecté, en passant les silences. Pratique sur une nuit entière." />
          </div>
          {/* Boutons de zoom. On ne propose que les largeurs utiles : pas de fenêtre de 5 s
              pour un fichier de 1,5 s (Math.max garantit qu'au moins 0,5 s reste proposé).
              .map + key : un bouton par largeur, `key={z}` identifie chaque bouton.
              first:border-l-0 : pas de bordure gauche sur le premier bouton du groupe. */}
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

        {/* L'image elle-même, ou un message tant que l'analyse n'est pas finie.
            On passe à Spectrogram une FONCTION `url(size)` plutôt qu'une adresse toute
            faite : c'est Spectrogram qui connaît la taille de son cadre, il l'appelle
            avec cette taille pour obtenir l'adresse de l'image. */}
        {rec.status === 'done' ? (
          <Spectrogram full={full}
            url={(size) => api.spectrogramUrl(rec.id, t0.toFixed(3), t1.toFixed(3), imgThr, selected, size, theme)}
            alt={`Spectrogramme de ${rec.filename} entre ${t0.toFixed(2)} et ${t1.toFixed(2)} s`} />
        ) : (
          <div className="h-48 grid place-items-center text-slate-light text-sm bg-page rounded">Le spectrogramme apparaîtra une fois l’analyse terminée.</div>
        )}
        {/* Frise de tout le fichier, seulement s'il est plus long que la fenêtre.
            onSeek reçoit l'instant touché et centre la fenêtre dessus. */}
        {duration > span && <Timeline duration={duration} t0={t0} span={span} calls={calls} selected={selected} onSeek={(t) => setT0(clampT0(t - span / 2))} />}

        {/* Seuil : dans le bloc du spectrogramme, car il change les cadres affichés.
            <input type="range"> = un curseur. Sa valeur arrive en texte (e.target.value),
            d'où parseFloat pour la transformer en nombre.
            order-last sm:order-none : sur téléphone le curseur passe en dernier, sur sa propre ligne. */}
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm pt-1">
          <label htmlFor="thr" className="font-medium whitespace-nowrap">Seuil de confiance <span className="tabular-nums">{thr.toFixed(2)}</span></label>
          <input id="thr" type="range" min="0.1" max="0.95" step="0.05" value={thr}
            onChange={(e) => setThr(parseFloat(e.target.value))} className="w-full sm:w-52 accent-green-dark order-last sm:order-none" />
          <Help text="Le modèle donne un score de 0 à 1 à chaque cri détecté. Ce curseur ne change que l'AFFICHAGE de cette page. L'analyse garde les cris dès 0,1 : en descendant sous 0,3, tu vois les cris faibles (cris lointains… ou bruits) pour vérifier. Tous les chiffres de la campagne (cris, contacts, groupes, synthèse) sont calculés à 0,3, quelle que soit la position du curseur. 0,3 est un choix (la valeur des exemples de BatDetect2), pas un réglage d'origine du modèle." />
          <span className="tabular-nums text-slate-light">{calls.length} cris sur {rec.calls.length}</span>
        </div>
      </div>

      {/* Espèces proposées.
          Object.entries(species) transforme { 'Pipistrellus pipistrellus': 12, … } en
          [['Pipistrellus pipistrellus', 12], …] ; on trie par nombre décroissant
          (b[1] - a[1]) puis on affiche une étiquette par espèce. */}
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

      {/* Liste des cris : tableau sur ordinateur / tablette, cartes sur téléphone.
          Les deux versions sont rendues ; le CSS (md:hidden / hidden md:block) n'en montre qu'une.
          onPick={focusCall} : cliquer un cri appelle focusCall avec ce cri. */}
      {calls.length === 0
        ? <div className="card p-6 text-slate-light">Aucun cri au-dessus de ce seuil.</div>
        : <>
            <CallsTable calls={calls} selected={selected} t0={t0} t1={t1} onPick={focusCall} />
            <CallsCards calls={calls} selected={selected} t0={t0} t1={t1} onPick={focusCall} />
          </>}

      {/* Rappel en bas de page sur le rôle du curseur. */}
      <p className="text-sm border-l-4 border-yellow bg-surface px-4 py-3 rounded-r max-w-3xl">
        Touche un cri dans la liste pour zoomer dessus dans le spectrogramme. L’analyse garde les cris dont le score dépasse 0,1 ;
        le curseur ne fait que masquer ceux sous la valeur choisie. Les chiffres de la campagne sont toujours calculés à 0,3.
      </p>
    </div>
  )
}

// ---------- Morceaux de la page ----------

// Bouton d'écoute : la fenêtre affichée, rejouée 10 fois plus lentement (45 kHz → 4,5 kHz, audible).
// Le ralentissement est fait par le serveur (api.audioUrl, paramètre slow=10).
function Listen({ src }) {
  // Le lecteur audio est gardé dans un ref : on doit pouvoir l'arrêter plus tard,
  // et le changer ne doit pas redessiner le composant.
  const audio = useRef(null)
  const [playing, setPlaying] = useState(false)
  // Effet dont la seule utilité est sa fonction de nettoyage : quand le bouton
  // disparaît (on quitte la page), on coupe le son.
  useEffect(() => () => audio.current?.pause(), [])
  // Quand `src` change (la fenêtre a bougé), on arrête la lecture en cours :
  // elle ne correspondrait plus à ce qui est affiché.
  useEffect(() => { audio.current?.pause(); setPlaying(false) }, [src]) // la fenêtre a changé
  // Lecture / arrêt. new Audio(src) crée un lecteur qui télécharge le son.
  // play() renvoie une promesse : elle échoue par exemple si le navigateur
  // bloque la lecture ; on remet alors le bouton à l'état « arrêté ».
  // onended : quand le son est fini, le bouton revient à « Écouter ».
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

// Une tuile de chiffre : petit libellé + bulle d'aide en haut, grand nombre en dessous.
// Les props `label`, `value` et `help` sont récupérées par déstructuration.
// `truncate` coupe la valeur avec « … » si elle est trop longue pour la tuile.
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
  const box = useRef(null)              // le cadre HTML, pour mesurer sa taille
  const [size, setSize] = useState(null) // { w, h, dpr } mesurés (null avant la 1re mesure)

  // --- Mesure du cadre ---
  // Relancée quand on entre ou sort du plein écran (`full` change).
  useEffect(() => {
    const el = box.current
    if (!el) return
    const measure = () => {
      // clientWidth / clientHeight : taille intérieure de l'élément, en pixels CSS.
      const w = el.clientWidth
      // Normal : hauteur proportionnelle à la largeur (entre 240 et 460 px) ; plein écran : toute la place
      const h = full ? el.clientHeight : Math.round(Math.min(460, Math.max(240, w * 0.34)))
      // devicePixelRatio : nombre de pixels physiques de l'écran par pixel CSS
      // (1 sur un écran classique, 2 ou 3 sur un téléphone récent). On demande
      // une image plus détaillée en conséquence pour qu'elle reste nette,
      // mais plafonnée à 2 pour ne pas générer des images trop lourdes.
      const dpr = Math.min(window.devicePixelRatio || 1, 2)
      // Arrondi à 20 px : un petit redimensionnement ne redemande pas d'image
      // (et le dpr est arrondi au quart : 1, 1.25, 1.5…).
      setSize({ w: Math.round(w / 20) * 20, h: Math.round(h / 20) * 20, dpr: Math.round(dpr * 4) / 4 })
    }
    measure()
    // ResizeObserver : un outil du navigateur qui prévient quand un élément
    // change de taille (fenêtre redimensionnée, téléphone tourné…).
    // Pendant un redimensionnement, il se déclenche très souvent : on attend
    // 150 ms sans changement avant de remesurer (le minuteur est rangé dans
    // ro.t, et chaque nouvel appel annule le précédent).
    const ro = new ResizeObserver(() => { clearTimeout(ro.t); ro.t = setTimeout(measure, 150) })
    ro.observe(el)
    // Nettoyage : on arrête d'observer et on annule un éventuel minuteur en attente.
    return () => { ro.disconnect(); clearTimeout(ro.t) }
  }, [full])

  // --- Adresse de l'image et état du chargement ---
  // src : l'adresse de l'image, seulement si la taille est connue et non nulle.
  // loaded : l'adresse de la dernière image finie de charger. Tant que
  //          loaded !== src, une nouvelle image est en route → on affiche « Calcul… ».
  // failed : le serveur n'a pas pu fournir l'image ; remis à false à chaque nouvelle adresse.
  const src = size && size.w > 0 && size.h > 0 ? url(size) : null
  const [loaded, setLoaded] = useState(null)
  const [failed, setFailed] = useState(false)
  useEffect(() => setFailed(false), [src])
  const loading = src && loaded !== src

  return (
    // En plein écran, le cadre prend toute la hauteur restante (flex-1) ; sinon
    // sa hauteur est fixée par `style` (280 px tant que la mesure n'est pas faite).
    // `style={{ … }}` : les doubles accolades = un objet JavaScript dans une prop.
    <div ref={box} className={`relative bg-page rounded overflow-hidden ${full ? 'flex-1 min-h-0' : ''}`}
      style={full ? undefined : { height: size ? size.h : 280 }}>
      {/* L'image remplit tout le cadre (absolute inset-0). onLoad / onError sont
          appelés par le navigateur quand elle a fini de charger ou a échoué. */}
      {src && <img src={src} alt={alt} className="absolute inset-0 w-full h-full object-fill"
        onLoad={() => setLoaded(src)} onError={() => { setLoaded(src); setFailed(true) }} />}
      {/* Voile semi-transparent pendant le calcul : l'ancienne image reste visible dessous. */}
      {loading && <div className="absolute inset-0 bg-surface/50 grid place-items-center text-sm text-slate-light">Calcul du spectrogramme…</div>}
      {failed && <div className="absolute inset-0 grid place-items-center text-sm text-red-700 dark:text-red-300">Impossible de générer le spectrogramme.</div>}
    </div>
  )
}

// Frise sous le spectrogramme : toute la durée du fichier, un trait par cri, la fenêtre affichée en vert pâle.
// Clic (ou toucher) = on y déplace la fenêtre. Indispensable pour les fichiers longs (une nuit entière).
// Les positions sont en pourcentage de la largeur : instant / durée × 100.
function Timeline({ duration, t0, span, calls, selected, onSeek }) {
  // Le cri sélectionné (s'il est dans la liste filtrée), pour le marquer en jaune.
  const sel = calls.find((c) => c.id === selected)
  return (
    <div className="grid gap-1">
      {/* role="slider" + aria-value… : décrit la frise comme un curseur aux lecteurs d'écran.
          onPointerDown : fonctionne à la souris, au doigt et au stylet. On calcule où
          l'on a touché : (position du pointeur − bord gauche) / largeur = fraction de
          0 à 1, multipliée par la durée = instant en secondes.
          touch-none : empêche le navigateur de faire défiler la page quand on touche la frise. */}
      <div
        role="slider" aria-label="Position dans le fichier" aria-valuemin={0} aria-valuemax={Math.round(duration)} aria-valuenow={Math.round(t0)} tabIndex={0}
        className="relative h-7 bg-page border border-line rounded-sm cursor-pointer touch-none"
        onPointerDown={(e) => { const r = e.currentTarget.getBoundingClientRect(); onSeek(((e.clientX - r.left) / r.width) * duration) }}
      >
        {/* La fenêtre affichée. Largeur minimale de 0,6 % pour rester visible sur un très long fichier. */}
        <div className="absolute inset-y-0 bg-green-soft border-x-2 border-green" style={{ left: `${(t0 / duration) * 100}%`, width: `${Math.max((span / duration) * 100, 0.6)}%` }} />
        {/* Un trait fin (w-px = 1 px) par cri. */}
        {calls.map((c) => (
          <div key={c.id} className="absolute top-1 bottom-1 w-px bg-slate/50" style={{ left: `${(c.start_time / duration) * 100}%` }} />
        ))}
        {/* Le cri sélectionné, en jaune et un peu plus épais. */}
        {sel && <div className="absolute -top-0.5 -bottom-0.5 w-0.5 bg-yellow" style={{ left: `${(sel.start_time / duration) * 100}%` }} />}
      </div>
      <p className="text-xs text-slate-light">Vue d’ensemble du fichier : chaque trait est un cri, le cadre vert la fenêtre affichée. Touche la frise pour t’y déplacer.</p>
    </div>
  )
}

// Colonnes du tableau des cris : [titre, texte de la bulle d'aide (null = pas de bulle), alignement].
// Alignement : 'r' = à droite (les nombres, pour que les chiffres s'alignent), 'l' ou '' = à gauche.
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

// Fait défiler la liste jusqu'au cri sélectionné (quand on le choisit ailleurs, ex. depuis la frise).
// C'est un « hook maison » : une fonction dont le nom commence par `use` et qui
// utilise elle-même des hooks. Elle renvoie un ref à accrocher à la boîte qui défile.
// À chaque changement de `selected`, on cherche dans la boîte la ligne marquée
// data-selected="true" et on la fait apparaître (scrollIntoView, 'nearest' = en
// bougeant le moins possible).
// offsetParent vaut null quand la boîte est cachée (display: none) : le tableau
// et les cartes existent tous les deux, mais un seul est visible ; on ne fait
// défiler que celui qu'on voit.
function useScrollToSelected(selected) {
  const box = useRef(null)
  useEffect(() => {
    const el = box.current?.querySelector('[data-selected="true"]')
    if (el && box.current.offsetParent !== null) el.scrollIntoView({ block: 'nearest' })
  }, [selected])
  return box
}

// Liste des cris en tableau (visible à partir de md: 768 px, d'où `hidden md:block`).
// max-h-[36rem] + overflow-auto : le tableau a une hauteur maximale et défile à l'intérieur.
function CallsTable({ calls, selected, t0, t1, onPick }) {
  const box = useScrollToSelected(selected)
  return (
    <div ref={box} className="hidden md:block card overflow-auto max-h-[36rem]">
      <table className="w-full text-sm">
        {/* sticky top-0 : la ligne de titres reste collée en haut quand on fait défiler le tableau. */}
        <thead className="sticky top-0 bg-surface z-10">
          <tr>
            {/* Une cellule de titre par élément de COLS ; la bulle d'aide seulement si `help` existe. */}
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
            // inView : le cri est (au moins en partie) dans la fenêtre affichée → fond vert pâle.
            // low : score sous 0,5 → chiffre en orange (à vérifier).
            const inView = c.end_time >= t0 && c.start_time <= t1
            const low = c.det_prob < 0.5
            return (
              // Toute la ligne est cliquable. data-selected sert à useScrollToSelected.
              // Couleur de fond : jaune si sélectionné, sinon vert pâle si dans la fenêtre.
              <tr key={c.id} onClick={() => onPick(c)} title="Zoomer le spectrogramme sur ce cri" data-selected={c.id === selected}
                className={`cursor-pointer ${c.id === selected ? 'bg-yellow/25' : inView ? 'bg-green-soft/60' : ''} hover:bg-green-soft`}>
                {/* Numéro (i + 1, car les index commencent à 0), instants au 1/10 000 de seconde,
                    durée en ms, fréquences converties de Hz en kHz (÷ 1000). */}
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
      {/* Légende de lecture des cartes, avec une bulle d'aide détaillée. */}
      <p className="text-xs text-slate-light flex items-center gap-1.5">
        Début · durée · fréquences, puis espèce proposée et confiance du cri
        <Help text="Début : instant du cri dans le fichier. Durée en millisecondes (pipistrelle 3 à 8 ms, rhinolophe jusqu'à 50 ms). Fréquences basse → haute en kHz. La barre = score du modèle « c'est un cri de chauve-souris » (orange sous 0,5 : à vérifier). Le pourcentage à droite de l'espèce = score de l'espèce, à prendre avec beaucoup de recul." />
      </p>
      {/* divide-y : un trait de séparation entre chaque élément de la liste. */}
      <ul ref={box} className="card divide-y divide-line max-h-[28rem] overflow-auto">
        {calls.map((c, i) => {
          const inView = c.end_time >= t0 && c.start_time <= t1
          const low = c.det_prob < 0.5
          return (
            <li key={c.id} data-selected={c.id === selected}>
              {/* Chaque carte est un <button> : cliquable au doigt et accessible au clavier. */}
              <button onClick={() => onPick(c)}
                className={`w-full text-left px-3 py-2 grid gap-0.5 ${c.id === selected ? 'bg-yellow/25' : inView ? 'bg-green-soft/60' : ''}`}>
                {/* 1re ligne : numéro, début, durée et fréquences. */}
                <span className="flex items-baseline gap-2 text-sm tabular-nums">
                  <span className="text-slate-light text-xs w-7">#{i + 1}</span>
                  <b className="font-medium">{c.start_time.toFixed(3)} s</b>
                  <span className="text-slate-light">· {((c.end_time - c.start_time) * 1000).toFixed(1)} ms · {(c.low_freq / 1000).toFixed(0)}–{(c.high_freq / 1000).toFixed(0)} kHz</span>
                </span>
                {/* 2e ligne (décalée de pl-9 pour s'aligner sous le texte) : espèce + son score
                    en pourcentage, puis la barre et le score du cri. */}
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

// Barre de confiance : verte, orange si < 0,5 (à vérifier).
// Sa largeur est proportionnelle au score : 48 px pour un score de 1.
// Dans `style`, un nombre sans unité est compris par React comme des pixels.
function Bar({ p }) {
  return <span className={`inline-block h-2 rounded-sm align-middle mr-2 ${p < 0.5 ? 'bg-orange-400' : 'bg-green'}`} style={{ width: Math.round(p * 48) }} />
}

// ---------- Petits utilitaires ----------

// Compte les éléments d'une liste selon une clé.
// `key` est une fonction qui dit quoi compter (ex. (c) => c.species).
// Résultat : un objet { valeur: nombre }, ex. { 'Myotis': 3, 'Pipistrelles': 10 }.
// `(out[k] || 0) + 1` : si la valeur n'a pas encore été vue, on part de 0.
function countBy(list, key) {
  const out = {}
  for (const x of list) out[key(x)] = (out[key(x)] || 0) + 1
  return out
}

// Instant en secondes → texte. Exemples : 3,25 → « 3,25 s » ; 75 → « 1 min 15,0 s » ;
// au-delà d'une heure (les nuits entières se comptent en heures) : 3725 → « 1 h 02 min 5,0 s ».
// padStart(2, '0') ajoute un zéro devant les minutes : 2 → '02'.
function fmtT(s) {
  if (s < 60) return `${s.toFixed(2).replace('.', ',')} s`
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), r = (s % 60).toFixed(1).replace('.', ',')
  return h ? `${h} h ${String(m).padStart(2, '0')} min ${r} s` : `${m} min ${r} s`
}

// Renvoie `value`, mais seulement une fois qu'elle n'a pas bougé pendant `delay` ms.
// Principe (« debounce ») : à chaque changement de `value`, on programme une
// mise à jour dans `delay` ms ; si `value` change encore avant, la fonction de
// nettoyage annule le minuteur précédent. Seule la dernière valeur passe.
function useDebounced(value, delay) {
  const [v, setV] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setV(value), delay)
    return () => clearTimeout(t)
  }, [value, delay])
  return v
}
