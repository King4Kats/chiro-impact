/*
 * Help.jsx — le petit bouton « ? » vert qui affiche une bulle d'explication.
 *
 * Utilisé partout dans l'appli : <Help text="explication…" />. La bulle s'ouvre au survol de la
 * souris, au clic / toucher (téléphone) ou au clavier (touche Tab), et se referme au clic
 * ailleurs, à la touche Échap, au défilement ou au redimensionnement de la fenêtre.
 *
 * Travaille avec : FestivalDates, Sites, Summary, UploadZone et les pages (Campaign, Campaigns,
 * Recording) qui l'importent ; index.css / tailwind.config.js pour les couleurs (bg-brand…).
 */
import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

// Réglages de placement, en pixels.
const MARGIN = 8   // distance minimale entre la bulle et le bord de l'écran
const GAP = 8      // distance entre le « ? » et la bulle
const WIDTH = 288  // largeur de la bulle (réduite sur petit écran)

// Le petit "?" vert : au survol (ordinateur) ou au toucher (téléphone), affiche une bulle d'explication.
// La bulle est dessinée au-dessus de toute la page (portail vers <body>) et recalée pour rester dans
// l'écran : elle n'est jamais coupée par un tableau qui défile, ni par le bord d'un téléphone.
// (La prop `align` des versions précédentes est acceptée mais n'est plus nécessaire.)
// eslint-disable-next-line no-unused-vars
export default function Help({ text, className = '', align }) {
  // État du composant :
  //  - open   : la bulle est-elle affichée ?
  //  - pinned : ouverte par un clic (alors quitter le « ? » avec la souris ne la ferme pas) ;
  //  - pos    : position calculée de la bulle (null tant qu'on ne l'a pas encore mesurée).
  const [open, setOpen] = useState(false)
  const [pinned, setPinned] = useState(false) // ouverte par un clic : reste ouverte jusqu'au clic suivant
  const [pos, setPos] = useState(null)
  // useRef : une « boîte » qui garde une valeur entre deux affichages sans provoquer de redessin.
  // Placée dans ref={…} sur une balise, React y met l'élément HTML réel (btn.current = le <button>).
  // On en a besoin pour mesurer la position du bouton et la taille de la bulle.
  const btn = useRef(null)
  const tip = useRef(null)
  // useId : fabrique un identifiant unique, stable, différent pour chaque « ? » de la page.
  // Il relie le bouton à sa bulle (aria-describedby) pour les lecteurs d'écran.
  const id = useId()

  // Calcule la position une fois la bulle affichée (on a besoin de sa hauteur réelle)
  //
  // useLayoutEffect ressemble à useEffect, mais s'exécute juste après que React a modifié la
  // page et AVANT que l'écran soit repeint. On peut donc mesurer la bulle et la déplacer sans
  // qu'on la voie clignoter au mauvais endroit. Au premier affichage, elle est posée hors écran
  // (left: -9999, voir plus bas) le temps de la mesurer.
  //
  // getBoundingClientRect() donne la position du bouton dans la fenêtre visible (left, top, bottom…).
  // Les calculs :
  //  1. largeur = 288 px, ou moins si l'écran est plus étroit ;
  //  2. bulle centrée sous le « ? », puis bornée pour ne pas sortir à gauche ni à droite ;
  //  3. en dessous si ça tient, sinon au-dessus (sauf si au-dessus ça ne tient pas non plus) ;
  //  4. `arrow` : position horizontale de la petite flèche, pour qu'elle pointe toujours vers le « ? ».
  // Dépendances [open, text] : on recalcule à chaque ouverture ou si le texte change.
  useLayoutEffect(() => {
    if (!open || !btn.current || !tip.current) return
    const b = btn.current.getBoundingClientRect()
    const w = Math.min(WIDTH, window.innerWidth - 2 * MARGIN)
    const h = tip.current.offsetHeight
    let left = b.left + b.width / 2 - w / 2
    left = Math.max(MARGIN, Math.min(left, window.innerWidth - w - MARGIN))
    // En dessous du « ? » si la place le permet, sinon au-dessus
    const below = b.bottom + GAP + h <= window.innerHeight - MARGIN || b.top - GAP - h < MARGIN
    const top = below ? b.bottom + GAP : b.top - GAP - h
    const arrow = Math.max(12, Math.min(b.left + b.width / 2 - left, w - 12))
    setPos({ left, top, width: w, below, arrow })
  }, [open, text])

  // Fermer quand on fait défiler la page, qu'on redimensionne ou qu'on clique ailleurs
  //
  // Ces écouteurs ne sont posés que pendant que la bulle est ouverte (dépendance [open]).
  // Le `return () => {…}` est le nettoyage : React l'appelle quand `open` repasse à false ou
  // quand le composant disparaît, et on retire alors exactement les écouteurs ajoutés.
  //  - 'scroll' avec `true` : écoute en phase de « capture », pour attraper aussi le défilement
  //    d'un tableau ou d'un bloc intérieur (cet événement ne remonte pas jusqu'à window sinon) ;
  //  - 'pointerdown' : souris, doigt ou stylet. On ferme si le clic n'est ni sur le « ? » ni dans la bulle ;
  //  - 'keydown' : la touche Échap ferme la bulle.
  useEffect(() => {
    if (!open) return
    const close = () => { setOpen(false); setPinned(false) }
    const outside = (e) => { if (!btn.current?.contains(e.target) && !tip.current?.contains(e.target)) close() }
    window.addEventListener('scroll', close, true)
    window.addEventListener('resize', close)
    document.addEventListener('pointerdown', outside)
    const esc = (e) => e.key === 'Escape' && close()
    document.addEventListener('keydown', esc)
    return () => {
      window.removeEventListener('scroll', close, true)
      window.removeEventListener('resize', close)
      document.removeEventListener('pointerdown', outside)
      document.removeEventListener('keydown', esc)
    }
  }, [open])

  // Affichage : le bouton « ? », puis la bulle si elle est ouverte.
  //
  // Les gestionnaires d'événements du bouton :
  //  - onClick : bascule entre « ouverte et épinglée » et « fermée ». stopPropagation() empêche le
  //    clic de remonter vers les éléments parents, qui pourraient eux aussi réagir au clic ;
  //  - onPointerEnter / onPointerLeave : survol, seulement pour une vraie souris (pointerType 'mouse'),
  //    car sur téléphone un toucher déclenche aussi ces événements ;
  //  - onFocus / onBlur : ouverture au clavier quand le bouton reçoit le focus (touche Tab).
  //
  // Les attributs aria-* décrivent l'état du bouton aux lecteurs d'écran.
  return (
    <span className={`inline-flex align-middle ${className}`}>
      <button
        ref={btn}
        type="button"
        aria-label="Aide"
        aria-describedby={open ? id : undefined}
        aria-expanded={open}
        onClick={(e) => { e.stopPropagation(); const next = !(open && pinned); setOpen(next); setPinned(next) }}
        onPointerEnter={(e) => e.pointerType === 'mouse' && setOpen(true)}
        onPointerLeave={(e) => e.pointerType === 'mouse' && !pinned && setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => !pinned && setOpen(false)}
        className="w-[18px] h-[18px] shrink-0 rounded-full border-[1.5px] border-green text-green-dark text-[11px] font-bold leading-none inline-flex items-center justify-center bg-surface cursor-help hover:bg-green-soft focus-visible:outline focus-visible:outline-2 focus-visible:outline-green"
      >
        ?
      </button>
      {/* La bulle. createPortal(contenu, document.body) : un « portail » React. Le contenu reste
          un enfant de ce composant pour React (état, événements), mais il est réellement placé
          dans <body>, en dehors de la page. Ainsi aucun bloc parent avec overflow (tableau qui
          défile) ne peut le couper. `fixed` + z-[100] : positionné par rapport à la fenêtre,
          au-dessus de tout. Tant que pos est null, la bulle est hors écran (left: -9999) pour être mesurée. */}
      {open && createPortal(
        <span
          ref={tip}
          id={id}
          role="tooltip"
          style={pos ? { left: pos.left, top: pos.top, width: pos.width } : { left: -9999, top: 0, width: WIDTH }}
          className="fixed z-[100] bg-brand text-white text-xs font-normal normal-case tracking-normal leading-relaxed p-3 rounded shadow-lg text-left whitespace-normal"
        >
          {/* La petite flèche : un carré de taille 0 dont une seule bordure est colorée, ce qui
              dessine un triangle. Elle est collée en haut de la bulle (bulle en dessous du « ? »)
              ou en bas (bulle au-dessus). aria-hidden : purement décorative. */}
          {pos && (
            <span aria-hidden
              className={`absolute w-0 h-0 border-[6px] border-transparent ${pos.below ? 'bottom-full border-b-brand' : 'top-full border-t-brand'}`}
              style={{ left: pos.arrow - 6 }} />
          )}
          {text}
        </span>,
        document.body,
      )}
    </span>
  )
}
