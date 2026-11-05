/*
 * UploadZone.jsx — dépôt des fichiers WAV d'une campagne.
 *
 * L'utilisateur choisit le site où l'enregistreur était posé et la phase (Auto / Avant /
 * Pendant / Après), puis glisse ses fichiers dans la zone en pointillés (ou clique pour les
 * choisir). Les fichiers sont envoyés au serveur, qui lance l'analyse BatDetect2 en arrière-plan.
 *
 * Travaille avec :
 *  - pages/Campaign.jsx : l'affiche dans sa colonne latérale et lui passe campaign + onUploaded ;
 *  - api.js : api.upload() (envoi en FormData) et PHASES ;
 *  - FestivalDates.jsx : sans dates du festival, la phase « Auto » est désactivée ;
 *  - Help.jsx : les bulles « ? ».
 */
import { useRef, useState } from 'react'
import { api, PHASES } from '../api'
import Help from './Help'

// Zone de dépôt des WAV : on choisit le site et la phase, puis on glisse les fichiers (ou on clique).
// Phase « Auto » : déduite de la date dans le nom du fichier et des dates du festival de la campagne.
export default function UploadZone({ campaign, onUploaded }) {
  // hasDates : les deux dates du festival sont-elles renseignées ? (Boolean(...) force un vrai/faux)
  const hasDates = Boolean(campaign.festival_start && campaign.festival_end)
  // État du composant :
  //  - siteId : site choisi (le premier de la liste par défaut, '' s'il n'y en a aucun) ;
  //  - phase  : 'auto' par défaut si les dates existent, sinon 'avant' ;
  //  - busy   : un envoi est en cours (la zone est alors bloquée) ;
  //  - msg    : texte de progression puis de bilan ;
  //  - skipped: fichiers refusés par le serveur ou impossibles à envoyer, avec la raison ;
  //  - drag   : un fichier est en train d'être survolé au-dessus de la zone (pour la colorer).
  const [siteId, setSiteId] = useState(campaign.sites[0]?.id || '')
  const [phase, setPhase] = useState(hasDates ? 'auto' : 'avant')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')
  const [skipped, setSkipped] = useState([])
  const [drag, setDrag] = useState(false)
  // Référence vers le <input type="file"> caché : on le « clique » par programme quand
  // l'utilisateur clique sur la zone en pointillés.
  const inputRef = useRef()

  // Les fichiers partent UN PAR UN : une carte SD entière en un seul envoi serait coupée par le
  // serveur (délai d'attente) et une seule erreur ferait tout échouer.
  //
  // Déroulé :
  //  1. [...fileList] transforme la FileList du navigateur (qui n'est pas un vrai tableau) en tableau ;
  //  2. vérifications : au moins un fichier, un site choisi ;
  //  3. boucle : chaque fichier est envoyé seul ; `await` attend la réponse avant de passer au suivant.
  //     On compte les fichiers créés et on accumule les refus (ceux du serveur, et nos propres
  //     erreurs réseau, mises au même format { filename, reason }) ;
  //  4. tous les 5 fichiers, onUploaded() demande à la page de recharger la liste, pour voir
  //     l'avancement sans attendre la fin. `?.()` n'appelle la fonction que si elle a été fournie ;
  //  5. à la fin : message de bilan, liste des refus, dernier rechargement, et on vide le champ
  //     fichier (sinon re-choisir les mêmes fichiers ne déclencherait pas onChange).
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

  // noSite : sans site, impossible de déposer (liste vide, zone grisée).
  // phaseBtn : petite fonction qui fabrique un bouton de phase. Le bouton de la phase choisie
  // est plein (vert) ; disabled sert à griser « Auto » quand il n'y a pas de dates.
  // type="button" : sans lui, un <button> dans un formulaire enverrait le formulaire.
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
        {/* Choix du site : liste déroulante « contrôlée » (value + onChange) */}
        <div>
          <label className="label" htmlFor="up-site">Site</label>
          <select id="up-site" className="input" value={siteId} onChange={(e) => setSiteId(e.target.value)} disabled={noSite}>
            {campaign.sites.map((s) => <option key={s.id} value={s.id}>{s.name}{s.is_control ? ' (témoin)' : ''}</option>)}
          </select>
        </div>
        {/* Choix de la phase : « Auto » puis un bouton par phase de PHASES (Avant, Pendant, Après) */}
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
      {/* Zone de glisser-déposer (drag & drop).
          Le navigateur envoie plusieurs événements quand on fait glisser un fichier :
           - dragover : le fichier survole la zone. Par défaut le navigateur refuse le dépôt ;
             e.preventDefault() dit « ici, on accepte ». On colore aussi la zone (drag = true) ;
           - dragleave : le fichier quitte la zone → on retire la couleur ;
           - drop : le fichier est lâché. preventDefault() empêche le navigateur d'ouvrir le
             fichier dans l'onglet ; e.dataTransfer.files contient les fichiers lâchés.
          Un clic sur la zone ouvre la fenêtre de choix de fichiers, via l'<input> caché.
          Rien ne se passe pendant un envoi (busy) ou s'il n'y a pas de site. */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDrag(true) }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); if (!busy && !noSite) send(e.dataTransfer.files) }}
        onClick={() => !busy && !noSite && inputRef.current.click()}
        className={`border-2 border-dashed rounded p-6 text-center cursor-pointer transition ${drag ? 'border-green bg-green-soft' : 'border-line hover:border-green'} ${busy || noSite ? 'opacity-60 cursor-not-allowed' : ''}`}
      >
        <p className="font-medium">Glisse tes fichiers .wav ici</p>
        <p className="text-sm text-slate-light">ou clique pour les choisir · plusieurs fichiers à la fois possible</p>
        {/* Champ fichier caché (hidden). accept filtre la fenêtre de choix sur les .wav,
            multiple autorise plusieurs fichiers, e.target.files contient la sélection. */}
        <input ref={inputRef} type="file" accept=".wav,.WAV" multiple hidden onChange={(e) => send(e.target.files)} />
      </div>
      {msg && <p className="text-sm text-slate-light">{msg}</p>}
      {/* Fichiers ignorés : on en montre 8 au plus (slice(0, 8)) pour ne pas noyer l'écran,
          puis le nombre restant. break-all coupe les noms de fichiers très longs. */}
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
