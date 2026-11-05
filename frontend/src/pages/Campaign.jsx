/*
 * ============================================================================
 * Campaign.jsx — la page d'UNE campagne (adresse « /campaigns/:id »)
 * ============================================================================
 *
 * RÔLE DE LA PAGE
 *   C'est le poste de travail d'une campagne. On y trouve :
 *     - deux onglets : « Enregistrements » (la liste des fichiers WAV, rangés
 *       par phase avant / pendant / après) et « Synthèse » (les indicateurs) ;
 *     - un panneau avec la zone de dépôt des fichiers, les dates du festival
 *       et la liste des sites d'enregistrement.
 *   Pendant que le serveur analyse des fichiers, la page se recharge toute
 *   seule toutes les 3 secondes pour montrer l'avancement.
 *
 * DONNÉES DEMANDÉES À L'API (voir frontend/src/api.js)
 *   - api.campaign(id)            → GET   /api/campaigns/{id}             : la campagne (nom, dates, sites…)
 *   - api.recordings(id)          → GET   /api/campaigns/{id}/recordings  : ses enregistrements
 *   - api.summary(id)             → GET   /api/campaigns/{id}/summary     : la synthèse chiffrée
 *   - api.updateRecording(id, …)  → PATCH /api/recordings/{id}            : corriger la phase d'un fichier
 *   - api.reprocess(id)           → POST  /api/recordings/{id}/reprocess  : relancer une analyse en erreur
 *   - api.deleteRecording(id)     → DELETE /api/recordings/{id}           : supprimer un fichier
 *   (Le dépôt, les dates et les sites passent par les composants UploadZone,
 *   FestivalDates et Sites, rangés dans src/components/.)
 *
 * SOMMAIRE DES COMPOSANTS ET FONCTIONS DU FICHIER
 *   - Campaign         : la page entière (export par défaut).
 *   - Recordings       : la liste des fichiers, un bloc par phase.
 *   - RecordingsTable  : version « tableau » de la liste (grands écrans).
 *   - RecordingCard    : version « carte » d'un fichier (téléphone / tablette).
 *   - PhaseSelect      : le menu déroulant pour corriger la phase d'un fichier.
 *   - Actions          : les liens « relancer » et « supprimer » d'un fichier.
 *   - TzMark           : le petit avertissement « ⚠ fuseau ? ».
 *   - fmtDur, fmtDate, fmtDay : mise en forme des durées et des dates
 *     (fmtDur et fmtDate sont aussi utilisées par la page Recording.jsx).
 *
 * RAPPEL SUR TAILWIND
 *   Les classes (« grid gap-5 text-sm »…) sont des petits styles Tailwind.
 *   Les préfixes s'appliquent à partir d'une largeur d'écran :
 *   sm: ≥ 640 px, md: ≥ 768 px, lg: ≥ 1024 px, xl: ≥ 1280 px.
 *   `dark:` ne s'applique qu'en thème sombre. `card`, `btn`, `th`, `td`… sont
 *   des raccourcis maison définis dans src/index.css.
 */

// --- Imports ---
// Les hooks React utilisés ici : useState (mémoriser une valeur), useEffect
// (lancer du code après l'affichage) et useCallback (garder la même fonction
// d'un affichage à l'autre). Chacun est expliqué au moment où il sert.
import { useCallback, useEffect, useState } from 'react'
// Link : lien interne sans rechargement de page.
// useParams : lit les morceaux variables de l'adresse (ici le `:id` de « /campaigns/:id »).
import { Link, useParams } from 'react-router-dom'
// api : toutes les requêtes au serveur. PHASES : la liste [avant, pendant, après] avec leurs libellés.
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
  // --- Quelle campagne afficher ? ---
  // useParams() renvoie un objet avec les paramètres de l'adresse. Pour
  // « /campaigns/7 », on obtient { id: '7' } (attention : c'est du texte, pas un nombre).
  // `const { id } = ...` est une déstructuration : on sort directement la clé `id`.
  const { id } = useParams()

  // --- L'état de la page ---
  // useState garde une valeur en mémoire entre deux affichages. Appeler la
  // fonction `setXxx` change la valeur ET redessine la page (re-rendu).
  const [camp, setCamp] = useState(null)       // la campagne (null tant qu'elle n'est pas chargée)
  const [recs, setRecs] = useState([])         // ses enregistrements
  const [summary, setSummary] = useState(null) // la synthèse chiffrée
  const [tab, setTab] = useState('recs')       // onglet affiché : 'recs' ou 'summary'
  const [error, setError] = useState('')       // message d'erreur éventuel

  // --- Chargement des données ---
  // Recharge tout (campagne, enregistrements, synthèse).
  // Promise.all lance les 3 requêtes EN MÊME TEMPS et attend qu'elles soient
  // toutes terminées. Les 3 réponses arrivent dans un tableau, qu'on
  // déstructure en [c, r, s]. Si une seule échoue, on passe dans .catch.
  //
  // useCallback(fonction, [id]) : React renvoie la MÊME fonction à chaque
  // affichage, tant que `id` ne change pas. Sans ça, `load` serait une nouvelle
  // fonction à chaque re-rendu, et les useEffect qui dépendent de `load`
  // (juste en dessous) se relanceraient en boucle.
  const load = useCallback(() => {
    Promise.all([api.campaign(id), api.recordings(id), api.summary(id)])
      .then(([c, r, s]) => { setCamp(c); setRecs(r); setSummary(s) })
      .catch((e) => setError(e.message))
  }, [id])
  // useEffect lance `load` après le premier affichage, puis à chaque fois que
  // `load` change (c'est-à-dire quand on passe à une autre campagne, car `id` change).
  useEffect(() => { load() }, [load])

  // --- Rafraîchissement automatique pendant l'analyse ---
  // Tant qu'il reste des fichiers en cours d'analyse, on rafraîchit toutes les 3 s.
  // .some(...) renvoie true si AU MOINS UN fichier vérifie la condition.
  const working = recs.some((r) => r.status === 'pending' || r.status === 'processing')
  useEffect(() => {
    // Rien en cours : on ne programme rien.
    if (!working) return
    // setInterval appelle `load` toutes les 3000 ms (3 s).
    const t = setInterval(load, 3000)
    // La fonction renvoyée par un useEffect est sa « fonction de nettoyage ».
    // React l'appelle avant de relancer l'effet, ou quand on quitte la page.
    // Ici elle arrête le minuteur : quand plus rien n'est en cours (working
    // passe à false), ou quand on change de page, les rechargements s'arrêtent.
    return () => clearInterval(t)
  }, [working, load])

  // --- Cas particuliers : erreur ou chargement ---
  // On sort tôt de la fonction : tant que la campagne n'est pas là, on affiche
  // juste un message. (Tous les hooks sont appelés AVANT ces `return` : React
  // exige que les hooks soient appelés dans le même ordre à chaque affichage.)
  if (error) return <p className="text-red-600 dark:text-red-400">{error}</p>
  if (!camp) return <p className="text-slate-light">Chargement…</p>

  // --- Petites valeurs calculées pour l'affichage ---
  // Boolean(...) transforme la valeur en vrai / faux : true seulement si les DEUX dates sont renseignées.
  const hasDates = Boolean(camp.festival_start && camp.festival_end)
  // tabBtn fabrique un bouton d'onglet. `k` = la clé de l'onglet, `label` = le texte.
  // L'onglet actif (tab === k) a une bordure verte en dessous ; les autres ont
  // une bordure transparente. Le ternaire `condition ? 'classes A' : 'classes B'`
  // choisit les classes, et le template literal (backticks + ${...}) les colle
  // aux classes communes.
  const tabBtn = (k, label) => (
    <button onClick={() => setTab(k)} className={`px-3 sm:px-4 py-2 border-b-[3px] -mb-[2px] font-medium whitespace-nowrap ${tab === k ? 'border-green text-slate' : 'border-transparent text-slate-light hover:text-slate'}`}>{label}</button>
  )

  return (
    <div className="grid gap-5 sm:gap-6">
      {/* En-tête : lien retour, nom de la campagne, description et dates du festival. */}
      <div className="min-w-0">
        <Link to="/" className="text-sm text-slate-light hover:text-slate">← Campagnes</Link>
        <h2 className="text-xl sm:text-2xl font-bold break-words">{camp.name}</h2>
        <p className="text-slate-light text-sm sm:text-base">
          {camp.description}
          {/* Les dates ne s'affichent que si elles existent (rendu conditionnel avec &&).
              Sur téléphone, elles passent sur leur propre ligne (`block`) ; à partir de
              sm: elles suivent la description sur la même ligne (`sm:inline`), séparées
              par « · » (séparateur affiché seulement s'il y a une description). */}
          {hasDates && <span className="block sm:inline"><span className="hidden sm:inline">{camp.description ? ' · ' : ''}</span>festival les nuits du {fmtDay(camp.festival_start)} au {fmtDay(camp.festival_end)}</span>}
        </p>
      </div>

      {/* Mise en page principale. Sur petit écran : une seule colonne, et l'ordre
          d'affichage est réglé par les classes `order-1`, `order-2`, `order-3`
          (dépôt, puis liste, puis dates et sites).
          À partir de xl: (1280 px) : deux colonnes (la liste à gauche, un panneau de
          340 px à droite) et deux rangées ; `xl:order-none` annule l'ordre du mobile
          et chaque bloc est placé dans la grille avec col-start / row-start.
          minmax(0,1fr) et min-w-0 empêchent un long nom de fichier d'élargir la colonne. */}
      <div className="grid gap-5 sm:gap-6 xl:grid-cols-[minmax(0,1fr)_340px] xl:grid-rows-[auto_1fr]">
        {/* Bloc « onglets » : la barre d'onglets puis le contenu de l'onglet choisi.
            Sur grand écran il occupe la colonne de gauche sur les deux rangées (row-span-2). */}
        <section className="min-w-0 order-2 xl:order-none xl:col-start-1 xl:row-start-1 xl:row-span-2">
          {/* overflow-x-auto : si les onglets ne tiennent pas en largeur, on peut les faire défiler. */}
          <div className="flex gap-1 border-b-2 border-line mb-4 overflow-x-auto overflow-y-hidden">
            {tabBtn('recs', `Enregistrements (${recs.length})`)}
            {tabBtn('summary', 'Synthèse')}
          </div>
          {/* Ternaire : on affiche soit la liste des fichiers, soit la synthèse.
              `onChange={load}` passe la fonction de rechargement aux enfants : après
              une modification (phase, suppression…), ils l'appellent pour que la page
              se mette à jour. */}
          {tab === 'recs' ? <Recordings recs={recs} hasDates={hasDates} onChange={load} /> : <Summary summary={summary} />}
        </section>
        {/* Zone de dépôt : en haut sur mobile (order-1), en haut à droite sur grand écran. */}
        <div className="order-1 xl:order-none xl:col-start-2 xl:row-start-1">
          {/* key : la zone se réinitialise quand les dates changent (phase « Auto » activable).
              Explication : quand la `key` d'un composant change, React jette l'ancien
              et en crée un neuf, avec un état remis à zéro. La key est construite à
              partir des dates et du nombre de sites, donc toute modification de
              ceux-ci repart d'une zone de dépôt propre. */}
          <UploadZone key={`${camp.festival_start}-${camp.festival_end}-${camp.sites.length}`} campaign={camp} onUploaded={load} />
        </div>
        {/* Dates du festival et sites : en bas sur mobile (order-3), côte à côte sur
            tablette (md:grid-cols-2), l'un sous l'autre dans le panneau de droite sur
            grand écran (xl:grid-cols-1). */}
        <div className="order-3 xl:order-none xl:col-start-2 xl:row-start-2 grid gap-4 md:grid-cols-2 xl:grid-cols-1 content-start">
          <FestivalDates campaign={camp} onChange={load} />
          <Sites campaign={camp} onChange={load} />
        </div>
      </div>
    </div>
  )
}

// --- État d'analyse d'un fichier ---
// Pour chaque statut renvoyé par le serveur : [texte affiché, classes de couleur du badge].
const STATUS = {
  pending: ['En attente', 'bg-line text-slate-light'],
  processing: ['Analyse…', 'bg-yellow/30 text-slate'],
  done: ['Analysé', 'bg-green-soft text-green-dark'],
  error: ['Erreur', 'bg-red-100 dark:bg-red-900/40 text-red-700 dark:text-red-300'],
}

// Renvoie [texte, classes] du badge d'état d'un enregistrement `r`.
function statusOf(r) {
  // Statut inconnu : on retombe sur « En attente » (l'opérateur || prend la 2e valeur si la 1re est vide).
  const [label, cls] = STATUS[r.status] || STATUS.pending
  // Pendant l'analyse d'un long fichier, on affiche l'avancement.
  // r.progress va de 0 à 1 : × 100 puis arrondi donne un pourcentage (ex. « Analyse… 42 % »).
  return [r.status === 'processing' && r.progress > 0 ? `${label} ${Math.round(r.progress * 100)} %` : label, cls]
}

// Texte de la bulle d'aide de la colonne « Phase » (utilisé dans le tableau).
const PHASE_HELP = "Phase du fichier. « auto » = calculée depuis la date du fichier et les dates du festival. Tu peux la corriger ici : le fichier change alors de groupe et la synthèse est recalculée."

// Liste des enregistrements, groupée par phase.
// Ordinateur (≥ 1024 px) : un tableau. Téléphone / tablette : des cartes (1 ou 2 colonnes).
// Props : recs (les fichiers), hasDates (le festival a-t-il des dates ?), onChange (recharger la page).
function Recordings({ recs, hasDates, onChange }) {
  // Aucun fichier : un message qui indique quoi faire.
  if (recs.length === 0) return <div className="card p-6 text-slate-light">Aucun enregistrement. Dépose des fichiers WAV avec la zone « Déposer des enregistrements ».</div>
  return (
    <div className="grid gap-4">
      {/* Un bloc par phase, dans l'ordre avant → pendant → après. */}
      {PHASES.map((p) => {
        // .filter garde seulement les fichiers de cette phase.
        const rows = recs.filter((r) => r.phase === p.key)
        // Phase sans fichier : renvoyer null dans un .map n'affiche rien pour cet élément.
        if (!rows.length) return null
        return (
          <div key={p.key} className="card overflow-hidden">
            {/* Titre du bloc : nom de la phase + nombre de fichiers. */}
            <div className="px-3 py-2 font-bold bg-green-soft border-b border-line">{p.label} <span className="text-slate-light font-normal text-sm">· {rows.length} fichier(s)</span></div>
            {/* Les DEUX versions sont rendues ; c'est le CSS qui choisit laquelle se voit :
                le tableau est caché sous lg: (classe `hidden lg:table` dans RecordingsTable),
                les cartes sont cachées à partir de lg: (`lg:hidden`). */}
            <RecordingsTable rows={rows} hasDates={hasDates} onChange={onChange} />
            <div className="lg:hidden grid md:grid-cols-2 divide-y md:divide-y-0 divide-line">
              {/* `odd` (impair) sert à tracer une bordure à gauche des cartes de la 2e colonne.
                  i % 2 === 1 : le reste de la division par 2 vaut 1 pour les index impairs. */}
              {rows.map((r, i) => <RecordingCard key={r.id} r={r} hasDates={hasDates} onChange={onChange} odd={i % 2 === 1} />)}
            </div>
          </div>
        )
      })}
    </div>
  )
}

// Version « tableau » (visible à partir de 1024 px de large).
function RecordingsTable({ rows, hasDates, onChange }) {
  return (
    // `hidden lg:table` : caché par défaut, affiché comme un tableau à partir de lg:.
    <table className="hidden lg:table w-full text-sm">
      {/* En-têtes de colonnes. Certaines ont une bulle d'aide « ? ». */}
      <thead><tr>
        <th className="th">Fichier · date</th>
        <th className="th">Site</th>
        <th className="th"><span className="inline-flex items-center gap-1">Phase <Help text={PHASE_HELP} /></span></th>
        <th className="th text-right">Durée</th>
        <th className="th text-right"><span className="inline-flex items-center gap-1">Cris <Help text="Nombre de cris détectés au-dessus du seuil 0,3." /></span></th>
        <th className="th text-right"><span className="inline-flex items-center gap-1">Contacts <Help text="Tranches de 5 s contenant au moins un cri. C'est l'unité qui sert à calculer l'activité." /></span></th>
        <th className="th">Groupes</th>
        <th className="th">État</th>
        {/* sr-only : texte invisible à l'écran mais lu par les lecteurs d'écran
            (la colonne contient des boutons, elle n'a pas besoin de titre visible). */}
        <th className="th"><span className="sr-only">Actions</span></th>
      </tr></thead>
      <tbody>
        {/* Une ligne <tr> par fichier. */}
        {rows.map((r) => {
          const [label, cls] = statusOf(r)
          return (
            <tr key={r.id} className="hover:bg-green-soft/50 align-top">
              {/* Nom du fichier (lien vers sa page de détail) et date d'enregistrement.
                  `!whitespace-normal` : le « ! » de Tailwind force ce style par-dessus
                  celui de la classe `td` (qui interdit le retour à la ligne). */}
              <td className="td !whitespace-normal">
                <Link to={`/recordings/${r.id}`} className="font-medium hover:text-green-dark break-all">{r.filename}</Link>
                <div className="text-xs text-slate-light">{fmtDate(r.recorded_at)}<TzMark r={r} /></div>
              </td>
              {/* Site, avec la mention « (témoin) » si c'est le site de contrôle. */}
              <td className="td !whitespace-normal">{r.site_name}{r.is_control ? <span className="text-slate-light"> (témoin)</span> : null}</td>
              <td className="td"><PhaseSelect r={r} hasDates={hasDates} onChange={onChange} /></td>
              <td className="td text-right">{fmtDur(r.duration)}</td>
              {/* Les chiffres n'ont de sens qu'une fois l'analyse terminée ; sinon un tiret. */}
              <td className="td text-right">{r.status === 'done' ? r.n_calls : '–'}</td>
              <td className="td text-right">{r.status === 'done' ? r.n_contacts : '–'}</td>
              {/* Groupes : la liste jointe par des virgules. Si elle est vide, join donne ''
                  (considéré comme « faux »), et `||` affiche alors « aucun » (analyse finie)
                  ou rien (analyse pas encore faite). */}
              <td className="td !whitespace-normal text-xs min-w-[8rem]">{r.groups.join(', ') || (r.status === 'done' ? 'aucun' : '')}</td>
              {/* Badge d'état. title={r.error} : au survol, le message d'erreur du serveur s'affiche. */}
              <td className="td"><span className={`text-xs px-2 py-0.5 rounded-sm ${cls}`} title={r.error}>{label}</span></td>
              <td className="td text-right"><Actions r={r} onChange={onChange} /></td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

// Version « carte » d'un fichier (téléphone et tablette) : les mêmes informations
// que le tableau, empilées pour tenir dans un écran étroit.
function RecordingCard({ r, hasDates, onChange, odd }) {
  const [label, cls] = statusOf(r)
  return (
    // Sur tablette (md:), les cartes sont sur 2 colonnes : celles de droite (odd)
    // ont une bordure à gauche, et toutes ont une bordure en bas, pour dessiner un quadrillage.
    <div className={`p-3 grid gap-2 text-sm ${odd ? 'md:border-l md:border-line' : ''} md:border-b md:border-line`}>
      {/* 1re ligne : nom du fichier (lien) et badge d'état. */}
      <div className="flex items-start gap-2">
        <Link to={`/recordings/${r.id}`} className="font-medium hover:text-green-dark break-all flex-1 min-w-0">{r.filename}</Link>
        <span className={`text-xs px-2 py-0.5 rounded-sm whitespace-nowrap ${cls}`} title={r.error}>{label}</span>
      </div>
      {/* 2e ligne : site, date (avec l'avertissement de fuseau si besoin) et durée. */}
      <div className="text-xs text-slate-light">
        {r.site_name}{r.is_control ? ' (témoin)' : ''} · {fmtDate(r.recorded_at)}<TzMark r={r} /> · {fmtDur(r.duration)}
      </div>
      {/* 3e ligne, seulement si l'analyse est finie : cris, contacts et groupes.
          `tabular-nums` : chiffres de largeur égale, pour qu'ils s'alignent. */}
      {r.status === 'done' && (
        <div className="text-xs">
          <b className="tabular-nums">{r.n_calls}</b> cris · <b className="tabular-nums">{r.n_contacts}</b> contacts
          {r.groups.length > 0 && <span className="text-slate-light"> · {r.groups.join(', ')}</span>}
        </div>
      )}
      {/* Dernière ligne : le choix de phase à gauche, les actions à droite.
          Le <span className="flex-1" /> vide prend toute la place du milieu et pousse les actions à droite. */}
      <div className="flex items-center gap-3 flex-wrap">
        <PhaseSelect r={r} hasDates={hasDates} onChange={onChange} />
        <span className="flex-1" />
        <Actions r={r} onChange={onChange} />
      </div>
    </div>
  )
}

// Menu déroulant pour corriger la phase d'un fichier.
// Choisir une valeur l'envoie tout de suite au serveur (api.updateRecording),
// puis `.then(onChange)` recharge la page pour voir le fichier changer de bloc.
function PhaseSelect({ r, hasDates, onChange }) {
  return (
    <span className="inline-flex items-center gap-1">
      {/* aria-label : chaque menu a un nom qui cite le fichier, pour les lecteurs d'écran. */}
      <select className="border border-line rounded-sm bg-surface text-xs px-1.5 py-1" aria-label={`Phase de ${r.filename}`}
        value={r.phase} onChange={(e) => api.updateRecording(r.id, { phase: e.target.value }).then(onChange)}>
        {/* Une option par phase. */}
        {PHASES.map((ph) => <option key={ph.key} value={ph.key}>{ph.label}</option>)}
        {/* L'option « auto » n'existe que si le festival a des dates : sans dates,
            le serveur ne peut pas calculer la phase. */}
        {hasDates && <option value="auto">↻ recalculer (auto)</option>}
      </select>
      {/* Petit badge « auto » quand la phase actuelle a été calculée et non choisie à la main. */}
      {r.phase_source === 'auto' && <span className="text-[10px] uppercase text-green-dark" title="Phase calculée automatiquement">auto</span>}
    </span>
  )
}

// Liens d'action d'un fichier : « relancer » (seulement en cas d'erreur) et
// « supprimer » (avec confirmation en deux clics, comme sur la page des campagnes).
function Actions({ r, onChange }) {
  const [confirm, setConfirm] = useState(false)
  return (
    <span className="inline-flex items-center gap-3 text-xs whitespace-nowrap">
      {/* Analyse en erreur : on peut demander au serveur de la refaire. */}
      {r.status === 'error' && <button className="text-slate-light hover:text-slate py-1" onClick={() => api.reprocess(r.id).then(onChange)}>relancer</button>}
      {/* 1er clic : « supprimer » devient « confirmer ? ». 2e clic : suppression.
          autoFocus place le focus sur le bouton « confirmer ? » dès qu'il apparaît ;
          ainsi, cliquer ailleurs déclenche onBlur et annule la confirmation. */}
      {confirm
        ? <button className="text-red-600 dark:text-red-400 font-medium py-1" onClick={() => api.deleteRecording(r.id).then(onChange)} onBlur={() => setConfirm(false)} autoFocus>confirmer ?</button>
        : <button className="text-slate-light hover:text-red-600 py-1" onClick={() => setConfirm(true)}>supprimer</button>}
    </span>
  )
}

// Petit repère quand l'heure vient du nom du fichier (fuseau inconnu : UTC par défaut sur AudioMoth).
// Un composant qui renvoie null n'affiche rien : c'est le cas quand l'heure a été lue dans le fichier lui-même.
function TzMark({ r }) {
  if (r.time_source !== 'nom du fichier') return null
  return <span className="text-orange-600 dark:text-orange-400" title="Heure lue dans le nom du fichier : fuseau inconnu (l'AudioMoth nomme ses fichiers en UTC par défaut)"> ⚠ fuseau ?</span>
}

// --- Mise en forme ---
// `export` (sans default) : ces fonctions peuvent être importées par d'autres
// fichiers avec leur nom entre accolades, comme le fait Recording.jsx :
// `import { fmtDate, fmtDur } from './Campaign'`.

// Durée en secondes → texte lisible. Exemples : 12.34 → « 12.3 s » ;
// 125 → « 2 min 5 s » ; 4000 → « 1 h 6 min » (au-delà d'une heure, les secondes ne sont plus affichées).
export function fmtDur(s) {
  // `== null` (deux signes égal) attrape à la fois null et undefined : durée inconnue.
  if (s == null) return '–'
  if (s < 60) return `${s.toFixed(1)} s`
  // Math.floor arrondit vers le bas ; `%` donne le reste de la division (les secondes restantes).
  const m = Math.floor(s / 60), sec = Math.round(s % 60)
  return m < 60 ? `${m} min ${sec} s` : `${Math.floor(m / 60)} h ${m % 60} min`
}

// '2024-07-12T22:30:00' → '12/07/2024 22:30'
// La date est découpée comme du texte (split), sans passer par l'objet Date de
// JavaScript : on affiche exactement l'heure envoyée par le serveur, sans
// conversion de fuseau par le navigateur.
export function fmtDate(iso) {
  if (!iso) return 'date inconnue'
  // split('T') coupe '2024-07-12T22:30:00' en ['2024-07-12', '22:30:00'].
  const [d, t] = iso.split('T')
  const [y, m, j] = d.split('-')
  // t.slice(0, 5) garde 'HH:MM'. S'il n'y a pas d'heure (t vide), on n'ajoute rien.
  return `${j}/${m}/${y}${t ? ' ' + t.slice(0, 5) : ''}`
}

// '2024-07-12' → '12/07/2024' (pour les dates du festival, qui n'ont pas d'heure).
function fmtDay(iso) {
  const [y, m, j] = iso.split('-')
  return `${j}/${m}/${y}`
}
