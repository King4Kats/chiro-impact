import { useRef, useState } from 'react'
import { api, PHASES } from '../api'
import Help from './Help'

// Zone de dépôt des WAV : on choisit le site et la phase, puis on glisse les fichiers (ou on clique).
// Phase « Auto » : déduite de la date dans le nom du fichier et des dates du festival de la campagne.
export default function UploadZone({ campaign, onUploaded }) {
  const hasDates = Boolean(campaign.festival_start && campaign.festival_end)
  const [siteId, setSiteId] = useState(campaign.sites[0]?.id || '')
  const [phase, setPhase] = useState(hasDates ? 'auto' : 'avant')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')
  const [skipped, setSkipped] = useState([])
  const [drag, setDrag] = useState(false)
  const inputRef = useRef()

  // Les fichiers partent UN PAR UN : une carte SD entière en un seul envoi serait coupée par le
  // serveur (délai d'attente) et une seule erreur ferait tout échouer.
  async function send(fileList) {
    const files = [...fileList]
    if (!files.length) return
    if (!siteId) { setMsg('Choisis d’abord un site.'); return }
    setBusy(true); setSkipped([])
    let created = 0
    const refused = []
    for (let i = 0; i < files.length; i++) {
      setMsg(`Envoi ${i + 1} / ${files.length} : ${files[i].name}…`)
      try {
        const res = await api.upload(campaign.id, siteId, phase, [files[i]])
        created += res.created.length
        refused.push(...res.skipped)
      } catch (e) {
        refused.push({ filename: files[i].name, reason: 'envoi impossible : ' + e.message })
      }
      if (i % 5 === 4) onUploaded?.() // la liste se met à jour au fil de l'envoi
    }
    setMsg(created
      ? `${created} fichier(s) déposé(s). L’analyse tourne en arrière-plan.`
      : 'Aucun fichier accepté.')
    setSkipped(refused)
    onUploaded?.()
    setBusy(false)
    if (inputRef.current) inputRef.current.value = ''
  }

  const noSite = campaign.sites.length === 0
  const phaseBtn = (key, label, disabled = false) => (
    <button key={key} type="button" onClick={() => setPhase(key)} disabled={disabled}
      className={`flex-1 py-2 rounded-sm border text-sm font-medium transition disabled:opacity-40 disabled:cursor-not-allowed ${phase === key ? 'bg-green-dark text-white border-green-dark' : 'bg-surface border-line hover:bg-green-soft'}`}>
      {label}
    </button>
  )

  return (
    <div className="card p-4 grid gap-3">
      <h3 className="font-bold flex items-center gap-2">
        Déposer des enregistrements
        <Help text="Récupère les fichiers WAV sur la carte SD de l'enregistreur, choisis le site où il était posé et la phase, puis glisse les fichiers ici. Chaque fichier est analysé par BatDetect2 dès son arrivée. Un fichier déjà déposé sur le même site est ignoré : tu peux redéposer toute une carte SD sans créer de doublons." />
      </h3>
      {noSite && <p className="text-sm bg-yellow/20 px-3 py-2 rounded-sm">Ajoute d’abord au moins un site d’enregistrement.</p>}
      {/* Une seule colonne : la zone est affichée dans la colonne latérale étroite (320 px) */}
      <div className="grid gap-3">
        <div>
          <label className="label" htmlFor="up-site">Site</label>
          <select id="up-site" className="input" value={siteId} onChange={(e) => setSiteId(e.target.value)} disabled={noSite}>
            {campaign.sites.map((s) => <option key={s.id} value={s.id}>{s.name}{s.is_control ? ' (témoin)' : ''}</option>)}
          </select>
        </div>
        <div>
          <span className="label flex items-center gap-1.5">
            Phase
            <Help text="Auto : l'application lit la date dans le nom du fichier (ex. 20240712_223000.WAV, format AudioMoth) et la compare aux dates du festival de la campagne. Un fichier de 2 h du matin compte pour la nuit qui a commencé la veille. Sinon, choisis la phase à la main." />
          </span>
          <div className="flex gap-1">
            {phaseBtn('auto', 'Auto', !hasDates)}
            {PHASES.map((p) => phaseBtn(p.key, p.label))}
          </div>
          {!hasDates && <p className="text-xs text-slate-light mt-1">« Auto » s’active quand les dates du festival sont renseignées.</p>}
        </div>
      </div>
      <div
        onDragOver={(e) => { e.preventDefault(); setDrag(true) }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); if (!busy && !noSite) send(e.dataTransfer.files) }}
        onClick={() => !busy && !noSite && inputRef.current.click()}
        className={`border-2 border-dashed rounded p-6 text-center cursor-pointer transition ${drag ? 'border-green bg-green-soft' : 'border-line hover:border-green'} ${busy || noSite ? 'opacity-60 cursor-not-allowed' : ''}`}
      >
        <p className="font-medium">Glisse tes fichiers .wav ici</p>
        <p className="text-sm text-slate-light">ou clique pour les choisir · plusieurs fichiers à la fois possible</p>
        <input ref={inputRef} type="file" accept=".wav,.WAV" multiple hidden onChange={(e) => send(e.target.files)} />
      </div>
      {msg && <p className="text-sm text-slate-light">{msg}</p>}
      {skipped.length > 0 && (
        <div className="text-sm bg-yellow/20 px-3 py-2 rounded-sm">
          <p className="font-medium">{skipped.length} fichier(s) ignoré(s) :</p>
          <ul className="mt-1 grid gap-0.5">
            {skipped.slice(0, 8).map((s) => <li key={s.filename} className="break-all"><b className="font-medium">{s.filename}</b> — {s.reason}</li>)}
            {skipped.length > 8 && <li>… et {skipped.length - 8} autre(s)</li>}
          </ul>
        </div>
      )}
    </div>
  )
}
