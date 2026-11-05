# Suivi projet — Identification acoustique des chiroptères (#projet-chiroptères)

> Fichier de suivi : chaque modification / décision est ajoutée à la suite, avec la date.
> Sert de contexte pour une nouvelle conversation et de fil de réflexion.

---

## 2026-11-05 — Démarrage, cadrage à partir de la conv Discord

### Équipe (Discord)
King4Kats (Flavien), kwildfire, theo, Dr. Baleine, Shwimy, L0üTre.

### Idée du projet
Reconnaître automatiquement les espèces de chauves-souris à partir d'enregistrements ultrasons (son → spectrogramme → modèle de deep learning), adapté aux espèces de l'ouest de la France.

### Outils / ressources identifiés
| Outil | Quoi | Point clé |
|---|---|---|
| **BatDetect2** (Python, open source) | Détecte les cris + propose une espèce, CNN | Entraîné sur 17 espèces UK → ne couvre pas toute la France. Permet de ré-entraîner sur d'autres données. BD utilisée : ChiroSetEurope. |
| **BSG-BATS** (Zenodo, PyTorch) | Classificateur CNN, WAV → probabilités par espèce | Entraîné sur 21 espèces européennes. |
| **Tadarida / TadariDeep** (Yves Bas, MNHN) | Chaîne française : Tadarida-D (détection, C++), -L (annotation, GUI), -C (classif random forest, R), TadariDeep (deep learning, Python) | C'est l'outil de Vigie-Chiro. Code public. |
| **Vigie-Chiro** | Programme participatif MNHN | Observations (espèce/lieu/date) libres sur OpenObs / GBIF, **mais sons bruts non téléchargeables**. |
| **ChiroSetEurope** (GitHub anlebai) | Manifest de métadonnées de sons européens | Annotation souvent « fichier = espèce », pas cri par cri. |

### Problème central
Il manque des **données audio françaises annotées finement** (début/fin/fréquence de chaque cri) pour entraîner/adapter un modèle. La « matière première » est fermée, l'« usine » (code) est ouverte.

### Pistes
1. Vérifier à quel point les espèces UK ≠ ouest France (si peu de différence → BatDetect2 tel quel peut suffire en 1re étape).
2. Utiliser Tadarida-L (ou autre) pour annoter nous-mêmes des sons récupérés auprès d'assos.
3. Utiliser le modèle comme **assistant de tri**, puis vérifier à la main un échantillon (les articles ci-dessous confirment que c'est indispensable).

### Biblio partagée par Dr. Baleine (résumé 1re page)
- **Rydell et al. 2017** (Ecological Indicators) — « A request for prudence » : test SonoChiro, Kaleidoscope, BatClassify. 100 % pour séparer pluie/chauve-souris, 68-100 % pour le **groupe**, mais espèces difficiles mal identifiées (Myotis 4-93 %, Plecotus 0-89 %, V. murinus 16-26 %). → Toujours valider les sorties automatiques.
- **Brabant et al. 2018** (Belgian J. Zoology) — 4 logiciels sur 9 espèces d'Europe de l'Ouest : BatIdent 77 %, Kaleidoscope 71 %, SonoChiro 65 %, BatExplorer 31 %. Un expert doit relire.
- **Jay 2018** (Plume de naturalistes) — Efficacité de SonoChiro (logiciel payant Biotope) en vergers (Gard) ; indice de confiance 0 (fort) → 10 (faible) par séquence.
- **Barataud 2021** — Écoute active vs passive : les enregistreurs auto ratent ~65 % des contacts ; 75 % de l'activité et 93 % de la diversité dans les 4 premières heures de nuit. (Barataud = co-auteur ChiroSetEurope, basé en Creuse.)

### Prochaines étapes (à valider)
- [ ] Définir l'objectif concret v1 (ex. pipeline : WAV → BatDetect2 → export CSV + spectrogrammes à vérifier).
- [ ] Choisir techno (Python 3.11 + batdetect2 probable).
- [ ] Trouver quelques WAV de test (assos, ChiroSetEurope).
- [ ] Comparer liste espèces UK (modèle BatDetect2) vs liste France (L0üTre).

---

## 2026-11-05 — Recadrage par Flavien : le vrai besoin

**Contexte** : association qui intervient sur des festivals.
**Objectif** : mesurer l'**impact d'un festival sur l'activité des chauves-souris** en comparant des enregistrements avant / (pendant) / après.
**Niveau de reconnaissance requis** : « chauve-souris ou pas », **pas l'espèce**. (Éventuellement groupe, bonus.)
**Matériel** : emprunt à des assos ou fabrication maison (piste AudioMoth).

### Conséquence
La reconnaissance d'espèces (et donc le manque de données françaises annotées) n'est plus un blocage. La détection seule est un problème résolu par les outils existants (BatDetect2, Tadarida-D). Le projet devient :
1. un **protocole de terrain** rigoureux (c'est lui qui fait la preuve),
2. un **pipeline logiciel** simple : WAV → détection → nombre de contacts / heure → graphiques avant/après.

### Métrique retenue (standard chiroptérologie)
Indice d'activité = nombre de contacts (ou « passages ») par heure, par site, par nuit.
Indice de diversité = nombre de groupes/espèces détectés.
⚠️ L'acoustique ne permet PAS de compter les individus (1 pipistrelle × 50 passages = 50 pipistrelles × 1 passage). Référence : Vigie-Chiro (Kerbiriou et al. 2015) raisonne en contacts.

### Matériel pressenti
AudioMoth (Open Acoustic Devices) : enregistreur open source, ~80-100 €, jusqu'à 384 kHz, piles AA, micro-SD, programmable. Utilisé par Vigie-Nature École.

---

## 2026-11-05 — Décisions techniques (projet logiciel)

- **Objectif logiciel** : interface web locale, propre et pro, pour déposer des WAV, lancer la détection, visualiser contacts/heure + groupes, comparer avant/pendant/après. Partageable aux copains plus tard.
- **Stack** : backend Python **FastAPI** (pilote BatDetect2) + frontend **React / Vite / Tailwind**.
- **Environnement** : Windows, Python + Node déjà installés. Tout tourne en local.
- **Dépôt** : dossier sur le PC de Flavien (via Add folder), git initialisé dedans, push GitHub par Flavien.
- **Données de test** : enregistrements publics en attendant le matériel.

### Test technique réalisé (cloud)
- `pip install batdetect2` (v1.3.1) + `audioread` + `librosa` (dépendances manquantes du paquet, à mettre dans requirements.txt).
- Commande : `batdetect2 detect dossier_wav/ sortie/ 0.3`
- 3 extraits exemple du dépôt BatDetect2 → 44 cris, espèce majoritaire correcte sur les 3 fichiers.
- Sortie = 1 JSON par WAV, 1 objet par cri : start_time, end_time, low_freq, high_freq, class, det_prob, class_prob.

### Maquette web publiée (artefact « Chiro Impact »)
- Onglet Détections : tuiles de synthèse, choix du fichier, spectrogramme avec boîtes de détection, curseur de seuil, tableau (début, fin, durée, fréquences, espèce, probabilités).
- Onglet Doc pipeline : schéma, 6 étapes, lecture du tableau, limites de la méthode, format JSON, architecture prévue.
- Sert de référence visuelle pour le frontend React.

### Maquette v2 — charte graphique Lagom Natura (lagomnatura.fr)
- Relevé sur le site : police **Rubik**, fond blanc, texte ardoise `#44405A`, vert tendre `#80C595` (accent), vert `#6AC8A2`, jaune `#FBCF38`, boutons coins 2 px.
- Spectrogrammes passés en gris sur blanc, boîtes vertes.
- Ajout de boutons « ? » avec infobulle sur chaque élément (tuiles, seuil, spectrogramme, chaque colonne du tableau, chips).
- À réutiliser tel quel comme thème Tailwind du frontend React.

---

## 2026-11-05 — Frontend terminé + premier test réel sur le PC

### Projet rapatrié
Le projet a été construit dans un environnement cloud puis livré en `chiro-impact.zip` ; décompressé dans `Documents\chiro-impact`.

### Frontend (point 1) — fait
- `src/main.jsx` + `src/App.jsx` : routeur avec `Layout`, routes `/`, `/campaigns/:id`, `/recordings/:id`, `/doc`, plus une page 404.
- `src/pages/Recording.jsx` : détail d'un fichier.
  - 4 tuiles (cris, contacts, groupes, durée) recalculées en direct selon le seuil.
  - Spectrogramme par fenêtres de 5 s : boutons ← / →, **frise** de tout le fichier sous l'image (un trait par cri, clic pour s'y déplacer), clic sur une ligne du tableau = fenêtre centrée sur le cri.
  - Curseur de seuil 0,10 → 0,95 (défaut 0,30) ; l'image est redemandée 300 ms après le dernier mouvement.
  - Chips des espèces proposées ; tableau des cris avec un « ? » par colonne (confiance cri en orange sous 0,5).
- `src/pages/Doc.jsx` : reprise de l'onglet « Comment ça marche » de la maquette (schéma de la chaîne en HTML, sans Mermaid ; 6 étapes, lecture du tableau, limites, JSON, architecture).
- Petits ajouts :
  - **Backend** : `GET /api/recordings/{id}/spectrogram.png` accepte `min_prob`, pour que les boîtes vertes suivent le seuil.
  - **`Help`** : option `align="right"`, pour que les bulles des colonnes de droite ne sortent pas de l'écran.
  - **`UploadZone`** : passée sur une seule colonne, car les boutons de phase débordaient de la colonne latérale.

### Test réel (point 2) — fait
- Python 3.12 dans `backend/.venv` : `pip install -r requirements.txt` OK (torch 2.15 CPU).
- `npm run build` OK ; le backend sert bien `frontend/dist` sur http://localhost:8000. Seul avertissement : le bundle JS fait 576 ko, à cause de recharts.
- Campagne test : 2 sites dont 1 témoin, 3 WAV de démo répartis avant / pendant / après.
  - Résultat : 15 / 9 / 20 cris, groupes corrects (Myotis + Pipistrelles, Rhinolophes, Noctules/Sérotines + Pipistrelles), identiques au test cloud. Analyse en ~2 s.
- WAV de 12 s fabriqué (6 × l'extrait EPTSER séparés de 1,5 s de silence) : 112 cris, 3 contacts. Navigation par fenêtres, frise et clic sur cri vérifiés.
- Bug trouvé et corrigé : écran blanc au chargement, dû à un composant utilisé avant sa déclaration dans `Doc.jsx`.
- Remarques :
  - Sur des extraits de 0,5 s, l'activité ressort à 7 200 contacts/h, ce qui est normal (1 contact / 0,5 s). Il faut de vraies nuits pour des chiffres parlants.
  - Pour des fichiers aussi courts, la synthèse affiche une durée de « 0 s » (arrondi de `hours` à 4 décimales). Sans conséquence sur de vraies nuits.

### Reste à faire
- [ ] Point 3 : `install.bat`, `start.bat`, `README.md` pour non-dev.
- [ ] Point 4 : premier commit propre.
- [ ] v2 à discuter : export CSV/PDF, profil horaire, météo par nuit, import carte SD AudioMoth.

## 2026-11-05 (suite) — Décision d'hébergement + backend complet

### Décision : appli web, hébergée sur un serveur personnel, adresse chiro.lagomnatura.fr — mais EN DERNIER
- Serveur choisi : **un serveur personnel** (8 cœurs, 13 Go RAM, 179 Go libres, Traefik + HTTPS déjà en place).
- Adresse : **chiro.lagomnatura.fr**. L'enregistrement DNS n'existe pas encore : il faudra un `A` vers l'IP publique du serveur chez le gestionnaire du domaine.
- Flavien : « pour l'instant du local pour les tests, surtout pour travailler l'interface ; le nom de domaine en dernier ».
- À prévoir au moment de la mise en ligne :
  - un mot de passe d'accès (aujourd'hui, n'importe qui pourrait déposer ou supprimer) ;
  - un Dockerfile (torch en version CPU) ;
  - les labels Traefik sur le réseau `traefik-proxy` ;
  - un sous-réseau fixé en 172.16.x (piège réseau Docker propre à ce serveur) ;
  - les délais de Traefik à vérifier pour les gros dépôts.

### Backend v0.2 (fait, testé)
- **Détection par blocs de 60 s** (`detection.py`).
  - BatDetect2 chargeait tout le fichier en RAM : environ 5,5 Go pour une heure à 384 kHz, impossible pour une nuit entière.
  - On lit maintenant le fichier par blocs, en reproduisant son découpage en tranches de 3 s.
  - Résultat **identique cri pour cri** à `process_file`, vérifié par les tests.
  - Vitesse : environ 8× le temps réel sur le PC (1 h d'audio ≈ 8 min).
  - Nombre de cœurs utilisés réglable avec `CHIRO_THREADS`.
- **File d'analyse** (`worker.py`) : un seul fil de travail, qui reprend au démarrage les analyses interrompues. La progression (0 → 100 %) est enregistrée en base.
- **Phases** :
  - la campagne a des dates de festival : `festival_start` et `festival_end`, première et dernière **nuit**, bornes incluses ;
  - chaque fichier a une `night` (avant midi = nuit de la veille) ;
  - au dépôt, `phase=auto` classe d'après la date dans le nom du fichier (format AudioMoth `AAAAMMJJ_HHMMSS`) ;
  - si on change les dates, les fichiers « auto » sont reclassés tout seuls ; ceux classés à la main ne bougent pas ;
  - `PATCH /api/recordings/{id}` corrige la phase et/ou le site.
- **Dépôt robuste** :
  - les fichiers refusés sont listés avec leur raison, sans bloquer les autres : pas un .wav, déjà déposé sur ce site (on peut redéposer toute une carte SD), WAV illisible, échantillonnage < 96 kHz (`CHIRO_MIN_SAMPLERATE`), fichier vide ;
  - stéréo accepté (1re voie).
- **Spectrogramme** (`spectro.py`) :
  - lecture directe de la fenêtre dans le fichier ;
  - FFT 512 / pas 128 ;
  - regroupement des colonnes en gardant le maximum, pour qu'un cri de 3 ms reste visible ;
  - boîtes vertes (≥ 0,5), orange (à vérifier), jaune (cri sélectionné, paramètre `hl`).
- **Écoute ralentie** : `GET /api/recordings/{id}/audio.wav?t0&t1&slow=10`. Les ultrasons deviennent audibles (45 kHz → 4,5 kHz), 10 s maximum par extrait.
- **Synthèse** : nouveau bloc `nights` (site × nuit), pour voir la variabilité d'une nuit à l'autre.
- **Divers** :
  - `PATCH` sur campagnes et sites ;
  - 410 si le WAV a disparu du disque ;
  - base en WAL, connexions fermées proprement ;
  - colonnes ajoutées automatiquement sur une base existante.

### Tests automatiques — `backend/tests/` (33 tests, ~70 s)
- Lancer : `cd backend` puis `.venv\Scripts\python -m pytest -v` (installer d'abord `requirements-dev.txt`).
- Ils utilisent un dossier de données temporaire : les vraies campagnes ne sont jamais touchées.
- Fichiers testés :
  - les 3 WAV de démo ;
  - des fichiers fabriqués : 12 s, 150 s (plusieurs blocs), stéréo, 44,1 kHz, abîmé.
- Couverture :
  - les calculs (contacts, dates, nuits, phases) ;
  - la détection, identique à BatDetect2 ;
  - tout le parcours API : dépôt manuel et auto, doublons, refus, reclassement, corrections, spectrogramme, audio, synthèse, relance d'analyse, suppressions qui effacent les WAV.

### Campagne de démo pour travailler l'interface
- `backend/scripts/creer_demo.py` (serveur lancé) crée « Démo festival » :
  - 2 sites, dont 1 témoin ;
  - 24 fichiers d'une minute sur 6 nuits, déposés en Auto.
- Résultat : la lisière passe de 720 à **240 contacts/h** pendant le festival, le témoin reste à 720. C'est l'effet qu'on cherche à mettre en évidence.

### Interface : branchements minimaux (la vraie refonte viendra après)
- Dates du festival : à la création d'une campagne, et dans un encadré de la page campagne.
- Dépôt : bouton « Auto », et liste des fichiers ignorés avec leur raison.
- Liste des fichiers : menu pour corriger la phase (ou recalculer en auto), pourcentage d'analyse en cours.
- Page détail : bouton « Écouter ×10 », cri sélectionné surligné en jaune.

### Interface — à travailler ensuite (relevé par Flavien)
- Le plein écran ne marche pas.
- Le responsive (mobile, tablette) n'est pas travaillé.
- Le tableau des enregistrements est trop large et défile horizontalement.
- Revoir les écrans campagnes, etc., étape par étape.

## 2026-11-05 (suite) — Interface : plein écran + responsive

### Spectrogramme « plus comme avant » (remarque de Flavien)
- Le dessin n'avait pas changé : sur le même extrait de 0,5 s, l'ancien rendu et le nouveau sont quasi identiques. Le contraste d'origine (−55 dB) a été rétabli.
- La différence venait du **zoom**. Les extraits de démo d'origine durent 0,5 s : un cri occupait toute la largeur. Les fichiers de la nouvelle démo durent 1 min, vus par fenêtres de 5 s, ce qui écrasait les cris en traits.
- Corrigé :
  - **zoom 0,5 s / 1 s / 2 s / 5 s**, 1 s par défaut ;
  - clic sur un cri = zoom 0,5 s centré sur lui, cri en jaune ;
  - à l'ouverture, la fenêtre se place sur le premier cri si le début du fichier est silencieux.

### Plein écran
- Bouton « Plein écran » (ou touche F) sur le spectrogramme.
- C'est un vrai plein écran du navigateur quand il est disponible ; sinon (iPhone), le bloc couvre toute la page.
- Clavier : ← → fenêtre précédente / suivante, + − zoom, F plein écran, Échap pour quitter.
- Boutons ⏮ ⏭ pour sauter au passage précédent / suivant, en passant les silences (utile sur une nuit entière).

### Image du spectrogramme à la taille de l'écran
- `GET /api/recordings/{id}/spectrogram.png` accepte `w`, `h` (pixels CSS) et `dpr` (densité de l'écran, 1 à 3).
- L'image est dessinée exactement à la taille de son cadre : axes lisibles sur téléphone, image nette en plein écran sur un grand moniteur.
- Taille plafonnée à environ 4,5 millions de pixels, pour garder un rendu rapide. Le test du spectrogramme vérifie aussi ces tailles (33 tests, tous OK).

### Responsive
- **Mise en page** : toute la largeur jusqu'à 1800 px (c'était 1150 px), marges de 16 à 32 px, en-tête compact.
- **Bulles « ? »** : dessinées au-dessus de toute la page et recalées dans l'écran. Elles ne sont plus coupées par un tableau qui défile et ne sortent plus sur les bords d'un téléphone. Ouverture au survol sur ordinateur, au toucher sur téléphone ; fermeture par Échap ou en touchant ailleurs.
- **Page campagne** :
  - ordinateur (≥ 1280 px) : panneau à droite ;
  - tablette / téléphone : dépôt en haut (l'action du terrain), puis la liste, puis dates et sites ;
  - liste des fichiers : tableau compact sur ordinateur (date sous le nom, plus de défilement horizontal), cartes sur une ou deux colonnes en dessous de 1024 px ;
  - suppression avec confirmation.
- **Synthèse** : sur téléphone, une carte par site avec les 3 phases côte à côte.
- **Page détail** :
  - tuiles 2 × 2 sur téléphone ;
  - seuil de confiance placé dans le bloc du spectrogramme, puisqu'il change les cadres affichés ;
  - liste des cris en cartes compactes sur téléphone, tableau à partir de 768 px ;
  - la liste défile jusqu'au cri sélectionné.
- Vérifié à 375 px (téléphone), 768 px (tablette) et 1920 px : aucune page ne déborde.

## 2026-11-05 (soir) — Audit complet + mise en ligne temporaire

Déclencheur : Flavien a relevé un texte faux dans l'interface (« les cris sous le seuil réapparaissent »). Il a
demandé une relecture complète : code, doc, BatDetect2 (dépôt, doc, tickets), cahier des charges, bonnes pratiques.
Il a aussi demandé une mise en ligne temporaire.

- **Rapport complet : `docs/AUDIT.md`** (ce qui était faux, cahier des charges point par point, usage de
  BatDetect2, explication du code, ce qui manque pour prouver un impact, problèmes restants).
- **Corrigé** :
  - **Bug Barbastelle** : le modèle écrit « Barbastellus » ; ses cris tombaient tous dans « Autre ».
  - **Synthèse** : festival et témoin ne sont plus jamais mélangés.
  - **Seuil** : cris gardés dès 0,1 et comptés au-dessus de 0,3, en strict comme BatDetect2 (les scores arrivent
    arrondis).
  - **Fréquence maximale** : les détections au-dessus de la moitié de l'échantillonnage sont jetées, comme
    `process_file` (ticket #22).
  - **AudioMoth en mode déclenché** : les fichiers `T.WAV` sont refusés.
  - **Heure** : heure + fuseau lus dans les blocs GUANO/ICMT AudioMoth et convertis en heure française ; sinon, heure
    du nom signalée « fuseau non vérifié ».
  - **Versions et fuseaux** : `batdetect2==1.3.1` figé ; ajout de `tzdata`.
  - **Interface** : confirmation avant de retirer un site ; dépôt des fichiers un par un.
  - **Textes** de l'interface et page Doc réécrits avec leurs sources.
- **Ajouté** :
  - `install.bat`, `start.bat`, `README.md` (point 3 du cahier des charges) ;
  - `Dockerfile` et `deploy/docker-compose.yml` ;
  - 44 tests (dont métadonnées AudioMoth, 192 kHz, seuil strict).
- **En ligne (temporaire)** : https://chiro.example.org
  - Serveur : un serveur personnel, Traefik + Let's Encrypt, accès par identifiant / mot de passe (`deploy/.env`, non commité).
  - Tests passés sur le serveur Linux (44/44).
  - Dépôt de 46 Mo par Internet OK.
  - Vitesse d'analyse sur le serveur : ~3× le temps réel.
  - Injoignable depuis le réseau de la maison (pas de « hairpin » sur la box) : tester en 4G.
- **Restant prioritaire** :
  - export par nuit et statistique BACI ;
  - contacts par groupe ;
  - validation manuelle des cris ;
  - sauvegarde des données en ligne ;
  - licence BatDetect2 CC BY-NC à garder en tête si l'étude est rémunérée.

## 2026-11-05 (soir) — Premier commit + thème clair / sombre

- **Premier commit** (`main`) : tout le projet, sans `deploy/.env` ni les données.
- **Thème clair et sombre** :
  - par défaut, l'interface suit le réglage de l'ordinateur ou du téléphone ;
  - sélecteur à 3 positions dans l'en-tête (Auto ◐ / Clair ☀ / Sombre ☾), mémorisé dans le navigateur ;
  - couleurs centralisées en variables CSS (`src/index.css`), mêmes noms de classes Tailwind ;
  - graphiques de la synthèse et spectrogramme (paramètre `theme=dark`) adaptés ;
  - pas de flash blanc au chargement (script dans `index.html`).

## 2026-11-05 (soir) — Code commenté, README illustré, dépôt public

- **Dépôt public** : https://github.com/King4Kats/chiro-impact (licence MIT pour notre code ; BatDetect2 reste CC BY-NC).
- Avant publication, l'IP publique et le nom du serveur ont été retirés de tout l'historique.
- **Code commenté bloc par bloc** pour un développeur débutant (tous les fichiers). Vérifié automatiquement :
  aucun changement de code (arbre Python et sortie esbuild identiques), 45 tests OK.
- **README réécrit** : principe BACI, contacts, installation, utilisation, 4 schémas (Mermaid), limites.
- **Corrections** : flèche des bulles d'aide en thème sombre, « 1 min 60 s », `{"name": null}` → 422 au lieu de 500.
- **Défauts repérés, pas encore corrigés** : suppressions sans message d'erreur si le serveur échoue (campagne,
  site, fichier) ; changer le site d'un fichier ne vérifie pas les doublons ; la frise d'un fichier n'a pas de
  commande clavier propre ; CORS ouvert à toutes les origines.
- Le site en ligne temporaire n'a pas encore reçu le thème clair/sombre ni ces corrections.
