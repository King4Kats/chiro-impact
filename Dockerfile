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

# ---------- Étape 1 : interface ----------
FROM node:22-alpine AS frontend
WORKDIR /front
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---------- Étape 2 : serveur ----------
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    CHIRO_DATA_DIR=/data \
    CHIRO_FRONT_DIST=/app/frontend/dist \
    MPLCONFIGDIR=/tmp/matplotlib
WORKDIR /app/backend

# PyTorch CPU d'abord (depuis le dépôt officiel PyTorch), puis le reste
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu
COPY backend/requirements.txt ./
RUN pip install -r requirements.txt

COPY backend/app ./app
COPY --from=frontend /front/dist /app/frontend/dist

# Utilisateur sans droits d'administration ; /data = base SQLite + WAV déposés (volume)
RUN useradd --uid 1000 --create-home chiro && mkdir -p /data && chown chiro:chiro /data
USER chiro
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')" || exit 1

# --proxy-headers : derrière Traefik, l'appli sait que le visiteur est en HTTPS
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
