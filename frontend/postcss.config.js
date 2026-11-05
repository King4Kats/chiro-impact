/*
 * postcss.config.js — chaîne de traitement du CSS.
 *
 * Vite fait passer chaque fichier CSS (src/index.css) dans PostCSS, qui applique ces outils dans l'ordre :
 *  - tailwindcss : remplace les @tailwind / @apply par le vrai CSS (réglages : tailwind.config.js) ;
 *  - autoprefixer : ajoute si besoin les préfixes propres à certains navigateurs (-webkit-…).
 * Les accolades vides {} veulent dire « options par défaut ».
 */
export default { plugins: { tailwindcss: {}, autoprefixer: {} } }
