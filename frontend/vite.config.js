/*
 * vite.config.js — réglages de Vite, l'outil qui fait tourner et construit l'interface.
 *
 * Vite a deux usages :
 *  - `npm run dev` : un serveur de développement (http://localhost:5173) qui recharge la page
 *    à chaque modification d'un fichier ;
 *  - `npm run build` : « construit » l'appli, c'est-à-dire traduit le JSX, assemble et compresse
 *    tous les fichiers dans le dossier frontend/dist/, prêt à être servi.
 *
 * Travaille avec : package.json (scripts dev / build), index.html (point d'entrée),
 * backend/app/main.py (qui sert dist/ en production), install.bat et Dockerfile (qui lancent le build).
 */
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// En développement (npm run dev), tout ce qui commence par /api est renvoyé au backend FastAPI (port 8000).
// En production (npm run build), le backend sert lui-même le dossier dist/ : pas besoin de proxy.
//
// Le « proxy » : la page est servie par Vite (port 5173) mais l'API est sur le port 8000.
// Plutôt que d'appeler un autre port depuis le navigateur, on laisse Vite relayer les requêtes /api.
// Ainsi api.js peut toujours utiliser l'adresse relative '/api', en dev comme en production.
// Le plugin react() permet à Vite de comprendre le JSX et de rafraîchir les composants à chaud.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { '/api': 'http://localhost:8000' } },
})
