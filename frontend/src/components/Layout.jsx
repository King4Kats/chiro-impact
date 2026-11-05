import { Link, NavLink, Outlet } from 'react-router-dom'
import { setChoice, THEME_CHOICES, useTheme } from '../theme'

// Largeur commune à l'en-tête et au contenu : toute la largeur de l'écran (jusqu'à 1800 px),
// avec des marges qui grandissent avec l'écran (16 px sur téléphone, 32 px sur ordinateur).
export const CONTAINER = 'w-full max-w-[1800px] mx-auto px-4 sm:px-6 lg:px-8'

// Squelette commun à toutes les pages : bandeau du haut + menu + contenu (Outlet = la page courante)
export default function Layout() {
  const link = ({ isActive }) =>
    `px-3 sm:px-4 py-2.5 border-b-[3px] -mb-px font-medium whitespace-nowrap transition ${isActive ? 'border-green text-slate' : 'border-transparent text-slate-light hover:text-slate'}`
  return (
    <div className="min-h-screen flex flex-col">
      <header className="bg-surface border-b border-line">
        <div className={`${CONTAINER} flex flex-wrap items-end justify-between gap-x-6`}>
          <div className="pt-4 pb-2 sm:pb-3 min-w-0">
            <Link to="/" className="text-xl sm:text-2xl font-bold text-green leading-none">Chiro Impact</Link>
            <p className="hidden sm:block text-slate-light text-sm mt-1">Suivi acoustique des chauves-souris avant, pendant et après un festival</p>
          </div>
          <div className="flex items-end gap-x-4 max-w-full">
          <ThemeSwitch />
          <nav className="flex gap-1 -mb-px overflow-x-auto overflow-y-hidden max-w-full">
            <NavLink to="/" end className={link}>Campagnes</NavLink>
            <NavLink to="/doc" className={link}>Comment ça marche</NavLink>
          </nav>
          </div>
        </div>
      </header>
      <main className={`${CONTAINER} py-5 sm:py-6 flex-1`}>
        <Outlet />
      </main>
    </div>
  )
}

// Sélecteur de thème : Auto (suit l'ordinateur), Clair ou Sombre
const ICONS = { auto: '◐', clair: '☀', sombre: '☾' }
const LABELS = { auto: 'Thème automatique (comme l’ordinateur)', clair: 'Thème clair', sombre: 'Thème sombre' }

function ThemeSwitch() {
  const { choice } = useTheme()
  return (
    <div role="radiogroup" aria-label="Thème de l’interface" className="mb-2 sm:mb-3 flex shrink-0 border border-line rounded-sm overflow-hidden text-sm">
      {THEME_CHOICES.map((c) => (
        <button key={c} role="radio" aria-checked={choice === c} title={LABELS[c]} onClick={() => setChoice(c)}
          className={`px-2 py-1 leading-none border-l first:border-l-0 border-line transition ${choice === c ? 'bg-green-dark text-white' : 'text-slate-light hover:bg-green-soft'}`}>
          <span aria-hidden="true">{ICONS[c]}</span><span className="sr-only">{LABELS[c]}</span>
        </button>
      ))}
    </div>
  )
}
