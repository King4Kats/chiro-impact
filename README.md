# Chiro Impact

Outil de l'association **Lagom Natura** pour mesurer l'effet d'un festival sur l'activité des chauves-souris.
On dépose les enregistrements ultrasons (WAV) faits **avant, pendant et après** le festival, sur des sites du
festival et sur un **site témoin**. L'outil détecte les cris avec [BatDetect2](https://github.com/macaodha/batdetect2),
puis calcule l'**activité** (contacts par heure) et les **groupes d'espèces** présents.

> ⚠️ Ce que l'outil ne fait pas : compter des individus, identifier les espèces françaises de façon fiable,
> ou prouver statistiquement un impact. Lire la page « Comment ça marche » de l'application (limites et sources).

---

## 1. Installer (une seule fois, sur Windows)

1. Installer **Python 3.11 ou plus récent** : <https://www.python.org/downloads/>
   → pendant l'installation, cocher **« Add python.exe to PATH »**.
2. Installer **Node.js 20 ou plus récent** (version « LTS ») : <https://nodejs.org>
3. Double-cliquer sur **`install.bat`**. Compter 5 à 15 minutes (téléchargement de PyTorch, ~200 Mo).

## 2. Lancer

Double-cliquer sur **`start.bat`**. Le navigateur s'ouvre sur <http://localhost:8000>.
Pour arrêter : fermer la fenêtre noire.

## 3. Utiliser

1. **Créer une campagne** (un festival, une édition), avec les **nuits du festival** (première et dernière nuit).
2. **Ajouter les sites** : un par emplacement d'enregistreur, dont au moins un **témoin** (hors zone du festival).
3. **Déposer les WAV** de la carte SD : choisir le site, puis la phase (**Auto** la déduit de la date du fichier).
   - Enregistreur AudioMoth réglé à **250 ou 384 kHz**, en **continu ou sur un horaire fixe**.
   - Les fichiers en mode déclenché (`…T.WAV`) sont refusés : les « déplier » d'abord avec l'application AudioMoth
     (Fichier → Expand).
   - Un fichier déjà déposé sur le même site est ignoré : on peut redéposer toute la carte SD.
4. Attendre l'analyse (environ 8 fois plus rapide que la durée d'enregistrement sur un PC récent).
5. Onglet **Synthèse** : activité des sites du festival et du témoin, phase par phase. Cliquer sur un fichier pour
   voir son spectrogramme, écouter les cris ralentis et vérifier les détections.

## 4. Pour les développeurs

```
backend/   FastAPI + BatDetect2 (Python)     app/ : main.py (API), detection.py, analysis.py, metadata.py,
                                              spectro.py, worker.py (file d'analyse), db.py (SQLite)
frontend/  React + Vite + Tailwind           src/pages, src/components
deploy/    docker-compose pour un serveur avec Traefik
docs/      maquette, WAV de démonstration, AUDIT.md (relecture complète du projet)
SUIVI_PROJET.md   journal des décisions
```

- Tests : `cd backend` puis `.venv\Scripts\python -m pip install -r requirements-dev.txt` et
  `.venv\Scripts\python -m pytest` (44 tests, ~1 min 15, avec de vrais cris de chauves-souris).
- Démo pour travailler l'interface : serveur lancé, puis `.venv\Scripts\python scripts\creer_demo.py`.
- Développement de l'interface avec rechargement automatique : `cd frontend` puis `npm run dev`
  (http://localhost:5173, l'API doit tourner sur le port 8000).
- Docker : `docker build -t chiro-impact .` ; sur un serveur avec Traefik, voir `deploy/docker-compose.yml`.
- Réglages (variables d'environnement) : `CHIRO_DATA_DIR`, `CHIRO_THREADS`, `CHIRO_TZ` (défaut Europe/Paris),
  `CHIRO_MIN_SAMPLERATE` (défaut 96 000).

## 5. Licences et citation

- **BatDetect2** (code et modèle) : licence **CC BY-NC 4.0**, usage **non commercial** uniquement.
  Si l'étude est rémunérée (par exemple par l'organisateur du festival), demander l'accord des auteurs.
  À citer : Mac Aodha O. et al. (2022), *Towards a general approach for bat echolocation detection and
  classification*, bioRxiv, doi:10.1101/2022.12.14.520490.
- Le code propre à Chiro Impact : licence à choisir par l'association avant publication.
