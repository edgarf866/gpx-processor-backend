"""
============================================================
ROUTES HISTORIQUE
============================================================
Gère la consultation et la suppression de l'historique des uploads.
============================================================
"""

from fastapi import APIRouter, HTTPException
from app import storage

router = APIRouter()


@router.get("/")
async def get_history(limit: int = 50):
    """
    Récupère l'historique des uploads.
    
    ?limit=10 → paramètre de query string (comme ?limit=10 en PHP)
    FastAPI le détecte automatiquement dans les paramètres de la fonction.
    """
    history = storage.get_history(limit=limit)
    return {"history": history, "total": len(history)}


@router.get("/{entry_id}")
async def get_entry(entry_id: str):
    """Récupère une entrée spécifique."""
    entry = storage.get_entry(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entrée non trouvée")
    return entry


@router.delete("/{entry_id}")
async def delete_entry(entry_id: str):
    """Supprime une entrée de l'historique."""
    deleted = storage.delete_entry(entry_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Entrée non trouvée")
    return {"message": "Supprimé avec succès", "id": entry_id}
