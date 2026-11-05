/*
 * Sites.jsx — liste et gestion des sites d'enregistrement d'une campagne.
 *
 * Un site = un emplacement où un enregistreur est posé. Chaque site est soit « festival »
 * (pastille verte), soit « témoin » hors de la zone du festival (pastille jaune).
 * Ce composant permet d'en ajouter et d'en retirer.
 *
 * Travaille avec :
 *  - pages/Campaign.jsx : l'affiche et lui passe la campagne (avec campaign.sites) + onChange ;
 *  - api.js : createSite() et deleteSite() ;
 *  - Help.jsx : la bulle « ? » d'explication ;
 *  - UploadZone.jsx et Summary.jsx : utilisent ces mêmes sites.
 */
import { useState } from 'react'
import { api } from '../api'
import Help from './Help'

// Gestion des sites d'enregistrement d'une campagne (ajout / suppression, drapeau témoin)
export default function Sites({ campaign, onChange }) {
  // État du petit formulaire d'ajout : nom tapé, case « témoin » cochée ou non, message d'erreur.
  const [name, setName] = useState('')
  const [control, setControl] = useState(false)
  const [error, setError] = useState('')

  // Ajout d'un site. trim() enlève les espaces au début et à la fin : un nom vide ou fait
  // seulement d'espaces est refusé sans rien envoyer. Après succès, on vide le formulaire et
  // on prévient la page parente (onChange) pour qu'elle recharge la campagne avec le nouveau site.
  async function add(e) {
    e.preventDefault()
    if (!name.trim()) return
    try {
      await api.createSite(campaign.id, { name: name.trim(), is_control: control })
      setName(''); setControl(false); onChange()
    } catch (e) { setError(e.message) }
  }

  return (
    <div className="card p-4 grid gap-3">
      <h3 className="font-bold flex items-center gap-2">
        Sites d’enregistrement
        <Help text="Un site = un emplacement précis où un enregistreur est posé (ex. « Lisière nord », « Scène principale »). Le même site doit être utilisé avant, pendant et après. Coche « témoin » pour un site hors de la zone du festival : il sert de référence pour séparer l'effet du festival de l'effet météo." />
      </h3>
      {/* Liste des sites existants : pastille de couleur, nom, mention « témoin », lien « retirer ».
          key={s.id} : identifiant unique exigé par React pour chaque élément d'une liste. */}
      <ul className="grid gap-2">
        {campaign.sites.map((s) => (
          <li key={s.id} className="flex items-center gap-2 text-sm">
            <span className={`w-2 h-2 rounded-full ${s.is_control ? 'bg-yellow' : 'bg-green'}`} />
            <span className="flex-1">{s.name}{s.is_control ? <span className="text-slate-light"> · témoin</span> : null}</span>
            <RemoveSite site={s} onDone={onChange} />
          </li>
        ))}
        {campaign.sites.length === 0 && <li className="text-sm text-slate-light">Aucun site.</li>}
      </ul>
      {/* Formulaire d'ajout. La case à cocher est « contrôlée » : checked vient de l'état,
          et e.target.checked (vrai/faux) le met à jour. accent-green-dark colore la coche. */}
      <form onSubmit={add} className="grid gap-2">
        <input className="input" placeholder="Nom du site" value={name} onChange={(e) => setName(e.target.value)} aria-label="Nom du site" />
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={control} onChange={(e) => setControl(e.target.checked)} className="accent-green-dark" />
          Site témoin (hors festival)
        </label>
        <button className="btn btn-ghost justify-center" type="submit">Ajouter le site</button>
        {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}
      </form>
    </div>
  )
}

// Retirer un site efface AUSSI tous ses enregistrements (fichiers WAV compris) : on demande confirmation.
// Fonctionnement en deux temps, sans fenêtre pop-up : un premier clic sur « retirer » remplace
// le lien par la question « oui / non » (état confirm). « oui » appelle le serveur puis onDone
// (rechargement) ; « non » revient au lien de départ.
// .then(onDone) : quand la promesse de suppression est tenue, on appelle onDone.
function RemoveSite({ site, onDone }) {
  const [confirm, setConfirm] = useState(false)
  if (!confirm) return <button className="text-xs text-slate-light hover:text-red-600 py-1" onClick={() => setConfirm(true)}>retirer</button>
  return (
    <span className="text-xs inline-flex items-center gap-2">
      <span className="text-red-700 dark:text-red-300">Effacer le site et ses fichiers ?</span>
      <button className="text-red-600 dark:text-red-400 font-medium py-1" onClick={() => api.deleteSite(site.id).then(onDone)}>oui</button>
      <button className="text-slate-light py-1" onClick={() => setConfirm(false)}>non</button>
    </span>
  )
}
