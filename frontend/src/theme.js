/*
 * theme.js — gestion du thème clair / sombre de l'interface.
 *
 * Principe : le thème sombre est activé en ajoutant la classe `dark` sur la balise <html>.
 * Les couleurs elles-mêmes sont des variables CSS définies dans src/index.css (une série pour
 * :root, une autre pour :root.dark). tailwind.config.js (darkMode: 'class') fait le lien.
 *
 * Travaille avec :
 *  - index.html : un petit script y applique le thème AVANT que React démarre (même clé 'chiro-theme') ;
 *  - components/Layout.jsx : le sélecteur Auto / Clair / Sombre appelle setChoice() ;
 *  - components/Summary.jsx et pages/Recording.jsx : lisent le thème avec useTheme() pour
 *    colorer les graphiques et demander des spectrogrammes sombres.
 */
import { useEffect, useState } from 'react'

// Thème de l'interface : « auto » (suit le réglage de l'ordinateur ou du téléphone), « clair » ou « sombre ».
// Le choix est gardé dans le navigateur. index.html applique déjà le bon thème avant l'affichage
// (sinon la page clignoterait en blanc au chargement).
//
// - KEY : nom sous lequel le choix est rangé dans le localStorage (voir getChoice).
// - matchMedia('(prefers-color-scheme: dark)') : demande au navigateur si le système
//   (Windows, Android…) est réglé en mode sombre. `media.matches` vaut true ou false,
//   et l'objet prévient quand ce réglage change (voir plus bas).
const KEY = 'chiro-theme'
const CHOICES = ['auto', 'clair', 'sombre']
const media = window.matchMedia('(prefers-color-scheme: dark)')

// Lit le choix enregistré.
// localStorage : petit espace de stockage du navigateur, propre à chaque site, qui survit à la
// fermeture de l'onglet. On y range du texte avec setItem(clé, valeur) et on le relit avec getItem(clé).
// Si la valeur lue n'est pas un des trois choix connus (rien d'enregistré, valeur abîmée…), on prend 'auto'.
export function getChoice() {
  try {
    const v = localStorage.getItem(KEY)
    return CHOICES.includes(v) ? v : 'auto'
  } catch {
    return 'auto' // navigation privée : pas de stockage, on suit le système
  }
}

// Traduit un choix (auto / clair / sombre) en thème réellement affiché ('dark' ou 'light').
// En 'auto', c'est le réglage du système qui décide.
const resolve = (choice) => (choice === 'sombre' || (choice === 'auto' && media.matches) ? 'dark' : 'light')

// Applique un choix à la page :
// 1. classList.toggle('dark', vrai/faux) ajoute ou retire la classe `dark` sur <html> ;
//    toutes les couleurs basculent d'un coup grâce aux variables CSS.
// 2. dispatchEvent envoie un « événement personnalisé » nommé 'chiro-theme' : un signal maison,
//    comme un 'click', que n'importe quel code peut écouter avec addEventListener('chiro-theme', …).
//    C'est ainsi que useTheme() (plus bas) apprend que le thème a changé.
function apply(choice) {
  document.documentElement.classList.toggle('dark', resolve(choice) === 'dark')
  window.dispatchEvent(new Event('chiro-theme'))
}

// Appelé quand l'utilisateur clique sur Auto / Clair / Sombre : on mémorise puis on applique.
// Si l'enregistrement échoue (navigation privée), le thème change quand même pour cette visite.
export function setChoice(choice) {
  try { localStorage.setItem(KEY, choice) } catch { /* ignoré */ }
  apply(choice)
}

// Si l'utilisateur change le thème de son système pendant que la page est ouverte
// (ex. Windows passe en sombre le soir). On ne réagit qu'en mode 'auto' : un choix forcé reste forcé.
media.addEventListener('change', () => { if (getChoice() === 'auto') apply('auto') })

// Hook React : renvoie { choice, theme } et se met à jour quand le thème change.
// theme = 'light' ou 'dark' (le thème réellement affiché).
//
// Notions pour débuter :
//  - Un « hook » est une fonction dont le nom commence par `use` et qui utilise d'autres hooks
//    React. On l'appelle en haut d'un composant : const { theme } = useTheme().
//  - useState(valeurDeDépart) : une mémoire propre au composant. Il renvoie [valeur, fonctionPourChanger].
//    Appeler la fonction (setState) redessine le composant avec la nouvelle valeur.
//    Ici on passe la fonction `read` (sans parenthèses) : React l'appelle une seule fois au départ.
//  - useEffect(fonction, dépendances) : code lancé APRÈS l'affichage, pour se brancher sur le
//    monde extérieur (événements, minuteries, réseau…). Le tableau [] vide veut dire « une seule
//    fois, à l'arrivée du composant ». La fonction renvoyée (return () => …) est le « nettoyage » :
//    React l'appelle quand le composant disparaît, pour ne pas laisser d'écouteur orphelin.
export function useTheme() {
  const read = () => ({ choice: getChoice(), theme: document.documentElement.classList.contains('dark') ? 'dark' : 'light' })
  const [state, setState] = useState(read)
  useEffect(() => {
    const update = () => setState(read())
    window.addEventListener('chiro-theme', update)
    return () => window.removeEventListener('chiro-theme', update)
  }, [])
  return state
}

// Liste des choix exportée pour construire les boutons du sélecteur (Layout.jsx).
export const THEME_CHOICES = CHOICES
