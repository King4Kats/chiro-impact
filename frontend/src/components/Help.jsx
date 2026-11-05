import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

const MARGIN = 8   // distance minimale entre la bulle et le bord de l'écran
const GAP = 8      // distance entre le « ? » et la bulle
const WIDTH = 288  // largeur de la bulle (réduite sur petit écran)

// Le petit "?" vert : au survol (ordinateur) ou au toucher (téléphone), affiche une bulle d'explication.
// La bulle est dessinée au-dessus de toute la page (portail vers <body>) et recalée pour rester dans
// l'écran : elle n'est jamais coupée par un tableau qui défile, ni par le bord d'un téléphone.
// (La prop `align` des versions précédentes est acceptée mais n'est plus nécessaire.)
// eslint-disable-next-line no-unused-vars
export default function Help({ text, className = '', align }) {
  const [open, setOpen] = useState(false)
  const [pinned, setPinned] = useState(false) // ouverte par un clic : reste ouverte jusqu'au clic suivant
  const [pos, setPos] = useState(null)
  const btn = useRef(null)
  const tip = useRef(null)
  const id = useId()

  // Calcule la position une fois la bulle affichée (on a besoin de sa hauteur réelle)
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
        className="w-[18px] h-[18px] shrink-0 rounded-full border-[1.5px] border-green text-green-dark text-[11px] font-bold leading-none inline-flex items-center justify-center bg-white cursor-help hover:bg-green-soft focus-visible:outline focus-visible:outline-2 focus-visible:outline-green"
      >
        ?
      </button>
      {open && createPortal(
        <span
          ref={tip}
          id={id}
          role="tooltip"
          style={pos ? { left: pos.left, top: pos.top, width: pos.width } : { left: -9999, top: 0, width: WIDTH }}
          className="fixed z-[100] bg-slate text-white text-xs font-normal normal-case tracking-normal leading-relaxed p-3 rounded shadow-lg text-left whitespace-normal"
        >
          {pos && (
            <span aria-hidden
              className={`absolute w-0 h-0 border-[6px] border-transparent ${pos.below ? 'bottom-full border-b-slate' : 'top-full border-t-slate'}`}
              style={{ left: pos.arrow - 6 }} />
          )}
          {text}
        </span>,
        document.body,
      )}
    </span>
  )
}
