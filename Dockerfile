# ===========================================================================
#  Image Docker de Chiro Impact : une seule image qui contient l'interface
#  compilée ET le serveur Python (FastAPI + BatDetect2).
#
#  Étape 1 : Node compile l'interface React (frontend/dist).
#  Étape 2 : Python installe le serveur ; PyTorch en version « CPU »
#            (~200 Mo au lieu de ~2,5 Go pour la version carte graphique).
#
#  Construire :  docker build -t chiro-impact .
#  Lancer     :  docker run -p 8000:8000 -v chiro-data:/data chiro-impact
# ===========================================================================
#
#  Pour débuter :
#  - Une « image » Docker est un paquet figé qui contient un système minimal, les
#    programmes et notre code. Un « conteneur » est une image en train de tourner.
#  - Ce fichier est une recette lue de haut en bas. Chaque instruction (FROM, COPY,
#    RUN…) crée une « couche » ; Docker garde les couches en cache et ne refait que
#    celles dont les entrées ont changé.
#  - « Multi-étapes » : il y a deux FROM. La première étape sert seulement à construire
#    l'interface (elle a besoin de Node). On n'en garde que le résultat (dist/) ;
#    Node et node_modules ne finissent pas dans l'image finale, qui reste plus légère.
#  - Travaille avec : .dockerignore (fichiers exclus de la copie), deploy/docker-compose.yml
#    (lancement sur le serveur), backend/app/config.py (lit les variables ENV ci-dessous).

# ---------- Étape 1 : interface ----------
# Image officielle Node 22, variante alpine (très petite). « AS frontend » donne un nom à
# cette étape pour pouvoir y piocher des fichiers plus tard (COPY --from=frontend).
FROM node:22-alpine AS frontend
WORKDIR /front
# On copie d'abord SEULEMENT la liste des dépendances, puis on les installe. Tant que ces
# deux fichiers ne changent pas, Docker réutilise la couche en cache et saute l'installation.
# npm ci : installe exactement les versions écrites dans package-lock.json (installation
# reproductible), contrairement à npm install qui peut les mettre à jour.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
# Puis le reste du code de l'interface, et la construction (Vite écrit le résultat dans dist/).
COPY frontend/ ./
RUN npm run build

# ---------- Étape 2 : serveur ----------
# Image officielle Python 3.12 allégée : c'est la base de l'image finale.
FROM python:3.12-slim
# Variables d'environnement :
#  - PYTHONDONTWRITEBYTECODE / PYTHONUNBUFFERED : pas de fichiers .pyc, et les messages
#    du programme s'affichent tout de suite dans les journaux (docker logs) ;
#  - PIP_NO_CACHE_DIR : pip ne garde pas ses téléchargements (image plus légère) ;
#  - CHIRO_DATA_DIR : dossier des données (base + WAV), qui sera un volume ;
#  - CHIRO_FRONT_DIST : où le serveur trouve l'interface construite à l'étape 1 ;
#  - MPLCONFIGDIR : dossier de travail de matplotlib, placé dans /tmp où l'utilisateur
#    sans droits peut écrire.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    CHIRO_DATA_DIR=/data \
    CHIRO_FRONT_DIST=/app/frontend/dist \
    MPLCONFIGDIR=/tmp/matplotlib
WORKDIR /app/backend

# PyTorch CPU d'abord (depuis le dépôt officiel PyTorch), puis le reste
# Même astuce de cache qu'à l'étape 1 : requirements.txt est copié seul avant le code,
# pour ne pas réinstaller toutes les dépendances à chaque modification du code.
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu
COPY backend/requirements.txt ./
RUN pip install -r requirements.txt

# Le code du serveur, puis l'interface construite récupérée dans l'étape « frontend ».
COPY backend/app ./app
COPY --from=frontend /front/dist /app/frontend/dist

# Utilisateur sans droits d'administration ; /data = base SQLite + WAV déposés (volume)
# Si l'appli était piratée, l'attaquant n'aurait pas les droits root dans le conteneur.
# VOLUME : /data est stocké hors du conteneur. Les données survivent quand on reconstruit
# ou remplace le conteneur (sinon elles disparaîtraient avec lui).
# EXPOSE : indique que l'appli écoute sur le port 8000 (documentation ; c'est -p ou
# docker-compose qui ouvre réellement le port).
RUN useradd --uid 1000 --create-home chiro && mkdir -p /data && chown chiro:chiro /data
USER chiro
VOLUME ["/data"]
EXPOSE 8000

# HEALTHCHECK : toutes les 30 s, Docker lance cette petite commande Python qui appelle
# /api/health. Si elle échoue, le conteneur est marqué « unhealthy » (visible dans docker ps).
# start-period=60s : on laisse une minute au serveur pour démarrer avant de compter les échecs.
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')" || exit 1

# Commande lancée au démarrage du conteneur : uvicorn, le serveur web qui fait tourner
# l'appli FastAPI (objet `app` du fichier app/main.py). --host 0.0.0.0 : accepter les
# connexions venant de l'extérieur du conteneur (127.0.0.1 ne serait joignable que de l'intérieur).
# --proxy-headers : derrière Traefik, l'appli sait que le visiteur est en HTTPS
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
