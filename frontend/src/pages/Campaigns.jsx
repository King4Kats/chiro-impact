import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import Help from '../components/Help'

// Page d'accueil : liste des campagnes + formulaire de création
export default function Campaigns() {
  const [list, setList] = useState([])
  const [name, setName] = useState('')
  const [desc, setDesc] = useState('')
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const [error, setError] = useState('')

  const load = () => api.campaigns().then(setList).catch((e) => setError(e.message))
  useEffect(() => { load() }, [])

  async function create(e) {
    e.preventDefault()
    if (!name.trim()) return
    try {
      await api.createCampaign({ name: name.trim(), description: desc.trim(), festival_start: start || null, festival_end: end || null })
      setName(''); setDesc(''); setStart(''); setEnd(''); setError(''); load()
    } catch (e) { setError(e.message) }
  }

  async function remove(c) {
    // Pas de confirm() natif : on demande deux clics (voir bouton)
    await api.deleteCampaign(c.id); load()
  }

  return (
    <div className="grid gap-6 md:grid-cols-[1fr_340px]">
      <section>
        <h2 className="text-xl font-bold mb-3 flex items-center gap-2">
          Campagnes
          <Help text="Une campagne = un festival + une édition (ex. « Dub Camp 2027 »). Elle regroupe les sites d'enregistrement et tous les fichiers audio des phases avant, pendant et après." />
        </h2>
        {error && <p className="text-red-600 dark:text-red-400 text-sm mb-2">{error}</p>}
        {list.length === 0 && (
          <div className="card p-6 text-slate-light">
            Aucune campagne pour l'instant. Crée la première avec le formulaire à droite.
          </div>
        )}
        <div className="grid gap-3">
          {list.map((c) => (
            <CampaignRow key={c.id} c={c} onDelete={() => remove(c)} />
          ))}
        </div>
      </section>

      <aside>
        <form onSubmit={create} className="card p-4 grid gap-3">
          <h3 className="font-bold">Nouvelle campagne</h3>
          <div>
            <label className="label" htmlFor="c-name">Nom</label>
            <input id="c-name" className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="Dub Camp 2027" />
          </div>
          <div>
            <label className="label" htmlFor="c-desc">Description (optionnel)</label>
            <textarea id="c-desc" className="input" rows={3} value={desc} onChange={(e) => setDesc(e.target.value)} placeholder="Lieu, dates, matériel utilisé…" />
          </div>
          <div>
            <span className="label flex items-center gap-1.5">
              Nuits du festival (optionnel)
              <Help text="Première et dernière nuit du festival. Elles permettent de classer automatiquement les fichiers en avant / pendant / après d'après leur date. Modifiables plus tard." />
            </span>
            <div className="grid grid-cols-2 gap-2">
              <input type="date" className="input px-2" aria-label="Première nuit" value={start} onChange={(e) => setStart(e.target.value)} />
              <input type="date" className="input px-2" aria-label="Dernière nuit" value={end} min={start || undefined} onChange={(e) => setEnd(e.target.value)} />
            </div>
          </div>
          <button className="btn btn-green justify-center" type="submit">Créer</button>
        </form>
      </aside>
    </div>
  )
}

function CampaignRow({ c, onDelete }) {
  const [confirm, setConfirm] = useState(false)
  return (
    <div className="card p-4 flex flex-wrap items-center gap-3">
      <div className="flex-1 min-w-0">
        <Link to={`/campaigns/${c.id}`} className="font-bold text-lg hover:text-green-dark">{c.name}</Link>
        {c.description && <p className="text-sm text-slate-light truncate">{c.description}</p>}
        <p className="text-xs text-slate-light mt-1">{c.n_sites} site(s) · {c.n_recordings} enregistrement(s) · créée le {c.created_at?.slice(0, 10)}</p>
      </div>
      <Link to={`/campaigns/${c.id}`} className="btn">Ouvrir</Link>
      {confirm ? (
        <button className="btn bg-red-600 hover:bg-red-700" onClick={onDelete} onBlur={() => setConfirm(false)}>Confirmer la suppression</button>
      ) : (
        <button className="btn btn-ghost" onClick={() => setConfirm(true)}>Supprimer</button>
      )}
    </div>
  )
}
