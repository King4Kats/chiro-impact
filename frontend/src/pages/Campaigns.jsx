/*
 * ============================================================================
 * Campaigns.jsx — la page d'accueil (adresse « / »)
 * ============================================================================
 *
 * RÔLE DE LA PAGE
 *   Afficher la liste de toutes les campagnes (une campagne = un festival + une
 *   édition) et proposer, à droite, un formulaire pour en créer une nouvelle.
 *   Chaque campagne de la liste a un lien pour l'ouvrir et un bouton pour la
 *   supprimer (avec une confirmation en deux clics).
 *
 * DONNÉES DEMANDÉES À L'API (voir frontend/src/api.js)
 *   - api.campaigns()          → GET    /api/campaigns        : la liste des campagnes
 *   - api.createCampaign(data) → POST   /api/campaigns        : crée une campagne
 *   - api.deleteCampaign(id)   → DELETE /api/campaigns/{id}   : supprime une campagne
 *
 * SOMMAIRE DES COMPOSANTS DU FICHIER
 *   - Campaigns   : la page entière (liste + formulaire). C'est l'export par défaut.
 *   - CampaignRow : une ligne de la liste (nom, description, compteurs, boutons).
 *
 * NOTIONS DE BASE (expliquées une fois ici, valables pour tout le fichier)
 *   - Un « composant » React est une fonction qui renvoie ce qu'il faut afficher.
 *     Son nom commence par une majuscule (Campaigns, CampaignRow…).
 *   - Ce qui ressemble à du HTML dans le code (<div>, <h2>…) s'appelle du JSX.
 *     Ce n'est pas du vrai HTML : l'outil de compilation (Vite) le transforme en
 *     appels JavaScript. D'où quelques différences : on écrit `className` au lieu
 *     de `class`, `htmlFor` au lieu de `for`, et on insère une valeur JavaScript
 *     entre accolades : {maVariable}.
 *   - Les classes comme "grid gap-6 text-xl font-bold" viennent de Tailwind CSS :
 *     chaque classe applique UN petit style (gap-6 = espace entre les éléments,
 *     text-xl = texte plus grand, font-bold = gras…). Un préfixe comme `md:` veut
 *     dire « seulement à partir d'une largeur d'écran moyenne (768 px) » ; `dark:`
 *     veut dire « seulement en thème sombre ». Les classes `card`, `btn`, `input`,
 *     `label` sont des raccourcis maison définis dans src/index.css.
 */

// --- Imports ---
// useState et useEffect sont deux « hooks » de React (fonctions spéciales qui
// commencent par `use` et qu'on appelle en haut d'un composant). Ils sont
// expliqués plus bas, au moment où on s'en sert.
import { useEffect, useState } from 'react'
// Link : un lien interne de react-router. Il change de page SANS recharger tout
// le site (contrairement à une balise <a> classique) : c'est plus rapide.
import { Link } from 'react-router-dom'
// `api` regroupe toutes les requêtes vers le serveur (fichier src/api.js).
import { api } from '../api'
// Help : le petit « ? » vert qui affiche une bulle d'explication au survol ou au toucher.
import Help from '../components/Help'

// Page d'accueil : liste des campagnes + formulaire de création.
// `export default` : c'est ce composant que les autres fichiers récupèrent quand
// ils écrivent `import Campaigns from './pages/Campaigns'` (voir App.jsx).
export default function Campaigns() {
  // --- L'état de la page ---
  // useState crée une « variable d'état » : une valeur dont React se souvient
  // entre deux affichages. Il renvoie un tableau de deux éléments, qu'on
  // récupère avec la « déstructuration » `const [valeur, setValeur] = ...` :
  //   - `list` : la valeur actuelle ;
  //   - `setList` : la fonction pour la changer.
  // Quand on appelle setList(...), React redessine le composant avec la
  // nouvelle valeur : c'est ce qu'on appelle un « re-rendu ».
  // La valeur entre parenthèses est la valeur de départ.
  const [list, setList] = useState([])     // les campagnes reçues du serveur (vide au départ)
  // Les 4 champs du formulaire de création. Chaque champ <input> affiche la
  // valeur de son état et la met à jour à chaque frappe (« champ contrôlé »).
  const [name, setName] = useState('')
  const [desc, setDesc] = useState('')
  const [start, setStart] = useState('')   // première nuit du festival, au format 'AAAA-MM-JJ'
  const [end, setEnd] = useState('')       // dernière nuit du festival
  const [error, setError] = useState('')   // message d'erreur à afficher ('' = pas d'erreur)

  // --- Chargement de la liste ---
  // `load` demande la liste au serveur. api.campaigns() renvoie une « promesse » :
  // un objet qui représente une réponse qui arrivera plus tard (le réseau prend
  // du temps). `.then(setList)` = « quand la réponse arrive, range-la dans list ».
  // `.catch(...)` = « si ça échoue, affiche le message d'erreur ».
  // `(e) => setError(e.message)` est une « fonction fléchée » : une façon courte
  // d'écrire une petite fonction anonyme.
  const load = () => api.campaigns().then(setList).catch((e) => setError(e.message))
  // useEffect exécute du code APRÈS l'affichage du composant.
  // Le second argument `[]` est le « tableau de dépendances » : React relance
  // l'effet seulement quand une de ces valeurs change. Tableau vide = l'effet ne
  // tourne qu'une seule fois, à l'arrivée sur la page. C'est le bon endroit pour
  // charger des données au démarrage.
  useEffect(() => { load() }, [])

  // --- Création d'une campagne (envoi du formulaire) ---
  // `async` permet d'utiliser `await` dans la fonction : `await` met la fonction
  // en pause jusqu'à ce que la promesse soit résolue, ce qui se lit plus
  // facilement qu'une chaîne de .then(). Les erreurs se rattrapent alors avec
  // un bloc try / catch classique.
  async function create(e) {
    // Par défaut, envoyer un <form> recharge toute la page. On l'empêche :
    // c'est notre code qui envoie les données au serveur.
    e.preventDefault()
    // Pas de nom (ou seulement des espaces) : on ne fait rien.
    if (!name.trim()) return
    try {
      // .trim() retire les espaces au début et à la fin.
      // `start || null` : si la date est vide (''), on envoie null (« pas de date »)
      // au lieu d'une chaîne vide, que le serveur ne saurait pas lire comme une date.
      await api.createCampaign({ name: name.trim(), description: desc.trim(), festival_start: start || null, festival_end: end || null })
      // Succès : on vide le formulaire, on efface l'erreur éventuelle et on
      // recharge la liste pour y voir la nouvelle campagne.
      setName(''); setDesc(''); setStart(''); setEnd(''); setError(''); load()
    } catch (e) { setError(e.message) }
  }

  // --- Suppression d'une campagne ---
  // Appelée par CampaignRow après le 2e clic (le bouton « Confirmer la suppression »).
  async function remove(c) {
    // Pas de confirm() natif : on demande deux clics (voir bouton)
    await api.deleteCampaign(c.id); load()
  }

  // --- Ce que la page affiche ---
  // Tout ce qui suit `return` est du JSX : la description de l'écran.
  return (
    // Grille : une seule colonne sur téléphone ; à partir de `md:` (768 px),
    // deux colonnes : la liste prend la place restante (1fr) et le formulaire
    // a une largeur fixe de 340 px.
    <div className="grid gap-6 md:grid-cols-[1fr_340px]">
      {/* Colonne de gauche : la liste des campagnes.
          (Dans le JSX, entre deux balises, un commentaire s'écrit entre accolades comme celui-ci.) */}
      <section>
        <h2 className="text-xl font-bold mb-3 flex items-center gap-2">
          Campagnes
          {/* `text="..."` est une « prop » : un paramètre qu'on passe à un composant,
              comme un attribut HTML. Help le reçoit et l'affiche dans sa bulle. */}
          <Help text="Une campagne = un festival + une édition (ex. « Dub Camp 2027 »). Elle regroupe les sites d'enregistrement et tous les fichiers audio des phases avant, pendant et après." />
        </h2>
        {/* Rendu conditionnel avec && : si `error` est vide (''), rien n'est affiché ;
            sinon le paragraphe rouge s'affiche. `A && B` vaut B seulement si A est « vrai ». */}
        {error && <p className="text-red-600 dark:text-red-400 text-sm mb-2">{error}</p>}
        {/* Liste vide : un message d'accueil qui guide vers le formulaire. */}
        {list.length === 0 && (
          <div className="card p-6 text-slate-light">
            Aucune campagne pour l'instant. Crée la première avec le formulaire à droite.
          </div>
        )}
        <div className="grid gap-3">
          {/* .map() transforme chaque campagne du tableau en un élément <CampaignRow>.
              La prop spéciale `key` donne à React un identifiant unique par ligne :
              il s'en sert pour savoir quelle ligne a changé, été ajoutée ou retirée,
              sans tout redessiner. On utilise l'id de la base, qui est unique.
              `onDelete` reçoit une fonction : la ligne l'appellera pour se faire supprimer. */}
          {list.map((c) => (
            <CampaignRow key={c.id} c={c} onDelete={() => remove(c)} />
          ))}
        </div>
      </section>

      {/* Colonne de droite : le formulaire de création.
          onSubmit={create} : quand on valide le formulaire (bouton « Créer » ou
          touche Entrée), React appelle la fonction create définie plus haut. */}
      <aside>
        <form onSubmit={create} className="card p-4 grid gap-3">
          <h3 className="font-bold">Nouvelle campagne</h3>
          {/* Champ « Nom ». htmlFor="c-name" relie l'étiquette au champ id="c-name" :
              cliquer sur l'étiquette place le curseur dans le champ (et c'est lu
              correctement par les lecteurs d'écran).
              value + onChange = champ « contrôlé » : React affiche toujours la valeur
              de l'état `name`, et chaque frappe la met à jour via setName.
              e.target.value = le texte actuellement dans le champ. */}
          <div>
            <label className="label" htmlFor="c-name">Nom</label>
            <input id="c-name" className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="Dub Camp 2027" />
          </div>
          {/* Champ « Description » : même principe, sur plusieurs lignes (textarea). */}
          <div>
            <label className="label" htmlFor="c-desc">Description (optionnel)</label>
            <textarea id="c-desc" className="input" rows={3} value={desc} onChange={(e) => setDesc(e.target.value)} placeholder="Lieu, dates, matériel utilisé…" />
          </div>
          {/* Dates du festival : deux sélecteurs de date côte à côte (grid-cols-2).
              Elles servent au serveur à classer automatiquement les fichiers en
              avant / pendant / après. Comme il y a deux champs pour une seule
              étiquette visible, chaque champ a son propre aria-label (nom lu par
              les lecteurs d'écran). */}
          <div>
            <span className="label flex items-center gap-1.5">
              Nuits du festival (optionnel)
              <Help text="Première et dernière nuit du festival. Elles permettent de classer automatiquement les fichiers en avant / pendant / après d'après leur date. Modifiables plus tard." />
            </span>
            <div className="grid grid-cols-2 gap-2">
              <input type="date" className="input px-2" aria-label="Première nuit" value={start} onChange={(e) => setStart(e.target.value)} />
              {/* min={start || undefined} : le calendrier de la dernière nuit
                  n'accepte pas une date avant la première nuit. Si `start` est vide,
                  on passe `undefined`, ce qui veut dire « pas d'attribut min du tout ». */}
              <input type="date" className="input px-2" aria-label="Dernière nuit" value={end} min={start || undefined} onChange={(e) => setEnd(e.target.value)} />
            </div>
          </div>
          {/* type="submit" : ce bouton déclenche l'envoi du formulaire (donc onSubmit). */}
          <button className="btn btn-green justify-center" type="submit">Créer</button>
        </form>
      </aside>
    </div>
  )
}

// --- Une ligne de la liste ---
// Les props arrivent dans un objet ; `{ c, onDelete }` les déstructure, c'est-à-dire
// qu'on récupère directement props.c et props.onDelete dans deux variables.
//   - c        : la campagne à afficher (objet reçu du serveur) ;
//   - onDelete : la fonction à appeler pour la supprimer.
function CampaignRow({ c, onDelete }) {
  // Suppression en deux clics : `confirm` passe à true au 1er clic, et le bouton
  // devient rouge « Confirmer la suppression ». Chaque ligne a son propre état,
  // donc confirmer une ligne n'affecte pas les autres.
  const [confirm, setConfirm] = useState(false)
  return (
    // flex-wrap : sur un écran étroit, les boutons passent à la ligne au lieu de déborder.
    <div className="card p-4 flex flex-wrap items-center gap-3">
      {/* Bloc texte : flex-1 lui donne toute la place restante ; min-w-0 l'autorise
          à rétrécir, ce qui permet à `truncate` de couper la description avec « … ». */}
      <div className="flex-1 min-w-0">
        {/* Le lien vers la page de la campagne. Les accolades + backticks forment
            un « template literal » : une chaîne où ${...} insère une valeur.
            Ici, pour la campagne 7, on obtient "/campaigns/7". */}
        <Link to={`/campaigns/${c.id}`} className="font-bold text-lg hover:text-green-dark">{c.name}</Link>
        {/* La description n'est affichée que si elle existe. */}
        {c.description && <p className="text-sm text-slate-light truncate">{c.description}</p>}
        {/* Compteurs calculés par le serveur.
            `c.created_at?.slice(0, 10)` : le `?.` (« chaînage optionnel ») évite une
            erreur si created_at est absent (on obtient alors undefined, qui n'affiche rien).
            slice(0, 10) garde les 10 premiers caractères de la date ISO, soit 'AAAA-MM-JJ'. */}
        <p className="text-xs text-slate-light mt-1">{c.n_sites} site(s) · {c.n_recordings} enregistrement(s) · créée le {c.created_at?.slice(0, 10)}</p>
      </div>
      <Link to={`/campaigns/${c.id}`} className="btn">Ouvrir</Link>
      {/* Opérateur ternaire `condition ? A : B` : affiche A si la condition est vraie, sinon B.
          - 1er état (confirm = false) : bouton discret « Supprimer » ; le cliquer passe confirm à true.
          - 2e état (confirm = true) : bouton rouge ; le cliquer appelle onDelete.
          onBlur = « le bouton perd le focus » (on clique ailleurs, on tabule plus loin) :
          on annule alors la confirmation, pour ne pas laisser un bouton rouge armé. */}
      {confirm ? (
        <button className="btn bg-red-600 hover:bg-red-700" onClick={onDelete} onBlur={() => setConfirm(false)}>Confirmer la suppression</button>
      ) : (
        <button className="btn btn-ghost" onClick={() => setConfirm(true)}>Supprimer</button>
      )}
    </div>
  )
}
