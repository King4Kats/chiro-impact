/*
 * Layout.jsx — le cadre commun à toutes les pages.
 *
 * Il dessine le bandeau du haut (nom de l'appli, sélecteur de thème, menu) puis, en dessous,
 * la page demandée par l'adresse. Il ne se recharge pas quand on change de page : seul le
 * contenu de <Outlet /> est remplacé.
 *
 * Travaille avec :
 *  - App.jsx : la route « de mise en page » <Route element={<Layout />}> qui l'utilise ;
 *  - theme.js : setChoice / useTheme / THEME_CHOICES pour le sélecteur Auto / Clair / Sombre ;
 *  - CONTAINER est aussi importable par les pages qui veulent la même largeur.
 */
import { Link, NavLink, Outlet } from 'react-router-dom'
import { setChoice, THEME_CHOICES, useTheme } from '../theme'

// Largeur commune à l'en-tête et au contenu : toute la largeur de l'écran (jusqu'à 1800 px),
// avec des marges qui grandissent avec l'écran (16 px sur téléphone, 32 px sur ordinateur).
// Les préfixes sm: et lg: de Tailwind n'appliquent la classe qu'à partir d'une certaine largeur
// d'écran (sm = 640 px, lg = 1024 px) : c'est ainsi qu'on adapte l'affichage aux téléphones.
export const CONTAINER = 'w-full max-w-[1800px] mx-auto px-4 sm:px-6 lg:px-8'

// Squelette commun à toutes les pages : bandeau du haut + menu + contenu (Outlet = la page courante)
export default function Layout() {
  // Style des onglets du menu. <NavLink> appelle cette fonction en lui passant { isActive } :
  // vrai si l'adresse courante correspond au lien. L'onglet actif reçoit un trait vert dessous.
  const link = ({ isActive }) =>
    `px-3 sm:px-4 py-2.5 border-b-[3px] -mb-px font-medium whitespace-nowrap transition ${isActive ? 'border-green text-slate' : 'border-transparent text-slate-light hover:text-slate'}`
  return (
    <div className="min-h-screen flex flex-col">
      {/* Bandeau du haut : à gauche le nom (lien vers l'accueil), à droite thème + menu.
          flex-wrap : sur un écran étroit, la partie droite passe à la ligne au lieu de déborder. */}
      <header className="bg-surface border-b border-line">
        <div className={`${CONTAINER} flex flex-wrap items-end justify-between gap-x-6`}>
          <div className="pt-4 pb-2 sm:pb-3 min-w-0">
            <Link to="/" className="text-xl sm:text-2xl font-bold text-green leading-none">Chiro Impact</Link>
            {/* Sous-titre caché sur téléphone (hidden), visible à partir de sm (sm:block) */}
            <p className="hidden sm:block text-slate-light text-sm mt-1">Suivi acoustique des chauves-souris avant, pendant et après un festival</p>
          </div>
          <div className="flex items-end gap-x-4 max-w-full">
          <ThemeSwitch />
          {/* Menu. `end` sur le lien "/" : il n'est actif que sur l'accueil exact,
              sinon il serait aussi actif sur /doc (toutes les adresses commencent par "/").
              overflow-x-auto : sur petit écran, le menu défile horizontalement. */}
          <nav className="flex gap-1 -mb-px overflow-x-auto overflow-y-hidden max-w-full">
            <NavLink to="/" end className={link}>Campagnes</NavLink>
            <NavLink to="/doc" className={link}>Comment ça marche</NavLink>
          </nav>
          </div>
        </div>
      </header>
      {/* Contenu : <Outlet /> est remplacé par la page choisie dans App.jsx.
          flex-1 : le contenu prend toute la hauteur restante sous le bandeau. */}
      <main className={`${CONTAINER} py-5 sm:py-6 flex-1`}>
        <Outlet />
      </main>
    </div>
  )
}

// Sélecteur de thème : Auto (suit l'ordinateur), Clair ou Sombre
// ICONS : le symbole affiché sur chaque bouton ; LABELS : le texte lu par les lecteurs d'écran
// et affiché en infobulle (title).
const ICONS = { auto: '◐', clair: '☀', sombre: '☾' }
const LABELS = { auto: 'Thème automatique (comme l’ordinateur)', clair: 'Thème clair', sombre: 'Thème sombre' }

// Trois boutons collés. useTheme() redessine ce composant quand le thème change, pour
// que le bouton actif (fond vert) suive. Un clic appelle setChoice(), qui enregistre et applique.
//
// .map() transforme le tableau des choix en tableau de boutons. React exige une prop `key`
// unique sur chaque élément d'une liste : elle lui permet de savoir quel élément a changé.
//
// Accessibilité : role="radiogroup" / role="radio" + aria-checked disent aux lecteurs d'écran
// qu'il s'agit d'un choix unique parmi trois. aria-hidden cache l'icône, et la classe sr-only
// (« screen reader only ») garde le texte lisible par le lecteur d'écran tout en le masquant à l'œil.
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
