import { Link, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import Campaign from './pages/Campaign'
import Campaigns from './pages/Campaigns'
import Doc from './pages/Doc'
import Recording from './pages/Recording'

// Plan du site : chaque URL affiche une page, toujours dans le même cadre (Layout)
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

function NotFound() {
  return (
    <div className="card p-6">
      <p className="font-medium">Page introuvable.</p>
      <Link to="/" className="text-green-dark hover:underline text-sm">← Retour aux campagnes</Link>
    </div>
  )
}
