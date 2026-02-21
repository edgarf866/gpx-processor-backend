"""
============================================================
MODÈLES DE DONNÉES (Pydantic)
============================================================
En PHP, tu utilises des classes ou des tableaux associatifs.
En Python/FastAPI, on utilise Pydantic pour :
  - Définir la structure des données
  - Valider automatiquement les entrées
  - Générer la doc API automatiquement
  
C'est comme un "contrat" : si les données ne correspondent pas
au modèle, FastAPI renvoie automatiquement une erreur 422.
============================================================
"""

from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class GPXValidationResult(BaseModel):
    """Résultat de la validation d'un fichier GPX"""
    is_valid: bool
    filename: str
    total_points: int
    errors: list[str] = []
    warnings: list[str] = []


class GeometryCorrections(BaseModel):
    """Détail des corrections appliquées à la géométrie"""
    artifacts_removed: int = 0          # Points aberrants supprimés
    self_intersections_fixed: int = 0   # Auto-intersections corrigées
    invalid_geometries_fixed: int = 0   # Géométries invalides réparées
    duplicate_vertices_removed: int = 0 # Vertices en double supprimés
    spikes_removed: int = 0             # Pics/pointes supprimés
    details: list[str] = []             # Détails textuels des corrections


class AreaCalculation(BaseModel):
    """Résultat du calcul de superficie"""
    area_sq_meters: float       # Surface en m²
    area_hectares: float        # Surface en hectares
    area_sq_km: float           # Surface en km²
    perimeter_meters: float     # Périmètre en mètres
    projection_used: str        # Projection utilisée pour le calcul


class ProcessingResult(BaseModel):
    """Résultat complet du traitement d'un fichier GPX"""
    id: str                                     # Identifiant unique du traitement
    filename: str
    uploaded_at: datetime
    validation: GPXValidationResult
    corrections: GeometryCorrections
    area: Optional[AreaCalculation] = None
    original_geojson: Optional[dict] = None     # GeoJSON original (pour affichage)
    corrected_geojson: Optional[dict] = None    # GeoJSON corrigé (pour affichage)
    polygon_geojson: Optional[dict] = None      # Polygone final (pour affichage)
    status: str = "pending"                     # pending, processing, completed, error
    error_message: Optional[str] = None


class HistoryItem(BaseModel):
    """Élément de l'historique des uploads"""
    id: str
    filename: str
    uploaded_at: datetime
    status: str
    area_hectares: Optional[float] = None
    total_corrections: int = 0
