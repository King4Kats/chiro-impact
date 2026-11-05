// Toutes les requêtes vers le backend passent par ici.
// Un seul endroit à modifier si l'API change.

const BASE = '/api'

// Petite fonction générique : envoie la requête, lève une erreur lisible si ça échoue, renvoie le JSON
async function request(path, options = {}) {
  const res = await fetch(BASE + path, options)
  if (!res.ok) {
    let msg = res.statusText
    try { msg = (await res.json()).detail || msg } catch {}
    throw new Error(msg)
  }
  if (res.status === 204) return null
  return res.json()
}

const json = (method, body) => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

export const api = {
  health: () => request('/health'),
  groups: () => request('/groups'),

  // Campagnes
  campaigns: () => request('/campaigns'),
  campaign: (id) => request(`/campaigns/${id}`),
  createCampaign: (data) => request('/campaigns', json('POST', data)),
  // Modifier une campagne (nom, description, dates du festival). Renvoie aussi `reclassified`.
  updateCampaign: (id, data) => request(`/campaigns/${id}`, json('PATCH', data)),
  deleteCampaign: (id) => request(`/campaigns/${id}`, { method: 'DELETE' }),

  // Sites
  createSite: (cid, data) => request(`/campaigns/${cid}/sites`, json('POST', data)),
  updateSite: (id, data) => request(`/sites/${id}`, json('PATCH', data)),
  deleteSite: (id) => request(`/sites/${id}`, { method: 'DELETE' }),

  // Enregistrements
  recordings: (cid) => request(`/campaigns/${cid}/recordings`),
  recording: (id) => request(`/recordings/${id}`),
  deleteRecording: (id) => request(`/recordings/${id}`, { method: 'DELETE' }),
  reprocess: (id) => request(`/recordings/${id}/reprocess`, { method: 'POST' }),
  // Corriger la phase ('avant' | 'pendant' | 'apres' | 'auto') ou le site d'un fichier
  updateRecording: (id, data) => request(`/recordings/${id}`, json('PATCH', data)),
  // L'upload envoie un formulaire multipart (pas du JSON) : fichiers + site + phase.
  // Réponse : { created: [...], skipped: [{ filename, reason }] }
  upload: (cid, siteId, phase, files) => {
    const fd = new FormData()
    fd.append('site_id', siteId)
    fd.append('phase', phase)
    for (const f of files) fd.append('files', f)
    return request(`/campaigns/${cid}/recordings`, { method: 'POST', body: fd })
  },
  // minProb : seuls les cris au-dessus de ce seuil sont entourés ; hl : id du cri surligné en jaune
  // size : { w, h, dpr } = taille d'affichage (pixels CSS) et densité de l'écran → image nette partout
  spectrogramUrl: (id, t0 = 0, t1, minProb = 0, hl, size, theme = 'light') =>
    `${BASE}/recordings/${id}/spectrogram.png?t0=${t0}${t1 != null ? `&t1=${t1}` : ''}&min_prob=${minProb}` +
    `${hl != null ? `&hl=${hl}` : ''}${size ? `&w=${size.w}&h=${size.h}&dpr=${size.dpr}` : ''}${theme === 'dark' ? '&theme=dark' : ''}`,
  // Extrait sonore ralenti (×10) : les ultrasons deviennent audibles
  audioUrl: (id, t0, t1, slow = 10) => `${BASE}/recordings/${id}/audio.wav?t0=${t0}&t1=${t1}&slow=${slow}`,

  // Synthèse
  summary: (cid) => request(`/campaigns/${cid}/summary`),
}

// Libellés affichés pour les phases (la base stocke les clés sans accent)
export const PHASES = [
  { key: 'avant', label: 'Avant' },
  { key: 'pendant', label: 'Pendant' },
  { key: 'apres', label: 'Après' },
]
export const phaseLabel = (k) => PHASES.find((p) => p.key === k)?.label || k
