/*
 * Compare.jsx — page « Comparer » d'une campagne (adresse /campaigns/:id/comparer).
 *
 * À QUOI ELLE SERT
 *   Comparer l'activité avant / pendant / après le festival, sur les sites du festival et sur le
 *   site témoin, en jouant sur les réglages pour vérifier que la conclusion tient :
 *   - réglages recalculés par le SERVEUR (il relit tous les cris) : seuil de score, largeur des
 *     tranches de contact, plage horaire de la nuit ;
 *   - réglages appliqués dans le NAVIGATEUR (instantané) : sites, nuits écartées, groupe d'espèces,
 *     indicateur (contacts ou cris par heure), façon de faire la moyenne.
 *
 * DONNÉES DEMANDÉES À L'API (voir api.js)
 *   - api.campaign(id)        : nom de la campagne et dates du festival ;
 *   - api.compare(id, params) : une ligne par site × nuit (heures d'écoute, contacts, cris, par groupe).
 *
 * SOMMAIRE
 *   - fonctions de calcul : rate, aggregate, change… (pures : mêmes entrées → même résultat)
 *   - Compare            : la page (état, chargement, mise en page)
 *   - Settings           : le panneau de réglages
 *   - PhaseTable         : activité par phase, festival / témoin
 *   - Baci               : écart d'évolution festival vs témoin
 *   - NightChart         : activité nuit par nuit (+ écarter des nuits)
 *   - GroupTable         : la même comparaison groupe par groupe
 *   - DetailTable        : le détail site × nuit et l'export CSV
 *
 * PRUDENCE
 *   Tous les chiffres sont descriptifs. Aucun test statistique n'est fait ici : un écart, même grand,
 *   peut venir du hasard (météo, petit nombre de nuits). Les textes d'aide le rappellent.
 */
import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { CartesianGrid, ComposedChart, Legend, Line, ReferenceArea, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, PHASES } from '../api'
import Help from '../components/Help'
import { useTheme } from '../theme'

// ---------------------------------------------------------------------------------------------
// Réglages possibles
// ---------------------------------------------------------------------------------------------

// Largeurs de tranche proposées (secondes). 5 s = convention Vigie-Chiro, celle de la synthèse.
const WINDOWS = [1, 5, 10, 30, 60]

// Heures proposées pour la plage horaire, dans l'ordre d'une nuit : de midi à midi le lendemain,
// par demi-heure. On s'en sert aussi pour vérifier que le début est avant la fin.
const NIGHT_HOURS = Array.from({ length: 48 }, (_, i) => (12 + i / 2) % 24)
const fmtHour = (h) => `${Math.floor(h)} h${h % 1 ? ' 30' : ''}`

// Réglages au chargement de la page : les mêmes que la synthèse, pour retrouver les mêmes chiffres.
const DEFAULTS = { threshold: 0.3, window: 5, useHours: false, hStart: 21, hEnd: 6 }

// Couleurs des deux types de site (mêmes que la synthèse) et des axes selon le thème
const COLORS = { impact: '#5aa876', control: '#fbcf38' }
const AXES = {
  light: { grid: '#e6e8e6', axis: '#44405a', soft: '#7a7790', tipBg: '#ffffff', area: '#80c595' },
  dark: { grid: '#3a374b', axis: '#e8e6f0', soft: '#a3a0b6', tipBg: '#22202d', area: '#80c595' },
}

// ---------------------------------------------------------------------------------------------
// Fonctions de calcul (pures)
// ---------------------------------------------------------------------------------------------

// Mise en forme des nombres à la française (virgule décimale). `null` = pas de donnée → « – ».
const fmt = (v, d = 1) => (v == null || Number.isNaN(v) ? '–' : v.toLocaleString('fr-FR', { minimumFractionDigits: d, maximumFractionDigits: d }))
const fmtPct = (v) => (v == null ? '–' : `${v > 0 ? '+' : ''}${fmt(v * 100, 0)} %`)
const fmtNight = (n) => (n ? n.slice(8, 10) + '/' + n.slice(5, 7) : 'sans date')

// Valeur comptée pour une ligne site × nuit, selon l'indicateur et le groupe choisis.
// `?? 0` : si le groupe n'a aucun contact cette nuit-là, la clé n'existe pas → on compte 0.
function valueOf(row, metric, group) {
  if (group === 'all') return metric === 'calls' ? row.calls : row.contacts
  return (metric === 'calls' ? row.calls_by_group : row.by_group)[group] ?? 0
}

// Moyenne d'un ensemble de lignes site × nuit. Deux façons de faire :
//  - 'nights' : on calcule le taux (par heure) de chaque site × nuit, puis la moyenne de ces taux.
//               Chaque nuit pèse autant, qu'elle ait duré 2 h ou 10 h.
//  - 'total'  : tout ce qui a été compté ÷ toutes les heures. Les longues nuits pèsent plus.
// Renvoie aussi le nombre de nuits distinctes et le plus petit / plus grand taux (dispersion).
function aggregate(rows, metric, group, mode) {
  const ok = rows.filter((r) => r.hours > 0) // une ligne sans heure d'écoute ne peut pas donner de taux
  if (!ok.length) return null
  const rates = ok.map((r) => valueOf(r, metric, group) / r.hours)
  const total = ok.reduce((s, r) => s + valueOf(r, metric, group), 0)
  const hours = ok.reduce((s, r) => s + r.hours, 0)
  return {
    value: mode === 'total' ? total / hours : rates.reduce((s, x) => s + x, 0) / rates.length,
    nights: new Set(ok.map((r) => r.night)).size,
    siteNights: ok.length,
    hours,
    min: Math.min(...rates),
    max: Math.max(...rates),
  }
}

// Évolution relative entre deux valeurs : 0,5 = +50 %, -0,67 = -67 %. Impossible si la base vaut 0.
const change = (from, to) => (from == null || to == null || from.value === 0 ? null : to.value / from.value - 1)

// Écart BACI descriptif : (évolution du festival) comparée à (évolution du témoin), en rapport.
// 0 = les deux ont évolué pareil ; -0,5 = le festival a fini 50 % plus bas que ce qu'aurait donné
// la même évolution que le témoin.
function baci(fBefore, fAfter, tBefore, tAfter) {
  const f = change(fBefore, fAfter)
  const t = change(tBefore, tAfter)
  if (f == null || t == null || 1 + t === 0) return null
  return (1 + f) / (1 + t) - 1
}

// ---------------------------------------------------------------------------------------------
// La page
// ---------------------------------------------------------------------------------------------

export default function Compare() {
  const { id } = useParams()
  const { theme } = useTheme()

  // Réglages calculés par le serveur (un changement relance une requête)
  const [threshold, setThreshold] = useState(DEFAULTS.threshold)
  const [windowS, setWindowS] = useState(DEFAULTS.window)
  const [useHours, setUseHours] = useState(DEFAULTS.useHours)
  const [hStart, setHStart] = useState(DEFAULTS.hStart)
  const [hEnd, setHEnd] = useState(DEFAULTS.hEnd)

  // Réglages appliqués dans le navigateur (aucun appel au serveur)
  const [hiddenSites, setHiddenSites] = useState(new Set())   // sites décochés
  const [hiddenNights, setHiddenNights] = useState(new Set()) // nuits écartées (pluie, panne…)
  const [group, setGroup] = useState('all')                   // 'all' ou un nom de groupe
  const [metric, setMetric] = useState('contacts')            // 'contacts' ou 'calls'
  const [mode, setMode] = useState('nights')                  // 'nights' ou 'total' (voir aggregate)

  const [camp, setCamp] = useState(null)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  // La plage horaire n'est valable que si le début vient avant la fin dans l'ordre de la nuit
  const hoursValid = NIGHT_HOURS.indexOf(hStart) < NIGHT_HOURS.indexOf(hEnd)
  const hours = useHours && hoursValid ? [hStart, hEnd] : null

  // Nom de la campagne et dates du festival (une seule fois)
  useEffect(() => { api.campaign(id).then(setCamp).catch((e) => setError(e.message)) }, [id])

  // Données de comparaison : rechargées quand un réglage « serveur » change.
  // Le setTimeout de 250 ms évite d'envoyer une requête à chaque cran du curseur ; la fonction de
  // nettoyage (return) annule l'attente précédente si l'utilisateur bouge encore le curseur.
  // `cancelled` ignore une réponse arrivée après qu'un réglage plus récent a été demandé.
  const hoursKey = hours ? hours.join('-') : 'all'
  useEffect(() => {
    if (useHours && !hoursValid) return
    let cancelled = false
    setLoading(true)
    const t = setTimeout(() => {
      api.compare(id, { threshold, window: windowS, hours })
        .then((d) => { if (!cancelled) { setData(d); setError('') } })
        .catch((e) => { if (!cancelled) setError(e.message) })
        .finally(() => { if (!cancelled) setLoading(false) })
    }, 250)
    return () => { cancelled = true; clearTimeout(t) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, threshold, windowS, hoursKey, useHours, hoursValid])

  // Lignes retenues après les filtres du navigateur. useMemo ne refait le filtrage que si
  // les données ou les filtres changent (et pas à chaque survol de la souris).
  const controlIds = useMemo(() => new Set((data?.sites || []).filter((s) => s.is_control).map((s) => s.id)), [data])
  const rows = useMemo(
    () => (data?.rows || []).filter((r) => !hiddenSites.has(r.site_id) && !hiddenNights.has(r.night)),
    [data, hiddenSites, hiddenNights],
  )

  // Tableau phase × type : stats[type][phase] = résultat d'aggregate (ou null)
  const statsFor = (g) => Object.fromEntries(['impact', 'control'].map((kind) => [kind, Object.fromEntries(PHASES.map((p) => [
    p.key, aggregate(rows.filter((r) => r.phase === p.key && controlIds.has(r.site_id) === (kind === 'control')), metric, g, mode),
  ]))]))
  const stats = statsFor(group)

  if (error && !data) return <p className="text-red-600 dark:text-red-400">{error}</p>
  if (!camp || !data) return <p className="text-slate-light">Chargement…</p>

  const unit = metric === 'calls' ? 'cris/h' : 'contacts/h'
  const hasImpact = data.sites.some((s) => !s.is_control && !hiddenSites.has(s.id))
  const hasControl = data.sites.some((s) => s.is_control && !hiddenSites.has(s.id))
  // Phases qui ont moins de 3 nuits sur un type de site : trop peu pour conclure quoi que ce soit
  const thin = ['impact', 'control'].flatMap((k) => PHASES.filter((p) => stats[k][p.key] && stats[k][p.key].nights < 3).map((p) => `${k === 'control' ? 'témoin' : 'festival'} ${p.label.toLowerCase()}`))

  // Fonctions de bascule : on recrée un Set (React ne voit pas une modification « en place »)
  const toggle = (set, setter) => (key) => setter((prev) => {
    const next = new Set(prev)
    next.has(key) ? next.delete(key) : next.add(key)
    return next
  })

  const settings = {
    threshold, setThreshold, windowS, setWindowS, useHours, setUseHours, hStart, setHStart, hEnd, setHEnd, hoursValid,
    group, setGroup, metric, setMetric, mode, setMode, groups: data.groups, sites: data.sites, hiddenSites,
    toggleSite: toggle(hiddenSites, setHiddenSites),
    reset: () => {
      setThreshold(DEFAULTS.threshold); setWindowS(DEFAULTS.window); setUseHours(DEFAULTS.useHours)
      setHStart(DEFAULTS.hStart); setHEnd(DEFAULTS.hEnd); setHiddenSites(new Set()); setHiddenNights(new Set())
      setGroup('all'); setMetric('contacts'); setMode('nights')
    },
  }

  return (
    <div className="grid gap-5 sm:gap-6">
      {/* En-tête : retour à la campagne et titre */}
      <div className="min-w-0">
        <Link to={`/campaigns/${id}`} className="text-sm text-slate-light hover:text-slate">← {camp.name}</Link>
        <h2 className="text-xl sm:text-2xl font-bold flex items-center gap-2">
          Comparer avant / pendant / après
          <Help text="Cette page refait les calculs de la synthèse avec les réglages de votre choix. Si la conclusion change beaucoup quand on bouge un réglage, elle est fragile. Les chiffres sont descriptifs : ce n'est pas un test statistique." />
        </h2>
      </div>

      {/* Deux colonnes sur grand écran : réglages à gauche (collés en haut au défilement), résultats à droite */}
      <div className="grid gap-5 lg:grid-cols-[300px_minmax(0,1fr)] items-start">
        <Settings {...settings} />

        <div className={`grid gap-5 min-w-0 transition-opacity ${loading ? 'opacity-60' : ''}`}>
          {/* Avertissements : ce qui empêche de lire les chiffres comme une comparaison solide */}
          {data.pending > 0 && <Note>{data.pending} fichier(s) encore en cours d’analyse : ils ne sont pas comptés.</Note>}
          {!hasControl && <Note>Aucun site témoin sélectionné : impossible de séparer l’effet du festival d’un changement de météo ou de saison.</Note>}
          {data.excluded_no_date > 0 && <Note>{data.excluded_no_date} fichier(s) sans date mis de côté : on ne sait pas à quelle heure ils ont été enregistrés.</Note>}
          {thin.length > 0 && <Note>Moins de 3 nuits pour : {thin.join(', ')}. Trop peu pour conclure (une seule nuit de pluie peut tout changer).</Note>}
          {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}

          <PhaseTable stats={stats} unit={unit} hasImpact={hasImpact} hasControl={hasControl} />
          {hasImpact && hasControl && <Baci stats={stats} />}
          <NightChart rows={data.rows} controlIds={controlIds} hiddenSites={hiddenSites} hiddenNights={hiddenNights}
            toggleNight={toggle(hiddenNights, setHiddenNights)} metric={metric} group={group} unit={unit} theme={theme} />
          {data.groups.length > 0 && <GroupTable groups={data.groups} statsFor={statsFor} current={group} setGroup={setGroup} unit={unit} />}
          <DetailTable data={data} rows={rows} controlIds={controlIds} camp={camp} metric={metric} group={group} unit={unit} hours={hours} />
        </div>
      </div>
    </div>
  )
}

// Petit encadré jaune d'avertissement
const Note = ({ children }) => <p className="text-sm bg-yellow/20 px-3 py-2 rounded-sm">{children}</p>

// ---------------------------------------------------------------------------------------------
// Panneau de réglages
// ---------------------------------------------------------------------------------------------

function Settings(s) {
  // Bouton d'un groupe de choix (indicateur, moyenne) : vert quand il est actif
  const choice = (active, onClick, label) => (
    <button type="button" onClick={onClick}
      className={`flex-1 px-2 py-1.5 text-sm border-l first:border-l-0 border-line ${active ? 'bg-green-dark text-white' : 'hover:bg-green-soft'}`}>{label}</button>
  )
  return (
    <aside className="card p-4 grid gap-5 lg:sticky lg:top-4">
      <div className="flex items-center justify-between">
        <h3 className="font-bold">Réglages</h3>
        <button type="button" className="text-xs text-slate-light hover:text-slate underline" onClick={s.reset}>revenir à la synthèse</button>
      </div>

      {/* Seuil de score : un curseur de 0,1 à 0,95 */}
      <div>
        <label className="label flex items-center gap-2" htmlFor="cmp-thr">
          Seuil de score : <span className="text-slate font-bold tabular-nums">{fmt(s.threshold, 2)}</span>
          <Help text="Un cri compte si le score donné par BatDetect2 dépasse ce seuil. Plus haut : moins de faux cris, mais plus de vrais cris manqués. La synthèse utilise 0,3. Les cris sous 0,1 ne sont pas gardés à l'analyse, d'où le minimum." />
        </label>
        <input id="cmp-thr" type="range" min="0.1" max="0.95" step="0.05" value={s.threshold}
          onChange={(e) => s.setThreshold(Number(e.target.value))} className="w-full accent-green" />
      </div>

      {/* Largeur de la tranche de contact */}
      <div>
        <label className="label flex items-center gap-2" htmlFor="cmp-win">
          Durée d’un contact
          <Help text="On découpe le temps en tranches de cette durée ; une tranche avec au moins un cri = 1 contact. 5 s est la convention du programme Vigie-Chiro et le réglage de la synthèse. Des tranches plus longues donnent moins de contacts et lissent les grosses séances de chasse." />
        </label>
        <select id="cmp-win" className="input" value={s.windowS} onChange={(e) => s.setWindowS(Number(e.target.value))}>
          {WINDOWS.map((w) => <option key={w} value={w}>{w} s{w === 5 ? ' (standard)' : ''}</option>)}
        </select>
      </div>

      {/* Plage horaire : une case à cocher, puis deux listes (début, fin) */}
      <div>
        <label className="label flex items-center gap-2">
          <input type="checkbox" className="accent-green" checked={s.useHours} onChange={(e) => s.setUseHours(e.target.checked)} />
          Même plage horaire chaque nuit
          <Help text="Ne garde, chaque nuit, que la partie des enregistrements comprise dans cette plage (heure française lue dans le fichier). Utile quand les enregistreurs n'ont pas tourné aux mêmes heures toutes les nuits. Les fichiers sans date sont alors mis de côté. Si l'heure vient seulement du nom du fichier, elle peut être en UTC (2 h de moins en été)." />
        </label>
        {s.useHours && (
          <div className="grid grid-cols-2 gap-2">
            <select aria-label="Début de la plage" className="input" value={s.hStart} onChange={(e) => s.setHStart(Number(e.target.value))}>
              {NIGHT_HOURS.map((h) => <option key={h} value={h}>{fmtHour(h)}</option>)}
            </select>
            <select aria-label="Fin de la plage" className="input" value={s.hEnd} onChange={(e) => s.setHEnd(Number(e.target.value))}>
              {NIGHT_HOURS.map((h) => <option key={h} value={h}>{fmtHour(h)}</option>)}
            </select>
            {!s.hoursValid && <p className="col-span-2 text-xs text-red-600 dark:text-red-400">Le début doit précéder la fin (de midi à midi le lendemain).</p>}
          </div>
        )}
      </div>

      {/* Groupe d'espèces */}
      <div>
        <label className="label flex items-center gap-2" htmlFor="cmp-grp">
          Groupe d’espèces
          <Help text="Ne compte que les cris attribués à ce groupe. Les effets d'un festival peuvent différer d'un groupe à l'autre. L'attribution vient d'un modèle entraîné au Royaume-Uni : c'est une indication à faire confirmer." />
        </label>
        <select id="cmp-grp" className="input" value={s.group} onChange={(e) => s.setGroup(e.target.value)}>
          <option value="all">Tous les groupes</option>
          {/* Le groupe choisi reste dans la liste même si, avec les réglages actuels, il n'a plus aucun cri */}
          {[...new Set([...s.groups, ...(s.group === 'all' ? [] : [s.group])])].map((g) => <option key={g} value={g}>{g}</option>)}
        </select>
      </div>

      {/* Indicateur */}
      <div>
        <p className="label flex items-center gap-2">
          Indicateur
          <Help text="Contacts par heure : le standard, une tranche active compte 1 même avec 40 cris. Cris par heure : chaque cri compte, donc une chauve-souris qui chasse longtemps près du micro fait monter le chiffre très vite." />
        </p>
        <div className="flex border border-line rounded-sm overflow-hidden">
          {choice(s.metric === 'contacts', () => s.setMetric('contacts'), 'Contacts/h')}
          {choice(s.metric === 'calls', () => s.setMetric('calls'), 'Cris/h')}
        </div>
      </div>

      {/* Façon de faire la moyenne */}
      <div>
        <p className="label flex items-center gap-2">
          Moyenne
          <Help text="Par nuit : on calcule l'activité de chaque site chaque nuit, puis la moyenne ; une nuit courte pèse autant qu'une longue. Totale : tous les contacts divisés par toutes les heures ; les longues nuits pèsent plus." />
        </p>
        <div className="flex border border-line rounded-sm overflow-hidden">
          {choice(s.mode === 'nights', () => s.setMode('nights'), 'Par nuit')}
          {choice(s.mode === 'total', () => s.setMode('total'), 'Totale')}
        </div>
      </div>

      {/* Sites : une case par site, festival d'abord puis témoins */}
      <div>
        <p className="label flex items-center gap-2">
          Sites
          <Help text="Décochez un site pour le retirer des calculs (enregistreur déplacé, micro abîmé…)." />
        </p>
        <div className="grid gap-1">
          {s.sites.map((site) => (
            <label key={site.id} className="flex items-center gap-2 text-sm cursor-pointer">
              <input type="checkbox" className="accent-green" checked={!s.hiddenSites.has(site.id)} onChange={() => s.toggleSite(site.id)} />
              <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: site.is_control ? COLORS.control : COLORS.impact }} />
              <span className="truncate">{site.name}</span>
              {site.is_control ? <span className="text-xs text-slate-light">témoin</span> : null}
            </label>
          ))}
        </div>
      </div>
    </aside>
  )
}

// ---------------------------------------------------------------------------------------------
// Activité par phase (festival / témoin)
// ---------------------------------------------------------------------------------------------

function PhaseTable({ stats, unit, hasImpact, hasControl }) {
  const kinds = [hasImpact && ['impact', 'Sites du festival'], hasControl && ['control', 'Site(s) témoin']].filter(Boolean)
  return (
    <div className="card p-4">
      <h3 className="font-bold flex items-center gap-2 mb-3">
        Activité moyenne par phase
        <Help text="Pour chaque phase : la moyenne, le nombre de nuits, et la plus petite / plus grande valeur d'un site sur une nuit. Si ces extrêmes se chevauchent d'une phase à l'autre, la différence entre les moyennes est à prendre avec prudence." />
      </h3>
      <div className="grid gap-3">
        {kinds.map(([kind, title]) => (
          <div key={kind}>
            <div className="text-sm font-medium mb-1.5 flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full" style={{ background: COLORS[kind] }} />{title}
            </div>
            <div className="grid grid-cols-3 gap-2">
              {PHASES.map((p) => {
                const st = stats[kind][p.key]
                const delta = p.key !== 'avant' ? change(stats[kind].avant, st) : null
                return (
                  <div key={p.key} className="bg-page rounded-sm p-2 min-w-0">
                    <div className="text-xs text-slate-light">{p.label}</div>
                    <div className="text-lg sm:text-xl font-bold tabular-nums">{st ? fmt(st.value) : '–'}</div>
                    <div className="text-[11px] text-slate-light">{unit}</div>
                    {st && <div className="text-[11px] text-slate-light tabular-nums">{st.nights} nuit{st.nights > 1 ? 's' : ''} · {fmt(st.min, 0)}–{fmt(st.max, 0)}</div>}
                    {delta != null && <div className={`text-xs font-medium tabular-nums ${delta < 0 ? 'text-orange-600 dark:text-orange-400' : 'text-green-dark'}`}>{fmtPct(delta)} vs avant</div>}
                  </div>
                )
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------------------------
// Écart BACI (festival comparé au témoin)
// ---------------------------------------------------------------------------------------------

function Baci({ stats }) {
  const items = PHASES.filter((p) => p.key !== 'avant').map((p) => ({
    ...p,
    f: change(stats.impact.avant, stats.impact[p.key]),
    t: change(stats.control.avant, stats.control[p.key]),
    d: baci(stats.impact.avant, stats.impact[p.key], stats.control.avant, stats.control[p.key]),
  }))
  return (
    <div className="card p-4">
      <h3 className="font-bold flex items-center gap-2 mb-3">
        Festival comparé au témoin
        <Help text="Le cœur du plan BACI : on compare l'évolution du festival à celle du témoin. Calcul : (festival pendant ÷ festival avant) ÷ (témoin pendant ÷ témoin avant) − 1. 0 % = les deux ont évolué pareil. −50 % = le festival a fini moitié plus bas que s'il avait suivi le témoin. C'est un chiffre descriptif : il ne dit pas si l'écart pourrait être dû au hasard." />
      </h3>
      <div className="grid gap-3 sm:grid-cols-2">
        {items.map((it) => (
          <div key={it.key} className="bg-page rounded-sm p-3">
            <div className="text-xs text-slate-light mb-1">{it.label} par rapport à avant</div>
            <div className="text-sm tabular-nums">Festival : <b>{fmtPct(it.f)}</b> · Témoin : <b>{fmtPct(it.t)}</b></div>
            <div className="mt-1 text-sm">
              Écart :{' '}
              <span className={`text-lg font-bold tabular-nums ${it.d == null ? '' : it.d < 0 ? 'text-orange-600 dark:text-orange-400' : 'text-green-dark'}`}>{it.d == null ? 'données insuffisantes' : fmtPct(it.d)}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------------------------
// Activité nuit par nuit
// ---------------------------------------------------------------------------------------------

function NightChart({ rows, controlIds, hiddenSites, hiddenNights, toggleNight, metric, group, unit, theme }) {
  const C = AXES[theme]
  // Toutes les nuits présentes (y compris écartées, pour pouvoir les remettre), triées par date
  const nights = [...new Set(rows.map((r) => r.night))].sort((a, b) => (a || '').localeCompare(b || ''))
  // Phase d'une nuit : celle de ses enregistrements (la première trouvée)
  const phaseOf = Object.fromEntries(nights.map((n) => [n, rows.find((r) => r.night === n)?.phase]))
  // Une valeur par nuit et par type : total ÷ heures sur les sites cochés (null si nuit écartée)
  const points = nights.map((n) => {
    const pt = { night: fmtNight(n) }
    for (const kind of ['impact', 'control']) {
      const rs = rows.filter((r) => r.night === n && !hiddenSites.has(r.site_id) && controlIds.has(r.site_id) === (kind === 'control'))
      const st = hiddenNights.has(n) ? null : aggregate(rs, metric, group, 'total')
      pt[kind] = st ? Math.round(st.value * 10) / 10 : null
    }
    return pt
  })
  // Zone colorée derrière les nuits « pendant » (de la première à la dernière)
  const during = nights.filter((n) => phaseOf[n] === 'pendant').map(fmtNight)
  const chip = { avant: 'border-line', pendant: 'border-green', apres: 'border-line' }

  return (
    <div className="card p-4">
      <h3 className="font-bold flex items-center gap-2 mb-2">
        Nuit par nuit
        <Help text="Activité de chaque nuit (sites cochés, total ÷ heures). La bande verte = nuits du festival. Cliquez sur une nuit sous le graphique pour l'écarter des calculs (pluie, vent fort, panne) ; elle passe en barré et peut être remise d'un autre clic." />
      </h3>
      <div className="h-60">
        <ResponsiveContainer>
          <ComposedChart data={points} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid stroke={C.grid} vertical={false} />
            {during.length > 0 && <ReferenceArea x1={during[0]} x2={during[during.length - 1]} fill={C.area} fillOpacity={0.15} />}
            <XAxis dataKey="night" tick={{ fill: C.axis, fontSize: 11 }} stroke={C.soft} />
            <YAxis tick={{ fill: C.soft, fontSize: 11 }} stroke={C.soft} width={44} />
            <Tooltip contentStyle={{ background: C.tipBg, borderColor: C.grid, borderRadius: 6 }} labelStyle={{ color: C.axis }}
              formatter={(v, name) => [v == null ? 'pas de données' : `${fmt(v)} ${unit}`, name]} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Line type="monotone" dataKey="impact" name="Festival" stroke={COLORS.impact} strokeWidth={2} dot={{ r: 3 }} connectNulls={false} isAnimationActive={false} />
            <Line type="monotone" dataKey="control" name="Témoin" stroke={COLORS.control} strokeWidth={2} dot={{ r: 3 }} connectNulls={false} isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      {/* Une étiquette par nuit : clic = écarter / remettre */}
      <div className="flex flex-wrap gap-1.5 mt-3">
        {nights.map((n) => {
          const off = hiddenNights.has(n)
          return (
            <button key={n ?? 'none'} type="button" onClick={() => toggleNight(n)} aria-pressed={!off}
              title={off ? 'Nuit écartée : cliquer pour la remettre' : 'Cliquer pour écarter cette nuit'}
              aria-label={`Nuit du ${fmtNight(n)}${off ? ' (écartée)' : ''}`}
              className={`text-xs px-2 py-1 rounded-sm border tabular-nums ${chip[phaseOf[n]] || 'border-line'} ${off ? 'line-through opacity-50' : 'hover:bg-green-soft'}`}>
              {fmtNight(n)}
            </button>
          )
        })}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------------------------
// Même comparaison, groupe par groupe
// ---------------------------------------------------------------------------------------------

function GroupTable({ groups, statsFor, current, setGroup, unit }) {
  // Un calcul complet par groupe (statsFor fait festival / témoin × 3 phases)
  const lines = ['all', ...groups].map((g) => {
    const st = statsFor(g)
    return { g, st, d: baci(st.impact.avant, st.impact.pendant, st.control.avant, st.control.pendant) }
  })
  return (
    <div className="card p-4 min-w-0">
      <h3 className="font-bold flex items-center gap-2 mb-2">
        Par groupe d’espèces
        <Help text={`Activité (${unit}) de chaque groupe, phase par phase, puis l'écart festival / témoin pendant le festival (même calcul que plus haut). Cliquez sur un groupe pour l'utiliser dans toute la page. Un groupe rare donne des chiffres très instables.`} />
      </h3>
      {/* overflow-x-auto : sur téléphone, le tableau défile horizontalement au lieu de déborder */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr>
              <th className="th" rowSpan={2}>Groupe</th>
              <th className="th text-center" colSpan={3}>Festival</th>
              <th className="th text-center" colSpan={3}>Témoin</th>
              <th className="th text-right" rowSpan={2}>Écart pendant</th>
            </tr>
            <tr>{[0, 1].flatMap((i) => PHASES.map((p) => <th key={`${i}${p.key}`} className="th text-right">{p.label}</th>))}</tr>
          </thead>
          <tbody>
            {lines.map(({ g, st, d }) => (
              <tr key={g} className={current === g ? 'bg-green-soft' : ''}>
                <td className="td">
                  <button type="button" className="hover:underline text-left" onClick={() => setGroup(g)}>{g === 'all' ? 'Tous' : g}</button>
                </td>
                {['impact', 'control'].flatMap((k) => PHASES.map((p) => <td key={k + p.key} className="td text-right">{fmt(st[k][p.key]?.value)}</td>))}
                <td className={`td text-right font-medium ${d == null ? '' : d < 0 ? 'text-orange-600 dark:text-orange-400' : 'text-green-dark'}`}>{fmtPct(d)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------------------------
// Détail site × nuit + export CSV
// ---------------------------------------------------------------------------------------------

function DetailTable({ data, rows, controlIds, camp, metric, group, unit, hours }) {
  const siteName = Object.fromEntries(data.sites.map((s) => [s.id, s.name]))
  const phaseLabel = Object.fromEntries(PHASES.map((p) => [p.key, p.label]))

  // Fabrique le fichier CSV et le fait télécharger par le navigateur.
  // Format « Excel français » : séparateur « ; », virgule décimale, et un BOM (﻿) au début
  // pour qu'Excel reconnaisse l'UTF-8 (sinon les accents s'affichent mal).
  const download = () => {
    const p = data.params
    const head = ['campagne', 'site', 'type', 'nuit', 'phase', 'fichiers', 'heures', 'contacts', 'cris',
      ...data.groups.map((g) => `contacts ${g}`), 'seuil', 'duree_contact_s', 'plage']
    const num = (v, d = 4) => String(Math.round(v * 10 ** d) / 10 ** d).replace('.', ',')
    const lines = rows.map((r) => [
      camp.name, siteName[r.site_id], controlIds.has(r.site_id) ? 'temoin' : 'festival', r.night || '', r.phase,
      r.files, num(r.hours), r.contacts, r.calls, ...data.groups.map((g) => r.by_group[g] ?? 0),
      num(p.threshold, 2), p.window, hours ? `${fmtHour(hours[0])}-${fmtHour(hours[1])}` : 'tout',
    ])
    // Chaque valeur est entourée de guillemets (un « ; » dans un nom de site ne casse pas le fichier)
    const csv = [head, ...lines].map((l) => l.map((v) => `"${String(v).replace(/"/g, '""')}"`).join(';')).join('\r\n')
    // Blob = un fichier fabriqué en mémoire ; createObjectURL lui donne une adresse temporaire
    const url = URL.createObjectURL(new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8' }))
    const a = document.createElement('a')
    a.href = url
    // \p{L} = toute lettre (accents compris), \p{N} = tout chiffre ; le reste devient « _ »
    a.download = `chiro-impact_${camp.name.replace(/[^\p{L}\p{N}_-]+/gu, '_')}_par_nuit.csv`
    a.click()
    URL.revokeObjectURL(url) // libère la mémoire
  }

  return (
    <div className="card p-4 min-w-0">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
        <h3 className="font-bold flex items-center gap-2">
          Détail par site et par nuit
          <Help text="Les lignes utilisées dans les calculs ci-dessus (sites cochés, nuits non écartées). Le fichier CSV contient ces lignes avec les contacts de chaque groupe et les réglages utilisés : c'est le point de départ d'une analyse statistique (par exemple un modèle de comptage, effet « phase × type de site »). Il s'ouvre dans Excel ou LibreOffice." />
        </h3>
        <button type="button" className="btn btn-green text-sm" onClick={download} disabled={!rows.length}>Télécharger le CSV</button>
      </div>
      <div className="overflow-x-auto max-h-96 overflow-y-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-surface">
            <tr>
              <th className="th">Site</th><th className="th">Nuit</th><th className="th">Phase</th>
              <th className="th text-right">Heures</th><th className="th text-right">Contacts</th>
              <th className="th text-right">Cris</th><th className="th text-right">{unit}{group !== 'all' ? ` (${group})` : ''}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={`${r.site_id}-${r.night}-${r.phase}`}>
                <td className="td">
                  <span className="inline-block w-2 h-2 rounded-full mr-2" style={{ background: controlIds.has(r.site_id) ? COLORS.control : COLORS.impact }} />
                  {siteName[r.site_id]}
                </td>
                <td className="td">{fmtNight(r.night)}</td>
                <td className="td">{phaseLabel[r.phase] || r.phase}</td>
                <td className="td text-right">{fmt(r.hours, 2)}</td>
                <td className="td text-right">{r.contacts}</td>
                <td className="td text-right">{r.calls}</td>
                <td className="td text-right font-medium">{r.hours > 0 ? fmt(valueOf(r, metric, group) / r.hours) : '–'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
