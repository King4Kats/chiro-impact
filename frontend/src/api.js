/*
 * api.js — le « téléphone » entre l'interface et le serveur.
 *
 * Rôle : toutes les requêtes vers le backend (FastAPI, dossier backend/app/) passent par ici.
 * Les pages (src/pages/*.jsx) et les composants (src/components/*.jsx) n'appellent jamais
 * fetch() directement : ils font api.campaigns(), api.upload(…), etc.
 * Avantage : si une adresse de l'API change, on ne modifie qu'un seul fichier.
 *
 * Travaille avec :
 *  - backend/app/main.py : définit les adresses /api/… qu'on appelle ici ;
 *  - vite.config.js : en développement, renvoie /api vers le serveur Python (port 8000) ;
 *  - PHASES / phaseLabel (en bas) : utilisés par UploadZone, Summary, Campaign, Recording.
 */

// Toutes les adresses de l'API commencent par /api. Comme c'est une adresse « relative »
// (sans http://machine:port), le navigateur l'envoie au même serveur que celui qui a servi la page.
const BASE = '/api'

// Petite fonction générique : envoie la requête, lève une erreur lisible si ça échoue, renvoie le JSON
//
// Notions pour débuter :
//  - fetch(url, options) : fonction du navigateur qui envoie une requête HTTP. Elle ne renvoie pas
//    la réponse tout de suite, mais une « promesse » (Promise) : un objet qui contiendra la réponse
//    plus tard, quand le serveur aura répondu.
//  - async / await : `async` devant la fonction permet d'écrire `await` à l'intérieur.
//    `await promesse` met la fonction en pause jusqu'à ce que la promesse soit tenue, sans bloquer
//    le reste de la page. Une fonction async renvoie elle-même toujours une promesse.
//  - options = {} : valeur par défaut si on n'en passe pas (requête GET simple).
async function request(path, options = {}) {
  const res = await fetch(BASE + path, options)
  // res.ok vaut false si le serveur répond avec un code d'erreur (400, 404, 500…).
  // fetch ne lève PAS d'erreur dans ce cas : c'est à nous de vérifier.
  if (!res.ok) {
    // Message par défaut : le texte du code HTTP (ex. « Not Found »).
    // FastAPI renvoie souvent un JSON { "detail": "explication" } : on le préfère s'il existe.
    // Le try/catch vide évite de planter si la réponse d'erreur n'est pas du JSON.
    let msg = res.statusText
    try { msg = (await res.json()).detail || msg } catch {}
    // `throw` fait échouer la promesse : l'appelant le récupère dans son propre try/catch
    // (voir par exemple save() dans FestivalDates.jsx).
    throw new Error(msg)
  }
  // 204 = « No Content » : le serveur a réussi mais n'a rien à renvoyer (ex. après une suppression).
  // Appeler res.json() sur une réponse vide planterait, donc on renvoie null.
  if (res.status === 204) return null
  // res.json() lit le corps de la réponse et le transforme en objet JavaScript (c'est aussi une promesse).
  return res.json()
}

// Raccourci pour fabriquer les options d'une requête qui envoie du JSON (POST, PATCH…).
// - headers Content-Type : prévient le serveur que le corps est du JSON ;
// - JSON.stringify : transforme l'objet JavaScript en texte JSON, seul format qui voyage sur le réseau.
const json = (method, body) => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

// L'objet `api` regroupe une fonction par action possible. Chacune renvoie une promesse :
// on l'utilise avec `await api.campaigns()` ou `api.campaigns().then(...)`.
// Les adresses avec ${…} sont des « gabarits » (template strings, entre accents graves `) :
// la valeur de la variable est insérée dans le texte.
export const api = {
  // health : le serveur répond-il ? groups : liste des groupes d'espèces connus.
  health: () => request('/health'),
  groups: () => request('/groups'),

  // Campagnes
  // GET = lire, POST = créer, PATCH = modifier une partie, DELETE = supprimer.
  campaigns: () => request('/campaigns'),
  campaign: (id) => request(`/campaigns/${id}`),
  createCampaign: (data) => request('/campaigns', json('POST', data)),
  // Modifier une campagne (nom, description, dates du festival). Renvoie aussi `reclassified`.
  updateCampaign: (id, data) => request(`/campaigns/${id}`, json('PATCH', data)),
  deleteCampaign: (id) => request(`/campaigns/${id}`, { method: 'DELETE' }),

  // Sites
  // cid = id de la campagne à laquelle le site appartient.
  createSite: (cid, data) => request(`/campaigns/${cid}/sites`, json('POST', data)),
  updateSite: (id, data) => request(`/sites/${id}`, json('PATCH', data)),
  deleteSite: (id) => request(`/sites/${id}`, { method: 'DELETE' }),

  // Enregistrements
  // reprocess : demande au serveur de relancer l'analyse BatDetect2 d'un fichier.
  recordings: (cid) => request(`/campaigns/${cid}/recordings`),
  recording: (id) => request(`/recordings/${id}`),
  deleteRecording: (id) => request(`/recordings/${id}`, { method: 'DELETE' }),
  reprocess: (id) => request(`/recordings/${id}/reprocess`, { method: 'POST' }),
  // Corriger la phase ('avant' | 'pendant' | 'apres' | 'auto') ou le site d'un fichier
  updateRecording: (id, data) => request(`/recordings/${id}`, json('PATCH', data)),
  // L'upload envoie un formulaire multipart (pas du JSON) : fichiers + site + phase.
  // Réponse : { created: [...], skipped: [{ filename, reason }] }
  //
  // FormData : objet du navigateur qui imite un formulaire HTML. On y ajoute des champs avec
  // append(nom, valeur). Une valeur peut être un fichier (objet File) : c'est la façon standard
  // d'envoyer des fichiers. Ici, pas de header Content-Type : le navigateur l'écrit lui-même
  // (« multipart/form-data » + une « frontière » qui sépare les champs).
  // On peut appeler append plusieurs fois avec le même nom ('files') : le serveur reçoit une liste.
  upload: (cid, siteId, phase, files) => {
    const fd = new FormData()
    fd.append('site_id', siteId)
    fd.append('phase', phase)
    for (const f of files) fd.append('files', f)
    return request(`/campaigns/${cid}/recordings`, { method: 'POST', body: fd })
  },
  // Les deux fonctions suivantes ne font PAS de requête : elles fabriquent seulement une adresse.
  // Cette adresse est ensuite mise dans <img src=…> ou <audio src=…> ; c'est le navigateur qui
  // télécharge l'image ou le son. Les paramètres après « ? » (t0=…&t1=…) sont lus par le serveur.
  //
  // spectrogramUrl : image PNG du spectrogramme entre t0 et t1 secondes.
  // minProb : seuls les cris au-dessus de ce seuil sont entourés ; hl : id du cri surligné en jaune
  // size : { w, h, dpr } = taille d'affichage (pixels CSS) et densité de l'écran → image nette partout
  // theme : 'dark' demande au serveur une image aux couleurs du thème sombre.
  // Les morceaux `${cond ? '…' : ''}` n'ajoutent un paramètre que s'il est fourni.
  spectrogramUrl: (id, t0 = 0, t1, minProb = 0, hl, size, theme = 'light') =>
    `${BASE}/recordings/${id}/spectrogram.png?t0=${t0}${t1 != null ? `&t1=${t1}` : ''}&min_prob=${minProb}` +
    `${hl != null ? `&hl=${hl}` : ''}${size ? `&w=${size.w}&h=${size.h}&dpr=${size.dpr}` : ''}${theme === 'dark' ? '&theme=dark' : ''}`,
  // Extrait sonore ralenti (×10) : les ultrasons deviennent audibles
  audioUrl: (id, t0, t1, slow = 10) => `${BASE}/recordings/${id}/audio.wav?t0=${t0}&t1=${t1}&slow=${slow}`,

  // Synthèse
  // Chiffres agrégés de la campagne (par phase, par site, par groupe), affichés par Summary.jsx.
  summary: (cid) => request(`/campaigns/${cid}/summary`),
  // Page « Comparer » : une ligne par site × nuit, recalculée avec les réglages choisis.
  // URLSearchParams fabrique la fin d'adresse « ?threshold=0.3&window=5… » en échappant les valeurs.
  compare: (cid, p) => {
    const q = new URLSearchParams({ threshold: p.threshold, window: p.window })
    if (p.hours) { q.set('h_start', p.hours[0]); q.set('h_end', p.hours[1]) }
    return request(`/campaigns/${cid}/compare?${q}`)
  },
}

// Libellés affichés pour les phases (la base stocke les clés sans accent)
// L'ordre du tableau = l'ordre d'affichage (colonnes, barres des graphiques, boutons).
export const PHASES = [
  { key: 'avant', label: 'Avant' },
  { key: 'pendant', label: 'Pendant' },
  { key: 'apres', label: 'Après' },
]
// Retrouve le libellé d'une clé ('apres' → 'Après'). Si la clé est inconnue, on affiche la clé telle quelle.
// `?.` (chaînage optionnel) : si find() ne trouve rien (undefined), on n'essaie pas de lire .label.
export const phaseLabel = (k) => PHASES.find((p) => p.key === k)?.label || k
