import { useEffect, useState } from 'react'
import { api } from '../api'
import Help from './Help'

// Dates du festival d'une campagne : première et dernière NUIT.
// Elles servent à classer automatiquement les fichiers en avant / pendant / après.
export default function FestivalDates({ campaign, onChange }) {
  const [start, setStart] = useState(campaign.festival_start || '')
  const [end, setEnd] = useState(campaign.festival_end || '')
  const [msg, setMsg] = useState('')
  useEffect(() => { setStart(campaign.festival_start || ''); setEnd(campaign.festival_end || '') }, [campaign.festival_start, campaign.festival_end])

  const dirty = start !== (campaign.festival_start || '') || end !== (campaign.festival_end || '')

  async function save(e) {
    e.preventDefault()
    setMsg('')
    try {
      const r = await api.updateCampaign(campaign.id, { festival_start: start || null, festival_end: end || null })
      setMsg(r.reclassified ? `${r.reclassified} fichier(s) reclassé(s).` : 'Dates enregistrées.')
      onChange()
    } catch (err) { setMsg('Erreur : ' + err.message) }
  }

  return (
    <form onSubmit={save} className="card p-4 grid gap-3">
      <h3 className="font-bold flex items-center gap-2">
        Dates du festival
        <Help text="Première et dernière NUIT du festival (bornes incluses). Exemple : festival du vendredi 12 au dimanche 14 juillet → première nuit le 12, dernière nuit le 14. Les fichiers déposés en phase « Auto » sont classés avant / pendant / après grâce à ces dates ; si tu les changes, ils sont reclassés tout seuls." />
      </h3>
      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className="label" htmlFor="fd-start">Première nuit</label>
          <input id="fd-start" type="date" className="input px-2" value={start} onChange={(e) => setStart(e.target.value)} />
        </div>
        <div>
          <label className="label" htmlFor="fd-end">Dernière nuit</label>
          <input id="fd-end" type="date" className="input px-2" value={end} min={start || undefined} onChange={(e) => setEnd(e.target.value)} />
        </div>
      </div>
      {dirty && <button className="btn btn-ghost justify-center" type="submit">Enregistrer les dates</button>}
      {msg && <p className="text-xs text-slate-light">{msg}</p>}
    </form>
  )
}
