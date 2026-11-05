# Audit complet de Chiro Impact — 5 novembre 2026

Relecture de tout le projet (code, interface, documentation), confrontée au cahier des charges, à la documentation
et aux tickets de BatDetect2, au firmware AudioMoth et à la littérature. Écrit pour être lu par un développeur
débutant : chaque notion est expliquée.

---

## 0. En bref

| Question | Réponse courte |
|---|---|
| L'application fonctionne-t-elle ? | **Oui, de bout en bout.** Elle est en ligne (adresse temporaire protégée) et passe 44 tests automatiques sur Windows et sur le serveur Linux, avec de vrais cris de chauves-souris. |
| Répond-elle au besoin ? | **En partie.** Elle produit correctement les données (cris, contacts, groupes, par site, phase et nuit) et les présente sans mélanger festival et témoin. Elle **ne prouve pas** un impact. Il faut encore une plage horaire fixe par nuit, plusieurs nuits par phase et une analyse statistique (§ 5). |
| Utilise-t-on bien BatDetect2 ? | **Maintenant oui.** Quatre écarts ont été trouvés et corrigés aujourd'hui (§ 3). Limite de fond : le modèle est anglais et n'a jamais été évalué sur des données françaises. |
| Les textes affichés étaient-ils justes ? | **Non.** Huit affirmations étaient fausses ou non vérifiées, dont une que j'avais écrite moi-même et répétée à l'oral (§ 1). Elles sont corrigées, et la page « Comment ça marche » cite maintenant ses sources. |

---

## 1. Ce qui était faux (et que j'avais présenté comme vrai)

| # | Affirmation | Réalité | Correction |
|---|---|---|---|
| 1 | « Les cris sous le seuil réapparaissent si tu baisses le seuil » | Faux sous 0,3 : ces cris n'étaient jamais enregistrés. | L'analyse garde les cris dès 0,1. Les chiffres restent calculés à 0,3. Le curseur montre vraiment les cris faibles. |
| 2 | « 0,3 est la valeur par défaut de BatDetect2 » | Le défaut de l'API est 0,01. 0,3 est la valeur des **exemples** de la doc, que l'auteur appelle « un bon point de départ » (ticket #72). | Texte corrigé : 0,3 est un **choix** de notre part. |
| 3 | « Abaisser le seuil d'analyse ne change rien aux cris comptés » | Faux sur l'extrait Sérotine : 21 cris au lieu de 20. BatDetect2 arrondit les scores à 3 décimales, et un score brut de 0,2996 arrivait sous la forme 0,300. | Comptage avec « score **>** 0,3 » (strict), comme BatDetect2. Test de non-régression ajouté. |
| 4 | Groupe « Barbastelle » | **Bug** : le modèle écrit « Barbastellus barbastellus » et notre table attendait « Barbastella ». Toutes les Barbastelles tombaient dans « Autre ». Présent depuis la première version, jamais remarqué. | Table corrigée. Un test vérifie que chacune des 17 classes du modèle a un groupe. Les cris déjà en base sont reclassés au démarrage. |
| 5 | « Le modèle est fiable au niveau du groupe » | Jamais vérifié en France. Les études citées (Rydell 2017, Brabant 2018) portaient sur **d'autres** logiciels. | Retiré. Remplacé par « indication à faire confirmer ». |
| 6 | « F. haute : Pipistrelle commune autour de 45 kHz » | 45 kHz est la fréquence où son cri est le plus fort, pas sa fréquence haute. | Texte corrigé. |
| 7 | Synthèse : tuiles « Avant / Pendant / Après » | Elles **mélangeaient** le site témoin et les sites du festival. Dans la démo, le « 480 contacts/h » était la moyenne de 240 (festival) et 720 (témoin), ce qui va à l'encontre du design BACI. | La synthèse sépare toujours **festival** et **témoin**, avec la variation par rapport à « avant ». |
| 8 | Divers (« chaque trait est un cri », « cris sûrs », « 30 à 77 % », « aucun son ne quitte le PC ») | Trop affirmatifs, chiffre inexact (31 à 77 %, une seule étude), ou faux une fois en ligne. | Corrigés. |

Aussi, à l'oral, j'avais généralisé « la séparation bruit / chauve-souris marche très bien ». La source (Rydell 2017)
ne parle que de la **pluie**, et pour d'autres logiciels. L'auteur de BatDetect2 dit au contraire que le modèle peut
confondre insectes et bruits avec des chauves-souris.

---

## 2. Le cahier des charges, point par point

| Exigence | État | Preuve / remarque |
|---|---|---|
| Comparer avant / pendant / après | ✅ | Phase choisie à la main ou « Auto » (dates du festival + heure du fichier). Corrigeable à tout moment. |
| Site témoin hors festival (BACI) | ✅ | Drapeau « témoin ». La synthèse ne mélange jamais témoin et festival (corrigé aujourd'hui). |
| Activité = contacts / heure, contact = tranche de 5 s avec ≥ 1 cri | ✅ avec une réserve | Juste si l'enregistreur tourne **en continu** sur la même plage horaire chaque nuit. Les fichiers en mode déclenché sont refusés (§ 3). |
| Diversité = groupes présents (6 groupes) | ⚠️ | Calculée, mais fragile : un seul cri suffit à « faire exister » un groupe, et la comparaison n'est juste qu'à effort égal (même nombre de nuits ou d'heures). |
| Ne pas compter d'individus | ✅ | Écrit dans l'interface et dans la doc. |
| BatDetect2 | ✅ | Version figée (1.3.1). Utilisation conforme à la doc (§ 3). |
| Interface claire, charte Lagom, « ? » partout | ✅ | Responsive (téléphone, tablette, grand écran), plein écran du spectrogramme. Les textes des « ? » ont été vérifiés. |
| Point 1 : frontend | ✅ | |
| Point 2 : test réel | ✅ | 44 tests automatiques + test manuel + dépôt par Internet. |
| Point 3 : `install.bat`, `start.bat`, README | ✅ (aujourd'hui) | `install.bat` testé sur ce PC (environnement déjà présent). **Pas testé sur un PC vierge.** |
| Point 4 : premier commit | ❌ | Rien n'est commité. |
| v2 : export CSV/PDF, profil horaire, météo, import carte SD | ❌ | Non commencé. |
| **Prouver l'impact** (le but) | ❌ | Voir § 5 : il manque la plage horaire, la réplication et la statistique. |

---

## 3. BatDetect2 : ce que disent la doc et la communauté, et ce qu'on fait

Sources : dépôt <https://github.com/macaodha/batdetect2> (README, FAQ, licence, code v1.3.1, tickets), article de
Mac Aodha et al. (2022), application note AudioMoth « Triggered T.WAV », firmware AudioMoth (`main.c`).

| Point | Ce que dit la source | Ce que fait l'appli |
|---|---|---|
| Fichiers longs | `process_file` charge tout le fichier en mémoire (≈ 5,5 Go pour 1 h à 384 kHz). | Lecture par blocs de 60 s, analyse par tranches de 3 s comme BatDetect2. **Résultat identique** (testé sur 6 fichiers, dont un de 150 s et un à 192 kHz). |
| Fréquence max. (ticket #22) | `process_file` jette les détections au-dessus de la moitié de l'échantillonnage d'origine (artefacts du passage à 256 kHz). `process_audio`, que nous utilisons, ne le fait pas. | **Corrigé aujourd'hui** : on ne les jetait pas, on les tronquait seulement. Testé avec un fichier à 192 kHz. |
| Seuil (#72) | « Garder les détections avec un seuil bas » ; 0,3 « bon point de départ » ; seuil dépendant des espèces. | Garde dès 0,1, compte à 0,3 (strict). Le seuil se règle sans relancer l'analyse. |
| Scores (#46) | Ce ne sont pas des probabilités ; à calibrer sur ses données. | Interface : « score », plus « probabilité ». |
| Faux positifs (#48, #50, FAQ) | Insectes, bruits, harmoniques pris pour des chauves-souris. | Signalés dans la doc. **Pas d'outil pour marquer un faux positif** (§ 6). |
| Cris sociaux, phases de capture (#49, #59) | Non détectés ; `event` toujours « Echolocation ». | Écrit dans la doc. |
| Espèces | 17 espèces britanniques ; nom « Barbastellus » mal orthographié (#62). | Corrigé (§ 1). Espèces françaises absentes listées dans la doc (Pipistrelle de Kuhl, Vespère de Savi, Minioptère, Molosse, Grand murin…). |
| Évaluation en France | **Aucune publication trouvée.** | Doc : « le modèle n'a pas été évalué sur des données françaises ». |
| Licence | **CC BY-NC 4.0** (code ET modèle) : non commercial. | Écrit dans la doc et le README. ⚠️ Si l'étude est payée par le festival : demander l'accord des auteurs. |
| Version | v1.3.1 stable ; v2 en bêta (résultats différents). | Version figée `batdetect2==1.3.1`. |
| AudioMoth en mode déclenché | Fichiers `…T.WAV` dont les silences ont été retirés ; il faut les « déplier ». | **Refusés** avec la marche à suivre : sinon l'activité est fausse et biaisée vers « impact ». |
| Heure AudioMoth | Noms de fichiers en **UTC par défaut** ; heure + fuseau dans le commentaire et le bloc GUANO. | **Lus et convertis** en heure française. Sans métadonnées : heure du nom, signalée « fuseau non vérifié ». |
| Échantillonnage | AudioMoth : 250 ou 384 kHz (pas de 256). Le modèle voit 10-120 kHz. | Doc corrigée (« 256 » était faux). Refus sous 96 kHz. |

---

## 4. Comment marche le code (pour un dev junior)

### Le trajet d'un fichier WAV

1. **Dépôt** (`frontend/src/components/UploadZone.jsx` → `POST /api/campaigns/{id}/recordings` dans
   `backend/app/main.py`). Les fichiers partent **un par un**. Le serveur les écrit sur le disque, vérifie que
   c'est un WAV lisible, refuse un échantillonnage trop bas ou un T.WAV, lit l'heure (`metadata.py`), en déduit la
   nuit et, en mode « Auto », la phase (`analysis.py`).
2. **File d'analyse** (`worker.py`). Un seul « ouvrier » (thread) analyse les fichiers l'un après l'autre.
   BatDetect2 utilise déjà plusieurs cœurs. Si le serveur redémarre, les analyses non terminées sont reprises.
3. **Détection** (`detection.py`). Lecture par blocs de 60 s, passage à 256 kHz, tranches de 3 s envoyées au modèle,
   détections au-dessus de la fréquence max. du fichier jetées.
4. **Calculs** (`analysis.py`). Contacts = tranches de 5 s avec au moins un cri de score > 0,3. Groupe = table
   espèce → groupe.
5. **Affichage**. Spectrogramme dessiné à la demande (`spectro.py`) à la taille exacte de l'écran. Écoute ralentie
   ×10. Synthèse par phase, type de site et nuit.

### Les fichiers

| Fichier | Rôle |
|---|---|
| `backend/app/main.py` | Toutes les routes de l'API (FastAPI). Sert aussi l'interface compilée. |
| `backend/app/db.py` | Base SQLite : 4 tables (campaigns, sites, recordings, calls). Ajoute les colonnes manquantes au démarrage, pour faire évoluer une base existante. |
| `backend/app/detection.py` | Pont vers BatDetect2. |
| `backend/app/analysis.py` | Groupes, contacts, dates, nuits, phases, résumés. |
| `backend/app/metadata.py` | Lecture de l'heure et du fuseau dans les blocs du WAV (sans lire le son). |
| `backend/app/spectro.py` | Image du spectrogramme et extrait audio ralenti. |
| `backend/app/worker.py` | File d'attente des analyses. |
| `backend/app/config.py` | Réglages par variables d'environnement. |
| `backend/tests/` | 44 tests (pytest) : calculs, détection comparée à BatDetect2, métadonnées, parcours complet de l'API. |
| `frontend/src/pages/` | Pages : liste des campagnes, campagne, détail d'un fichier, doc. |
| `frontend/src/components/` | Morceaux réutilisables (bulles d'aide, dépôt, sites, dates, synthèse). |
| `Dockerfile`, `deploy/` | Mise en ligne (image unique + Traefik). |

### Notions utiles

- **Échantillonnage / Nyquist** : un fichier à 384 kHz contient des sons jusqu'à 192 kHz (la moitié). À 192 kHz,
  rien au-dessus de 96 kHz.
- **Score de détection** : nombre de 0 à 1 donné par le modèle. Ce n'est pas une probabilité.
- **Contact** : unité d'activité. Une tranche de 5 s avec au moins un cri compte 1, qu'il y ait 1 ou 40 cris.
- **BACI** : Before/After × Control/Impact. L'effet du festival se mesure par **différence de différences**
  (variation festival − variation témoin), jamais sur un site seul.

---

## 5. Ce qu'il manque pour prouver un impact (le vrai besoin)

1. **Plage horaire fixe chaque nuit** (ex. coucher − 30 min → lever + 30 min, protocole Vigie-Chiro). Aujourd'hui
   l'activité est divisée par la durée des fichiers. C'est juste en continu, mais rien ne garantit que chaque nuit
   couvre la même plage.
2. **Plusieurs nuits par phase** (au moins 3 à 5) sur chaque site. Skalak et al. (2012) : plusieurs nuits sont
   nécessaires même pour les espèces communes. L'appli calcule déjà les chiffres **par nuit** (API `summary.nights`),
   mais ne les affiche pas encore.
3. **Météo par nuit** (température, vent, pluie), facteur majeur de variation.
4. **Statistique** : modèle de comptage des contacts par nuit, binomial négatif, effet « phase × type de site ».
   À faire en R ou Python à partir d'un **export CSV par nuit** (à développer, c'était prévu en v2).
5. **Analyse par groupe** : Hooker et al. (2023), étude publiée sur la musique de festival, trouvent un effet sur
   les Noctules / Sérotines et la Pipistrelle commune, pas sur les Myotis. L'appli compte les contacts tous groupes
   confondus.
6. **Relecture humaine** d'un échantillon de cris par phase et par site, pour estimer les faux positifs.

---

## 6. Problèmes restants (par gravité)

| Gravité | Problème | Piste |
|---|---|---|
| Haute | Pas d'analyse statistique ni d'export par nuit | Export CSV « site × nuit × groupe », puis script d'analyse |
| Haute | Contacts tous groupes confondus | Ajouter les contacts **par groupe** |
| Haute | Pas d'outil de validation (marquer « pas une chauve-souris ») | Bouton par cri, exclu des chiffres ; taux de relecture affiché |
| Moyenne | Fichiers T.WAV refusés au lieu d'être dépliés | Porter `expand.c` d'Open Acoustic Devices (court) |
| Moyenne | Plage horaire non contrôlée | Lieu du site (lat/lon) → coucher/lever du soleil → ne garder que la plage |
| Moyenne | Diversité = union sur un effort inégal | Groupes par nuit, minimum de contacts par groupe |
| Moyenne | Licence CC BY-NC de BatDetect2 | Vérifier que l'usage n'est pas rémunéré, sinon demander aux auteurs |
| Moyenne | En ligne : un seul identifiant partagé, pas de comptes | Comptes (ou au minimum un mot de passe par personne) avant la vraie mise en ligne |
| Moyenne | Données en ligne non sauvegardées | Sauvegarde du volume Docker `chiro-impact_data` (base + WAV) |
| Moyenne | Dépôt d'un très gros fichier (> ~1 min de transfert) coupé par le proxy | Envoi par morceaux, ou réglage du délai Traefik |
| Moyenne | Vitesse : ~8× le temps réel sur le PC, **~3× sur le serveur** (limité à 4 cœurs). Une nuit de 10 h d'un enregistreur ≈ 3 h 20 d'analyse en ligne | Monter `CHIRO_THREADS`/`cpus`, ou analyser en local |
| Basse | Recharts 2 n'est plus maintenu ; bundle JS de 600 ko | Passer à Recharts 3, découper le bundle |
| Basse | Pas de tests de l'interface | Quelques tests Playwright sur les parcours principaux |
| Basse | `install.bat` jamais testé sur un PC vierge | Le tester sur un autre PC de l'asso |
| Basse | Rien n'est commité | Premier commit, puis dépôt GitHub |

---

## 7. Bonnes pratiques

**Respectées** :
- Tests automatiques sur de vrais enregistrements, avec comparaison au résultat officiel de BatDetect2.
- Données de test isolées (dossier temporaire).
- Version du modèle figée.
- Aucun secret dans le code : le mot de passe est dans `deploy/.env`, exclu de git.
- Conteneur sans droits administrateur, limité en CPU et mémoire.
- HTTPS.
- Accès protégé.
- Commentaires en français simple.
- Journal de décisions (`SUIVI_PROJET.md`).

**Non respectées** :
- Pas de commits, donc pas d'historique.
- Pas de sauvegarde des données en ligne.
- Pas de tests d'interface.
- CORS ouvert à tous (inutile en ligne, à restreindre).
- Pas de limite de taille par fichier.
- Un seul compte partagé.

---

## 8. Mise en ligne temporaire

- Adresse : <https://chiro.example.org> (sslip.io pointe automatiquement vers l'IP du serveur ;
  certificat Let's Encrypt).
- Serveur : un serveur personnel, dossier `~/Serveur/chiro-impact`, conteneur `chiro-impact-app-1`, volume
  `chiro-impact_data`.
- Accès : identifiant et mot de passe dans `deploy/.env` (non commité).
- Depuis le réseau de la maison, l'adresse publique ne répond pas (la box ne renvoie pas vers l'intérieur) : tester
  depuis un téléphone en 4G/5G, ou hors de la maison.
- Mettre à jour : recopier le projet dans `~/Serveur/chiro-impact`, puis
  `docker compose -f deploy/docker-compose.yml --env-file deploy/.env up -d --build`.
