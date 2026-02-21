"""
============================================================
SERVICE DE STOCKAGE (Historique des uploads)
============================================================
Pour le MVP, on utilise un simple fichier JSON pour stocker
l'historique. En production, tu remplacerais par PostgreSQL/MySQL.

En PHP, tu utiliserais probablement une base de données directement.
En Python, on abstrait le stockage dans un "service" pour pouvoir
facilement changer la source de données plus tard.

C'est un bon pattern : Storage → JSON maintenant → PostgreSQL plus tard
sans toucher au reste du code.
============================================================
"""

import json
import os
from datetime import datetime
from typing import Optional


HISTORY_FILE = "uploads/history.json"


def _load_history() -> list:
    """Charge l'historique depuis le fichier JSON."""
    if not os.path.exists(HISTORY_FILE):
        return []
    
    try:
        with open(HISTORY_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def _save_history(history: list):
    """Sauvegarde l'historique dans le fichier JSON."""
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2, default=str)


def add_to_history(entry: dict):
    """Ajoute une entrée à l'historique."""
    history = _load_history()
    history.insert(0, entry)  # Ajouter en début (plus récent en premier)
    _save_history(history)


def get_history(limit: int = 50) -> list:
    """Récupère l'historique (les N plus récents)."""
    history = _load_history()
    return history[:limit]


def get_entry(entry_id: str) -> Optional[dict]:
    """Récupère une entrée par son ID."""
    history = _load_history()
    for entry in history:
        if entry.get("id") == entry_id:
            return entry
    return None


def delete_entry(entry_id: str) -> bool:
    """Supprime une entrée de l'historique."""
    history = _load_history()
    new_history = [e for e in history if e.get("id") != entry_id]
    
    if len(new_history) == len(history):
        return False  # Pas trouvé
    
    _save_history(new_history)
    return True
