import { useState } from 'react'
import { api } from '../api'
import Help from './Help'

// Gestion des sites d'enregistrement d'une campagne (ajout / suppression, drapeau témoin)
export default function Sites({ campaign, onChange }) {
  const [name, setName] = useState('')
  const [control, setControl] = useState(false)
  const [error, setError] = useState('')

  async function add(e) {
    e.preventDefault()
    if (!name.trim()) return
    try {
      await api.createSite(campaign.id, { name: name.trim(), is_control: control })
      setName(''); setControl(false); onChange()
    } catch (e) { setError(e.message) }
  }

  return (
    <div className="card p-4 grid gap-3">
      <h3 className="font-bold flex items-center gap-2">
        Sites d’enregistrement
        <Help text="Un site = un emplacement précis où un enregistreur est posé (ex. « Lisière nord », « Scène principale »). Le même site doit être utilisé avant, pendant et après. Coche « témoin » pour un site hors de la zone du festival : il sert de référence pour séparer l'effet du festival de l'effet météo." />
      </h3>
      <ul className="grid gap-2">
        {campaign.sites.map((s) => (
          <li key={s.id} className="flex items-center gap-2 text-sm">
            <span className={`w-2 h-2 rounded-full ${s.is_control ? 'bg-yellow' : 'bg-green'}`} />
            <span className="flex-1">{s.name}{s.is_control ? <span className="text-slate-light"> · témoin</span> : null}</span>
            <RemoveSite site={s} onDone={onChange} />
          </li>
        ))}
        {campaign.sites.length === 0 && <li className="text-sm text-slate-light">Aucun site.</li>}
      </ul>
      <form onSubmit={add} className="grid gap-2">
        <input className="input" placeholder="Nom du site" value={name} onChange={(e) => setName(e.target.value)} aria-label="Nom du site" />
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={control} onChange={(e) => setControl(e.target.checked)} className="accent-green-dark" />
          Site témoin (hors festival)
        </label>
        <button className="btn btn-ghost justify-center" type="submit">Ajouter le site</button>
        {error && <p className="text-xs text-red-600">{error}</p>}
      </form>
    </div>
  )
}

// Retirer un site efface AUSSI tous ses enregistrements (fichiers WAV compris) : on demande confirmation.
function RemoveSite({ site, onDone }) {
  const [confirm, setConfirm] = useState(false)
  if (!confirm) return <button className="text-xs text-slate-light hover:text-red-600 py-1" onClick={() => setConfirm(true)}>retirer</button>
  return (
    <span className="text-xs inline-flex items-center gap-2">
      <span className="text-red-700">Effacer le site et ses fichiers ?</span>
      <button className="text-red-600 font-medium py-1" onClick={() => api.deleteSite(site.id).then(onDone)}>oui</button>
      <button className="text-slate-light py-1" onClick={() => setConfirm(false)}>non</button>
    </span>
  )
}
