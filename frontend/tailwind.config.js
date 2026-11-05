/*
 * tailwind.config.js — réglages de Tailwind CSS (couleurs, police, arrondis, thème sombre).
 *
 * Tailwind fabrique les classes utilitaires (bg-surface, text-slate…) à partir de ce fichier.
 * Travaille avec : src/index.css (variables de couleur des thèmes), postcss.config.js (qui lance
 * Tailwind pendant le build de Vite), src/theme.js (qui pose la classe `dark` sur <html>).
 */
/**
 * Charte Lagom Natura : Rubik, ardoise #44405A, vert #80C595, jaune #FBCF38.
 * Les couleurs qui changent entre thème clair et sombre sont des variables CSS (voir src/index.css) :
 * on garde les mêmes noms de classes partout (text-slate, bg-surface…), seul le thème change leur valeur.
 */
// Petite fonction qui fabrique une couleur Tailwind à partir d'une variable CSS.
// v('ink') donne : rgb(var(--c-ink) / <alpha-value>)
// <alpha-value> est un emplacement que Tailwind remplace par l'opacité demandée :
// bg-slate → opacité 1, bg-slate/50 → opacité 0.5. C'est pour ça que index.css stocke
// les couleurs en « R G B » sans rgb() autour.
const v = (name) => `rgb(var(--c-${name}) / <alpha-value>)`

export default {
  // Fichiers dans lesquels Tailwind cherche les noms de classes utilisés.
  // Une classe qui n'apparaît dans aucun de ces fichiers n'est pas générée (CSS final plus léger).
  content: ['./index.html', './src/**/*.{js,jsx}'],
  // 'class' : les variantes dark:… (ex. dark:text-red-400) s'appliquent quand un parent porte
  // la classe `dark`, et non selon le réglage du système. C'est theme.js qui décide.
  darkMode: 'class', // thème sombre quand <html class="dark">
  theme: {
    // `extend` AJOUTE nos valeurs à celles de Tailwind au lieu de les remplacer.
    // Attention : slate, green et yellow existent déjà dans Tailwind ; ici on redéfinit leurs
    // teintes par défaut et quelques nuances (light, dark, soft) aux couleurs de la charte.
    extend: {
      fontFamily: { sans: ['Rubik', 'Arial', 'Helvetica', 'sans-serif'] },
      colors: {
        // DEFAULT = la couleur obtenue sans suffixe (text-slate) ; light = text-slate-light, etc.
        slate: { DEFAULT: v('ink'), light: v('ink-soft') }, // couleur du texte
        green: { DEFAULT: '#80c595', dark: '#5aa876', soft: v('green-soft') },
        yellow: { DEFAULT: '#fbcf38' },
        brand: v('brand'),     // fond des boutons principaux et des bulles d'aide
        surface: v('surface'), // fond des cartes, champs, en-tête
        line: v('line'),
        page: v('page'),
      },
      // Arrondis : `rounded` = 6 px, `rounded-sm` = 2 px.
      borderRadius: { DEFAULT: '6px', sm: '2px' },
    },
  },
  plugins: [],
}
