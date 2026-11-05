import { useEffect, useState } from 'react'

// Thème de l'interface : « auto » (suit le réglage de l'ordinateur ou du téléphone), « clair » ou « sombre ».
// Le choix est gardé dans le navigateur. index.html applique déjà le bon thème avant l'affichage
// (sinon la page clignoterait en blanc au chargement).
const KEY = 'chiro-theme'
const CHOICES = ['auto', 'clair', 'sombre']
const media = window.matchMedia('(prefers-color-scheme: dark)')

export function getChoice() {
  try {
    const v = localStorage.getItem(KEY)
    return CHOICES.includes(v) ? v : 'auto'
  } catch {
    return 'auto' // navigation privée : pas de stockage, on suit le système
  }
}

const resolve = (choice) => (choice === 'sombre' || (choice === 'auto' && media.matches) ? 'dark' : 'light')

function apply(choice) {
  document.documentElement.classList.toggle('dark', resolve(choice) === 'dark')
  window.dispatchEvent(new Event('chiro-theme'))
}

export function setChoice(choice) {
  try { localStorage.setItem(KEY, choice) } catch { /* ignoré */ }
  apply(choice)
}

// Si l'utilisateur change le thème de son système pendant que la page est ouverte
media.addEventListener('change', () => { if (getChoice() === 'auto') apply('auto') })

// Hook React : renvoie { choice, theme } et se met à jour quand le thème change.
// theme = 'light' ou 'dark' (le thème réellement affiché).
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

export const THEME_CHOICES = CHOICES
