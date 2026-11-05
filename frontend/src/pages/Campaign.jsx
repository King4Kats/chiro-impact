import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, PHASES } from '../api'
import FestivalDates from '../components/FestivalDates'
import Help from '../components/Help'
import Sites from '../components/Sites'
import Summary from '../components/Summary'
import UploadZone from '../components/UploadZone'

// Page d'une campagne : 2 onglets (Enregistrements / Synthèse) + panneau (dépôt, dates, sites).
// Ordinateur (≥ 1280 px) : panneau à droite. Tablette / téléphone : dépôt en haut (c'est l'action
// qu'on fait sur le terrain), puis la liste, puis dates et sites.
export default function Campaign() {
  const { id } = useParams()
  const [camp, setCamp] = useState(null)
  const [recs, setRecs] = useState([])
  const [summary, setSummary] = useState(null)
  const [tab, setTab] = useState('recs')
  const [error, setError] = useState('')

  // Recharge tout (campagne, enregistrements, synthèse)
  const load = useCallback(() => {
    Promise.all([api.campaign(id), api.recordings(id), api.summary(id)])
      .then(([c, r, s]) => { setCamp(c); setRecs(r); setSummary(s) })
      .catch((e) => setError(e.message))
  }, [id])
  useEffect(() => { load() }, [load])

  // Tant qu'il reste des fichiers en cours d'analyse, on rafraîchit toutes les 3 s
  const working = recs.some((r) => r.status === 'pending' || r.status === 'processing')
  useEffect(() => {
    if (!working) return
    const t = setInterval(load, 3000)
    return () => clearInterval(t)
  }, [working, load])

  if (error) return <p className="text-red-600 dark:text-red-400">{error}</p>
  if (!camp) return <p className="text-slate-light">Chargement…</p>

  const hasDates = Boolean(camp.festival_start && camp.festival_end)
  const tabBtn = (k, label) => (
    <button onClick={() => setTab(k)} className={`px-3 sm:px-4 py-2 border-b-[3px] -mb-[2px] font-medium whitespace-nowrap ${tab === k ? 'border-green text-slate' : 'border-transparent text-slate-light hover:text-slate'}`}>{label}</button>
  )

  return (
    <div className="grid gap-5 sm:gap-6">
      <div className="min-w-0">
        <Link to="/" className="text-sm text-slate-light hover:text-slate">← Campagnes</Link>
        <h2 className="text-xl sm:text-2xl font-bold break-words">{camp.name}</h2>
        <p className="text-slate-light text-sm sm:text-base">
          {camp.description}
          {hasDates && <span className="block sm:inline"><span className="hidden sm:inline">{camp.description ? ' · ' : ''}</span>festival les nuits du {fmtDay(camp.festival_start)} au {fmtDay(camp.festival_end)}</span>}
        </p>
      </div>

      <div className="grid gap-5 sm:gap-6 xl:grid-cols-[minmax(0,1fr)_340px] xl:grid-rows-[auto_1fr]">
        <section className="min-w-0 order-2 xl:order-none xl:col-start-1 xl:row-start-1 xl:row-span-2">
          <div className="flex gap-1 border-b-2 border-line mb-4 overflow-x-auto overflow-y-hidden">
            {tabBtn('recs', `Enregistrements (${recs.length})`)}
            {tabBtn('summary', 'Synthèse')}
          </div>
          {tab === 'recs' ? <Recordings recs={recs} hasDates={hasDates} onChange={load} /> : <Summary summary={summary} />}
        </section>
        <div className="order-1 xl:order-none xl:col-start-2 xl:row-start-1">
          {/* key : la zone se réinitialise quand les dates changent (phase « Auto » activable) */}
          <UploadZone key={`${camp.festival_start}-${camp.festival_end}-${camp.sites.length}`} campaign={camp} onUploaded={load} />
        </div>
        <div className="order-3 xl:order-none xl:col-start-2 xl:row-start-2 grid gap-4 md:grid-cols-2 xl:grid-cols-1 content-start">
          <FestivalDates campaign={camp} onChange={load} />
          <Sites campaign={camp} onChange={load} />
        </div>
      </div>
    </div>
  )
}

const STATUS = {
  pending: ['En attente', 'bg-line text-slate-light'],
  processing: ['Analyse…', 'bg-yellow/30 text-slate'],
  done: ['Analysé', 'bg-green-soft text-green-dark'],
  error: ['Erreur', 'bg-red-100 dark:bg-red-900/40 text-red-700 dark:text-red-300'],
}

function statusOf(r) {
  const [label, cls] = STATUS[r.status] || STATUS.pending
  // Pendant l'analyse d'un long fichier, on affiche l'avancement
  return [r.status === 'processing' && r.progress > 0 ? `${label} ${Math.round(r.progress * 100)} %` : label, cls]
}

const PHASE_HELP = "Phase du fichier. « auto » = calculée depuis la date du fichier et les dates du festival. Tu peux la corriger ici : le fichier change alors de groupe et la synthèse est recalculée."

// Liste des enregistrements, groupée par phase.
// Ordinateur (≥ 1024 px) : un tableau. Téléphone / tablette : des cartes (1 ou 2 colonnes).
function Recordings({ recs, hasDates, onChange }) {
  if (recs.length === 0) return <div className="card p-6 text-slate-light">Aucun enregistrement. Dépose des fichiers WAV avec la zone « Déposer des enregistrements ».</div>
  return (
    <div className="grid gap-4">
      {PHASES.map((p) => {
        const rows = recs.filter((r) => r.phase === p.key)
        if (!rows.length) return null
        return (
          <div key={p.key} className="card overflow-hidden">
            <div className="px-3 py-2 font-bold bg-green-soft border-b border-line">{p.label} <span className="text-slate-light font-normal text-sm">· {rows.length} fichier(s)</span></div>
            <RecordingsTable rows={rows} hasDates={hasDates} onChange={onChange} />
            <div className="lg:hidden grid md:grid-cols-2 divide-y md:divide-y-0 divide-line">
              {rows.map((r, i) => <RecordingCard key={r.id} r={r} hasDates={hasDates} onChange={onChange} odd={i % 2 === 1} />)}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function RecordingsTable({ rows, hasDates, onChange }) {
  return (
    <table className="hidden lg:table w-full text-sm">
      <thead><tr>
        <th className="th">Fichier · date</th>
        <th className="th">Site</th>
        <th className="th"><span className="inline-flex items-center gap-1">Phase <Help text={PHASE_HELP} /></span></th>
        <th className="th text-right">Durée</th>
        <th className="th text-right"><span className="inline-flex items-center gap-1">Cris <Help text="Nombre de cris détectés au-dessus du seuil 0,3." /></span></th>
        <th className="th text-right"><span className="inline-flex items-center gap-1">Contacts <Help text="Tranches de 5 s contenant au moins un cri. C'est l'unité qui sert à calculer l'activité." /></span></th>
        <th className="th">Groupes</th>
        <th className="th">État</th>
        <th className="th"><span className="sr-only">Actions</span></th>
      </tr></thead>
      <tbody>
        {rows.map((r) => {
          const [label, cls] = statusOf(r)
          return (
            <tr key={r.id} className="hover:bg-green-soft/50 align-top">
              <td className="td !whitespace-normal">
                <Link to={`/recordings/${r.id}`} className="font-medium hover:text-green-dark break-all">{r.filename}</Link>
                <div className="text-xs text-slate-light">{fmtDate(r.recorded_at)}<TzMark r={r} /></div>
              </td>
              <td className="td !whitespace-normal">{r.site_name}{r.is_control ? <span className="text-slate-light"> (témoin)</span> : null}</td>
              <td className="td"><PhaseSelect r={r} hasDates={hasDates} onChange={onChange} /></td>
              <td className="td text-right">{fmtDur(r.duration)}</td>
              <td className="td text-right">{r.status === 'done' ? r.n_calls : '–'}</td>
              <td className="td text-right">{r.status === 'done' ? r.n_contacts : '–'}</td>
              <td className="td !whitespace-normal text-xs min-w-[8rem]">{r.groups.join(', ') || (r.status === 'done' ? 'aucun' : '')}</td>
              <td className="td"><span className={`text-xs px-2 py-0.5 rounded-sm ${cls}`} title={r.error}>{label}</span></td>
              <td className="td text-right"><Actions r={r} onChange={onChange} /></td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

function RecordingCard({ r, hasDates, onChange, odd }) {
  const [label, cls] = statusOf(r)
  return (
    <div className={`p-3 grid gap-2 text-sm ${odd ? 'md:border-l md:border-line' : ''} md:border-b md:border-line`}>
      <div className="flex items-start gap-2">
        <Link to={`/recordings/${r.id}`} className="font-medium hover:text-green-dark break-all flex-1 min-w-0">{r.filename}</Link>
        <span className={`text-xs px-2 py-0.5 rounded-sm whitespace-nowrap ${cls}`} title={r.error}>{label}</span>
      </div>
      <div className="text-xs text-slate-light">
        {r.site_name}{r.is_control ? ' (témoin)' : ''} · {fmtDate(r.recorded_at)}<TzMark r={r} /> · {fmtDur(r.duration)}
      </div>
      {r.status === 'done' && (
        <div className="text-xs">
          <b className="tabular-nums">{r.n_calls}</b> cris · <b className="tabular-nums">{r.n_contacts}</b> contacts
          {r.groups.length > 0 && <span className="text-slate-light"> · {r.groups.join(', ')}</span>}
        </div>
      )}
      <div className="flex items-center gap-3 flex-wrap">
        <PhaseSelect r={r} hasDates={hasDates} onChange={onChange} />
        <span className="flex-1" />
        <Actions r={r} onChange={onChange} />
      </div>
    </div>
  )
}

function PhaseSelect({ r, hasDates, onChange }) {
  return (
    <span className="inline-flex items-center gap-1">
      <select className="border border-line rounded-sm bg-surface text-xs px-1.5 py-1" aria-label={`Phase de ${r.filename}`}
        value={r.phase} onChange={(e) => api.updateRecording(r.id, { phase: e.target.value }).then(onChange)}>
        {PHASES.map((ph) => <option key={ph.key} value={ph.key}>{ph.label}</option>)}
        {hasDates && <option value="auto">↻ recalculer (auto)</option>}
      </select>
      {r.phase_source === 'auto' && <span className="text-[10px] uppercase text-green-dark" title="Phase calculée automatiquement">auto</span>}
    </span>
  )
}

function Actions({ r, onChange }) {
  const [confirm, setConfirm] = useState(false)
  return (
    <span className="inline-flex items-center gap-3 text-xs whitespace-nowrap">
      {r.status === 'error' && <button className="text-slate-light hover:text-slate py-1" onClick={() => api.reprocess(r.id).then(onChange)}>relancer</button>}
      {confirm
        ? <button className="text-red-600 dark:text-red-400 font-medium py-1" onClick={() => api.deleteRecording(r.id).then(onChange)} onBlur={() => setConfirm(false)} autoFocus>confirmer ?</button>
        : <button className="text-slate-light hover:text-red-600 py-1" onClick={() => setConfirm(true)}>supprimer</button>}
    </span>
  )
}

// Petit repère quand l'heure vient du nom du fichier (fuseau inconnu : UTC par défaut sur AudioMoth)
function TzMark({ r }) {
  if (r.time_source !== 'nom du fichier') return null
  return <span className="text-orange-600 dark:text-orange-400" title="Heure lue dans le nom du fichier : fuseau inconnu (l'AudioMoth nomme ses fichiers en UTC par défaut)"> ⚠ fuseau ?</span>
}

export function fmtDur(s) {
  if (s == null) return '–'
  if (s < 60) return `${s.toFixed(1)} s`
  const m = Math.floor(s / 60), sec = Math.round(s % 60)
  return m < 60 ? `${m} min ${sec} s` : `${Math.floor(m / 60)} h ${m % 60} min`
}

// '2024-07-12T22:30:00' → '12/07/2024 22:30'
export function fmtDate(iso) {
  if (!iso) return 'date inconnue'
  const [d, t] = iso.split('T')
  const [y, m, j] = d.split('-')
  return `${j}/${m}/${y}${t ? ' ' + t.slice(0, 5) : ''}`
}

function fmtDay(iso) {
  const [y, m, j] = iso.split('-')
  return `${j}/${m}/${y}`
}
