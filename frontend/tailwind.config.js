/**
 * Charte Lagom Natura : Rubik, ardoise #44405A, vert #80C595, jaune #FBCF38.
 * Les couleurs qui changent entre thème clair et sombre sont des variables CSS (voir src/index.css) :
 * on garde les mêmes noms de classes partout (text-slate, bg-surface…), seul le thème change leur valeur.
 */
const v = (name) => `rgb(var(--c-${name}) / <alpha-value>)`

export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  darkMode: 'class', // thème sombre quand <html class="dark">
  theme: {
    extend: {
      fontFamily: { sans: ['Rubik', 'Arial', 'Helvetica', 'sans-serif'] },
      colors: {
        slate: { DEFAULT: v('ink'), light: v('ink-soft') }, // couleur du texte
        green: { DEFAULT: '#80c595', dark: '#5aa876', soft: v('green-soft') },
        yellow: { DEFAULT: '#fbcf38' },
        brand: v('brand'),     // fond des boutons principaux et des bulles d'aide
        surface: v('surface'), // fond des cartes, champs, en-tête
        line: v('line'),
        page: v('page'),
      },
      borderRadius: { DEFAULT: '6px', sm: '2px' },
    },
  },
  plugins: [],
}
