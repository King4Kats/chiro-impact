/*
 * Summary.jsx — la synthèse chiffrée d'une campagne (tuiles, graphiques et tableau par site).
 *
 * Il ne fait aucune requête lui-même : il reçoit l'objet `summary` déjà chargé par la page
 * (réponse de GET /api/campaigns/{id}/summary) et se contente de l'afficher.
 *
 * Plan BACI (Before / After × Control / Impact, voir README.md) : on compare l'évolution des
 * sites du festival à celle du ou des sites témoins. C'est pourquoi les deux types de sites sont
 * toujours affichés séparément.
 *
 * Travaille avec :
 *  - pages/Campaign.jsx : charge la synthèse avec api.summary() et l'affiche ici ;
 *  - backend/app/main.py (route summary) et analysis.py : calculent les chiffres ;
 *  - api.js : PHASES (ordre et libellés des phases) ;
 *  - theme.js : useTheme() pour adapter les couleurs des graphiques au thème ;
 *  - recharts : la bibliothèque de graphiques.
 */
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { PHASES } from '../api'
import Help from './Help'
import { useTheme } from '../theme'

// Couleurs des groupes dans le graphique de diversité (teintes douces, lisibles sur blanc)
// La clé est le nom du groupe tel que le serveur le renvoie. Un groupe absent de la liste prend la couleur « Autre ».
const GROUP_COLORS = {
  'Pipistrelles': '#80c595', 'Myotis': '#5b8def', 'Noctules / Sérotines': '#f0a35e',
  'Oreillards': '#b48fd9', 'Barbastelle': '#44405a', 'Rhinolophes': '#e46a6a', 'Autre': '#b8b5c4',
}
// Couleurs des axes et du quadrillage, selon le thème clair / sombre (recharts dessine en SVG)
// Les classes Tailwind ne s'appliquent pas à l'intérieur des graphiques : recharts attend des
// couleurs écrites en dur dans ses props. D'où ce petit tableau, un jeu de couleurs par thème.
// La Barbastelle (ardoise foncée) deviendrait invisible sur fond sombre : elle a sa propre teinte ici.
const CHART = {
  light: { grid: '#e6e8e6', axis: '#44405a', axisSoft: '#7a7790', tipBg: '#ffffff', tipLine: '#e6e8e6', barbastelle: '#44405a' },
  dark: { grid: '#3a374b', axis: '#e8e6f0', axisSoft: '#a3a0b6', tipBg: '#22202d', tipLine: '#3a374b', barbastelle: '#a7a2c4' },
}

// Synthèse d'une campagne. Design BACI : les sites du festival et le site témoin sont TOUJOURS
// présentés séparément (les mélanger ferait disparaître l'effet qu'on cherche à mesurer).
export default function Summary({ summary }) {
  // Le thème est lu AVANT le `return null` : un hook React doit toujours être appelé, dans le
  // même ordre, à chaque affichage. On ne peut donc pas le placer après une sortie anticipée.
  const { theme } = useTheme()
  // Tant que la synthèse n'est pas chargée, on n'affiche rien.
  if (!summary) return null
  // Préparation de l'affichage :
  //  - C : les couleurs du thème courant ;
  //  - colorOf : couleur d'un groupe d'espèces (cas spécial de la Barbastelle, voir CHART) ;
  //  - tooltip : style commun des infobulles des deux graphiques (fond, bordure, surbrillance de la colonne survolée).
  const C = CHART[theme]
  const colorOf = (g) => (g === 'Barbastelle' ? C.barbastelle : GROUP_COLORS[g] || GROUP_COLORS.Autre)
  const tooltip = { contentStyle: { background: C.tipBg, borderColor: C.tipLine, borderRadius: 6 }, labelStyle: { color: C.axis }, cursor: { fill: C.grid, opacity: 0.5 } }
  // « Déstructuration » : on sort d'un coup quatre champs de l'objet summary.
  //  - by_type : chiffres par type de site (impact = festival, control = témoin) puis par phase ;
  //  - sites : un élément par site, avec ses chiffres par phase ;
  //  - calls_by_group : nombre de cris par phase puis par groupe d'espèces ;
  //  - pending : nombre de fichiers pas encore analysés.
  // hasControl / hasImpact : existe-t-il au moins un site témoin / un site festival ?
  // (.some renvoie vrai si au moins un élément remplit la condition.)
  const { by_type, sites, calls_by_group, pending } = summary
  const hasControl = sites.some((s) => s.site.is_control)
  const hasImpact = sites.some((s) => !s.site.is_control)

  // Graphique « activité » : par phase, une barre festival + une barre témoin
  // recharts attend un tableau d'objets : un objet par groupe de barres (ici une phase),
  // une propriété par série (festival, temoin).
  const activity = PHASES.map((p) => ({
    phase: p.label,
    festival: by_type.impact[p.key].contacts_per_hour,
    temoin: by_type.control[p.key].contacts_per_hour,
  }))
  // Graphique « diversité » : cris par groupe, empilés par phase (tous sites)
  // groups : liste sans doublon (new Set) de tous les groupes vus dans au moins une phase.
  // diversity : pour chaque phase, { phase: 'Avant', Pipistrelles: 12, Myotis: 3, … }
  // (`...objet` recopie toutes les propriétés de l'objet dans le nouvel objet).
  const groups = [...new Set(Object.values(calls_by_group).flatMap((g) => Object.keys(g)))]
  const diversity = PHASES.map((p) => ({ phase: p.label, ...calls_by_group[p.key] }))

  return (
    <div className="grid gap-6">
      {/* Avertissements en jaune : analyse pas finie, ou pas de site témoin */}
      {pending > 0 && <p className="text-sm bg-yellow/20 px-3 py-2 rounded-sm">{pending} fichier(s) encore en cours d’analyse : la synthèse se mettra à jour toute seule.</p>}
      {!hasControl && <p className="text-sm bg-yellow/20 px-3 py-2 rounded-sm">Aucun site témoin : sans lui, impossible de distinguer l’effet du festival d’un changement de météo ou de saison. Ajoute un site « témoin » hors de la zone du festival.</p>}

      {/* Tuiles par type de site : une ligne « festival », une ligne « témoin » (côte à côte sur grand écran, lg:grid-cols-2) */}
      <div className="grid gap-4 lg:grid-cols-2">
        {hasImpact && <PhaseRow title="Sites du festival" kind="impact" data={by_type.impact}
          help="Activité moyenne (contacts par heure d'enregistrement) de tous les sites situés dans la zone du festival, phase par phase." />}
        {hasControl && <PhaseRow title="Site(s) témoin" kind="control" data={by_type.control}
          help="Même calcul pour le ou les sites témoins, hors de la zone du festival. S'ils varient autant que les sites du festival, la variation vient sans doute d'autre chose (météo, saison)." />}
      </div>

      <p className="text-xs text-slate-light max-w-3xl">
        Ces chiffres sont descriptifs : ils ne constituent pas un test statistique. Pour conclure à un impact, il faut plusieurs
        nuits par phase et une analyse statistique (comparaison festival / témoin, avant / pendant).
      </p>

      {/* Les deux graphiques recharts.
          Notions recharts :
           - ResponsiveContainer : prend la taille de son parent. Le parent doit donc avoir une
             hauteur fixée (ici h-56), sinon le graphique aurait une hauteur nulle ;
           - BarChart : le graphique en barres ; `data` = le tableau préparé plus haut ;
           - CartesianGrid : le quadrillage (vertical={false} : lignes horizontales seulement) ;
           - XAxis dataKey="phase" : la propriété lue pour les étiquettes de l'axe horizontal ;
           - Tooltip : l'infobulle au survol ; Legend : la légende sous le graphique ;
           - Bar dataKey=… : une série de barres, lue dans la propriété du même nom. */}
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="card p-4">
          <h3 className="font-bold flex items-center gap-2 mb-2">
            Activité : contacts par heure
            <Help text="Un contact = une tranche de 5 secondes contenant au moins un cri (score ≥ 0,3). On divise le nombre de contacts par la durée des fichiers enregistrés. Attention : ce calcul n'est juste que si l'enregistreur tourne en continu sur la plage horaire choisie. Un impact se lit quand les barres « festival » bougent et pas les barres « témoin »." />
          </h3>
          {/* Une barre festival (vert) et une barre témoin (jaune) par phase.
              formatter : texte de l'infobulle ; une valeur null (aucune durée enregistrée) s'affiche « pas de données ».
              radius : coins arrondis en haut des barres. */}
          <div className="h-56">
            <ResponsiveContainer>
              <BarChart data={activity} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid stroke={C.grid} vertical={false} />
                <XAxis dataKey="phase" tick={{ fill: C.axis, fontSize: 12 }} stroke={C.axisSoft} />
                <YAxis tick={{ fill: C.axisSoft, fontSize: 11 }} stroke={C.axisSoft} width={40} />
                <Tooltip {...tooltip} formatter={(v, name) => [v == null ? 'pas de données' : `${v} contacts/h`, name]} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                {hasImpact && <Bar dataKey="festival" name="Festival" fill="#5aa876" radius={[3, 3, 0, 0]} />}
                {hasControl && <Bar dataKey="temoin" name="Témoin" fill="#fbcf38" radius={[3, 3, 0, 0]} />}
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="card p-4">
          <h3 className="font-bold flex items-center gap-2 mb-2">
            Cris par groupe (tous sites)
            <Help text="Nombre de cris (score ≥ 0,3) attribués à chaque groupe d'espèces, tous sites confondus. Le groupe vient de l'espèce proposée par un modèle entraîné au Royaume-Uni : c'est une indication à faire confirmer par un spécialiste, pas une identification." />
          </h3>
          {/* Barres empilées : toutes les séries qui partagent le même stackId ("a") sont posées
              les unes sur les autres. Une série <Bar> par groupe d'espèces, avec sa couleur. */}
          <div className="h-56">
            <ResponsiveContainer>
              <BarChart data={diversity} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid stroke={C.grid} vertical={false} />
                <XAxis dataKey="phase" tick={{ fill: C.axis, fontSize: 12 }} stroke={C.axisSoft} />
                <YAxis tick={{ fill: C.axisSoft, fontSize: 11 }} stroke={C.axisSoft} width={40} />
                <Tooltip {...tooltip} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                {groups.map((g) => <Bar key={g} dataKey={g} stackId="a" fill={colorOf(g)} />)}
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Détail par site. Le même contenu existe en deux versions :
          des cartes pour téléphone (sm:hidden = cachées à partir de 640 px) et un tableau pour
          écran plus large (hidden sm:block = caché sur téléphone). Un tableau à 4 colonnes serait
          illisible sur un petit écran. */}
      {/* Téléphone : une carte par site, les 3 phases côte à côte */}
      {/* { site, phases: ph } : déstructuration avec renommage (la propriété phases devient la variable ph).
          Dans chaque case : contacts par heure (« – » si aucune donnée), nombre de fichiers et de groupes.
          <>…</> est un « fragment » : il regroupe plusieurs éléments sans ajouter de balise HTML. */}
      <div className="sm:hidden grid gap-3">
        {sites.map(({ site, phases: ph }) => (
          <div key={site.id} className="card p-3">
            <div className="font-medium mb-2">
              <span className={`inline-block w-2 h-2 rounded-full mr-2 ${site.is_control ? 'bg-yellow' : 'bg-green'}`} />
              {site.name}{site.is_control ? <span className="text-slate-light"> · témoin</span> : null}
            </div>
            <div className="grid grid-cols-3 gap-2 text-center">
              {PHASES.map((p) => {
                const s = ph[p.key]
                return (
                  <div key={p.key} className="bg-page rounded-sm py-1.5">
                    <div className="text-[11px] uppercase tracking-wide text-slate-light">{p.label}</div>
                    <div className="tabular-nums">{s.contacts_per_hour != null ? <><b>{s.contacts_per_hour}</b> <span className="text-xs">c/h</span></> : <span className="text-slate-light">–</span>}</div>
                    <div className="text-[11px] text-slate-light">{s.n_recordings} fich. · {s.n_groups} grp</div>
                  </div>
                )
              })}
            </div>
          </div>
        ))}
      </div>

      {/* Ordinateur / tablette : un tableau, une ligne par site, une colonne par phase.
          overflow-x-auto : si le tableau est trop large, il défile horizontalement dans sa carte. */}
      <div className="card overflow-x-auto hidden sm:block">
        <table className="w-full text-sm">
          <thead>
            <tr>
              <th className="th">Site</th>
              {PHASES.map((p) => <th key={p.key} className="th text-right">{p.label}</th>)}
            </tr>
          </thead>
          <tbody>
            {sites.map(({ site, phases: ph }) => (
              <tr key={site.id}>
                <td className="td font-medium">
                  <span className={`inline-block w-2 h-2 rounded-full mr-2 ${site.is_control ? 'bg-yellow' : 'bg-green'}`} />
                  {site.name}{site.is_control ? <span className="text-slate-light"> · témoin</span> : null}
                </td>
                {PHASES.map((p) => {
                  const s = ph[p.key]
                  return (
                    <td key={p.key} className="td text-right">
                      {s.contacts_per_hour != null ? <><b>{s.contacts_per_hour}</b> c/h</> : <span className="text-slate-light">–</span>}
                      <div className="text-xs text-slate-light">{s.n_recordings} fich. · {s.n_groups} grp</div>
                    </td>
                  )
                })}
              </tr>
            ))}
            {/* colSpan={4} : la cellule « Aucun site » s'étale sur les 4 colonnes (Site + 3 phases) */}
            {sites.length === 0 && <tr><td className="td text-slate-light" colSpan={4}>Aucun site.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// Affiche une durée exprimée en heures (nombre à virgule) dans l'unité la plus parlante :
// secondes sous une minute, minutes sous une heure, sinon heures avec une décimale.
// `!h` couvre 0, null et undefined.
function fmtHours(h) {
  if (!h) return '0 s'
  if (h < 1 / 60) return `${Math.round(h * 3600)} s`
  if (h < 1) return `${Math.round(h * 60)} min`
  return `${h.toFixed(1)} h`
}

// Une ligne de 3 tuiles (avant / pendant / après) pour un type de site, avec la variation par rapport à « avant »
//
// Props : title (titre), kind ('impact' ou 'control', pour la couleur du liseré du haut),
// data (by_type.impact ou by_type.control), help (texte de la bulle « ? »).
//
// La variation `delta` (en %) compare chaque phase à « avant » : (valeur / référence − 1) × 100.
// Elle n'est calculée que pour pendant et après, et seulement si les deux valeurs existent
// (et que la référence n'est pas 0, pour ne pas diviser par zéro). Baisse en orange, sinon en vert.
// `v ?? '–'` : affiche v, ou un tiret si v est null ou undefined.
function PhaseRow({ title, kind, data, help }) {
  const ref = data.avant.contacts_per_hour
  return (
    <div className={`card p-3 sm:p-4 border-t-4 ${kind === 'control' ? 'border-t-yellow' : 'border-t-green'}`}>
      <h3 className="font-bold flex items-center gap-2 mb-2">{title} <Help text={help} /></h3>
      <div className="grid grid-cols-3 gap-2">
        {PHASES.map((p) => {
          const s = data[p.key]
          const v = s.contacts_per_hour
          const delta = p.key !== 'avant' && v != null && ref ? Math.round((v / ref - 1) * 100) : null
          return (
            <div key={p.key} className="bg-page rounded-sm p-2 min-w-0">
              <div className="text-[11px] uppercase tracking-wide text-slate-light">{p.label}</div>
              <div className="text-xl sm:text-2xl font-bold tabular-nums leading-tight">{v ?? '–'}</div>
              <div className="text-[11px] text-slate-light">contacts/h</div>
              {delta != null && <div className={`text-xs font-medium tabular-nums ${delta < 0 ? 'text-orange-600 dark:text-orange-400' : 'text-green-dark'}`}>{delta > 0 ? '+' : ''}{delta} % vs avant</div>}
              <div className="text-[11px] text-slate-light mt-0.5">{s.n_recordings} fich. · {fmtHours(s.hours)} · {s.n_groups} grp</div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
