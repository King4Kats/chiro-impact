/*
 * FestivalDates.jsx — petit formulaire « Dates du festival » d'une campagne.
 *
 * L'utilisateur saisit la première et la dernière nuit du festival. Le serveur s'en sert pour
 * ranger automatiquement chaque fichier en avant / pendant / après (phase « Auto »), et
 * reclasse les fichiers déjà déposés quand les dates changent.
 *
 * Travaille avec :
 *  - pages/Campaign.jsx : l'affiche et lui passe la campagne + une fonction onChange ;
 *  - api.js : updateCampaign() envoie les dates au serveur ;
 *  - Help.jsx : la bulle « ? » d'explication ;
 *  - UploadZone.jsx : le bouton « Auto » n'est actif que si ces dates existent.
 */
import { useEffect, useState } from 'react'
import { api } from '../api'
import Help from './Help'

// Dates du festival d'une campagne : première et dernière NUIT.
// Elles servent à classer automatiquement les fichiers en avant / pendant / après.
//
// Les « props » sont les paramètres d'un composant, passés comme des attributs :
// <FestivalDates campaign={c} onChange={reload} />. Ici :
//  - campaign : l'objet campagne reçu du serveur ;
//  - onChange : fonction à appeler après l'enregistrement, pour que la page parente recharge ses données.
export default function FestivalDates({ campaign, onChange }) {
  // Copie locale des deux dates pendant la saisie (format AAAA-MM-JJ des champs date, '' si vide),
  // et un message affiché sous le formulaire.
  const [start, setStart] = useState(campaign.festival_start || '')
  const [end, setEnd] = useState(campaign.festival_end || '')
  const [msg, setMsg] = useState('')
  // useState ne lit sa valeur de départ qu'une fois. Si la campagne est rechargée avec d'autres
  // dates, cet effet recopie les nouvelles valeurs dans les champs. Le tableau de dépendances
  // [festival_start, festival_end] veut dire : relancer l'effet seulement quand l'une d'elles change.
  useEffect(() => { setStart(campaign.festival_start || ''); setEnd(campaign.festival_end || '') }, [campaign.festival_start, campaign.festival_end])

  // « dirty » (sale) : vrai si la saisie diffère de ce qui est enregistré.
  // Sert à n'afficher le bouton Enregistrer que lorsqu'il y a quelque chose à enregistrer.
  const dirty = start !== (campaign.festival_start || '') || end !== (campaign.festival_end || '')

  // Envoi du formulaire.
  // e.preventDefault() empêche le comportement par défaut d'un <form> (recharger toute la page).
  // Un champ vide est envoyé comme null pour effacer la date côté serveur.
  // La réponse contient `reclassified` : le nombre de fichiers qui ont changé de phase.
  async function save(e) {
    e.preventDefault()
    setMsg('')
    try {
      const r = await api.updateCampaign(campaign.id, { festival_start: start || null, festival_end: end || null })
      setMsg(r.reclassified ? `${r.reclassified} fichier(s) reclassé(s).` : 'Dates enregistrées.')
      onChange()
    } catch (err) { setMsg('Erreur : ' + err.message) }
  }

  // Affichage. Les champs sont « contrôlés » : leur valeur vient de l'état (value={start}) et
  // chaque frappe met l'état à jour (onChange). React reste ainsi la seule source de vérité.
  // htmlFor (le `for` du HTML) relie l'étiquette à son champ : cliquer sur le texte sélectionne le champ.
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
          {/* min : le calendrier interdit une dernière nuit avant la première */}
          <label className="label" htmlFor="fd-end">Dernière nuit</label>
          <input id="fd-end" type="date" className="input px-2" value={end} min={start || undefined} onChange={(e) => setEnd(e.target.value)} />
        </div>
      </div>
      {/* `condition && <élément>` : affichage conditionnel, l'élément n'apparaît que si la condition est vraie */}
      {dirty && <button className="btn btn-ghost justify-center" type="submit">Enregistrer les dates</button>}
      {msg && <p className="text-xs text-slate-light">{msg}</p>}
    </form>
  )
}
