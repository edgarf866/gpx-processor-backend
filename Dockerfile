# ============================================================
# DOCKERFILE - GPX Processor Backend
# ============================================================
# Railway utilise ce fichier pour construire et lancer le backend.
#
# POURQUOI un Dockerfile ?
# Les libs géo (GDAL, GEOS, PROJ) ont besoin de dépendances système
# que pip seul ne peut pas installer. Le Dockerfile gère tout.
#
# Railway détecte automatiquement le Dockerfile et l'utilise.
# ============================================================

FROM python:3.11-slim

# --- Dépendances système pour les libs géospatiales ---
# libgdal-dev = GDAL (lecture/écriture formats géo)
# libgeos-dev = GEOS (opérations géométriques pour Shapely)
# libproj-dev = PROJ (reprojections de coordonnées)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgdal-dev \
    libgeos-dev \
    libproj-dev \
    gdal-bin \
    && rm -rf /var/lib/apt/lists/*

# --- Dossier de travail ---
WORKDIR /app

# --- Installer les dépendances Python ---
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# --- Copier le code ---
COPY . .

# --- Créer les dossiers nécessaires ---
RUN mkdir -p uploads exports reports

# --- Port (Railway injecte la variable PORT) ---
EXPOSE 8000

# --- Commande de lancement ---
# Railway définit $PORT automatiquement
# On utilise gunicorn en production (plus stable qu'uvicorn seul)
CMD gunicorn app.main:app \
    --workers 2 \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:${PORT:-8000} \
    --timeout 300
