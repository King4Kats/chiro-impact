/*
 * App.jsx — le plan du site.
 *
 * Il associe chaque adresse (URL) à la page qui doit s'afficher. Les pages sont dans src/pages/,
 * le cadre commun (en-tête + menu) dans src/components/Layout.jsx.
 *
 * Travaille avec : main.jsx (qui l'affiche à l'intérieur de <BrowserRouter>), Layout.jsx, src/pages/*.jsx.
 */
import { Link, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import Campaign from './pages/Campaign'
import Campaigns from './pages/Campaigns'
import Doc from './pages/Doc'
import Recording from './pages/Recording'

// Plan du site : chaque URL affiche une page, toujours dans le même cadre (Layout)
//
// Notions pour débuter :
//  - Un « composant » React est une fonction dont le nom commence par une majuscule et qui
//    renvoie du JSX (le HTML-dans-le-JavaScript). On l'utilise ensuite comme une balise : <App />.
//  - <Routes> regarde l'adresse courante et choisit la première <Route> qui correspond.
//  - La <Route> sans `path` qui entoure les autres est une route « de mise en page » :
//    elle affiche <Layout />, et Layout place la page choisie à l'endroit de son <Outlet />.
//  - `:id` dans un chemin est un paramètre : /campaigns/12 affiche Campaign, qui lit 12 avec useParams().
//  - path="*" attrape toutes les adresses inconnues → page « introuvable ».
export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Campaigns />} />
        <Route path="/campaigns/:id" element={<Campaign />} />
        <Route path="/recordings/:id" element={<Recording />} />
        <Route path="/doc" element={<Doc />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}

// Petite page affichée pour une adresse inconnue.
// En JSX on écrit `className` (et non `class`, mot réservé en JavaScript).
// <Link to="/"> fabrique un lien qui change de page sans recharger tout le site.
function NotFound() {
  return (
    <div className="card p-6">
      <p className="font-medium">Page introuvable.</p>
      <Link to="/" className="text-green-dark hover:underline text-sm">← Retour aux campagnes</Link>
    </div>
  )
}
