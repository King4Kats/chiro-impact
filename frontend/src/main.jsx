/*
 * main.jsx — point de départ de l'interface.
 *
 * C'est le fichier que index.html charge (<script type="module" src="/src/main.jsx">).
 * Il démarre React, branche le routeur (gestion des adresses /, /doc…) et charge les styles.
 *
 * Travaille avec : index.html (la <div id="root">), App.jsx (le plan des pages), index.css (styles).
 *
 * Note : le fichier finit en .jsx car il contient du JSX, cette syntaxe qui ressemble à du HTML
 * (<App />) au milieu du JavaScript. Vite la traduit en appels de fonctions JavaScript normaux.
 */
// Point d'entrée : React s'accroche à la <div id="root"> de index.html
import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
// Importer un .css depuis du JavaScript est une facilité de Vite : la feuille de style est ajoutée à la page.
import './index.css'

// createRoot(élément).render(…) : React prend le contrôle de la <div id="root"> et y dessine l'appli.
// - React.StrictMode : mode « vérifications en plus » pendant le développement (il lance certains
//   effets deux fois pour repérer les oublis de nettoyage). Il n'a aucun effet dans la version construite.
// - BrowserRouter : fournit à toute l'appli la notion d'adresse courante (react-router).
//   Grâce à lui, <Routes>, <Link> et useParams() fonctionnent dans les autres fichiers.
//   Changer de page ne recharge pas le site : React redessine seulement ce qui change.
ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
)
