"""
============================================================
GPX PROCESSOR - APPLICATION PRINCIPALE
============================================================
C'est le point d'entrée de ton backend FastAPI.

CONCEPTS CLÉS POUR TOI QUI VIENS DE PHP :
- En PHP, tu as des fichiers .php que Apache/Nginx sert directement
- En Python/FastAPI, tu as UNE application qui tourne en continu
- Les routes sont définies avec des décorateurs (@app.get, @app.post)
- FastAPI génère automatiquement la doc API sur /docs (Swagger)

POUR LANCER : uvicorn app.main:app --reload --port 8000
              Puis ouvre http://localhost:8000/docs
============================================================
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os

# --- Création de l'application ---
# En PHP : c'est comme ton index.php principal
# En FastAPI : on crée un objet "app" qui gère tout
app = FastAPI(
    title="GPX Processor API",
    description="API de traitement de fichiers GPX : validation, correction, calcul de superficie",
    version="1.0.0"
)

# --- CORS (Cross-Origin Resource Sharing) ---
# Permet au frontend React (port 3000) de communiquer avec le backend (port 8000)
# En PHP, tu faisais ça avec des headers dans chaque fichier
# Ici, un seul middleware gère tout
# En dev : localhost. En prod : Railway génère des URLs en *.up.railway.app
# On accepte tout pour simplifier (tu peux restreindre plus tard)
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS + ["*"],  # Accepte tout (à restreindre en prod)
    allow_credentials=True,
    allow_methods=["*"],    # GET, POST, PUT, DELETE...
    allow_headers=["*"],
)

# --- Créer les dossiers nécessaires ---
os.makedirs("uploads", exist_ok=True)
os.makedirs("exports", exist_ok=True)
os.makedirs("reports", exist_ok=True)

# --- Import des routes ---
# En PHP : tu aurais un routeur ou des include()
# En FastAPI : on "inclut" des groupes de routes (routers)
from app.routes import gpx_routes, history_routes

app.include_router(gpx_routes.router, prefix="/api/gpx", tags=["GPX Processing"])
app.include_router(history_routes.router, prefix="/api/history", tags=["Historique"])

# --- Servir les fichiers statiques (exports, rapports) ---
app.mount("/exports", StaticFiles(directory="exports"), name="exports")
app.mount("/reports", StaticFiles(directory="reports"), name="reports")

# --- Route de base (healthcheck) ---
@app.get("/")
def root():
    """
    Route racine - vérifie que l'API tourne.
    En PHP : c'est comme un simple echo "OK";
    """
    return {
        "status": "running",
        "message": "GPX Processor API v1.0",
        "docs": "Accède à /docs pour voir la documentation interactive"
    }
