"""
============================================================
ROUTES GPX - Upload simple + Upload multiple (batch)
============================================================
NOUVEAU : /api/gpx/upload-batch
  → Accepte N fichiers GPX en une seule requête
  → Les traite en parallèle avec ThreadPoolExecutor
  → Retourne tous les résultats groupés
============================================================
"""

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List
import uuid
import json
import os
import zipfile

from app.gpx_service import GPXProcessor
from app.report_service import generate_report
from app import storage

router = APIRouter()
processor = GPXProcessor()

# Pool de threads pour le traitement parallèle (4 fichiers en même temps)
thread_pool = ThreadPoolExecutor(max_workers=4)


def _process_single_file(file_content: str, filename: str) -> dict:
    """
    Traite UN fichier GPX (appelé dans un thread séparé pour le batch).
    """
    entry_id = str(uuid.uuid4())[:8]
    now = datetime.now()
    
    try:
        # Sauvegarder le fichier original
        upload_path = os.path.join("uploads", f"{entry_id}_{filename}")
        with open(upload_path, "w", encoding="utf-8") as f:
            f.write(file_content)
        
        # Traitement complet
        result = processor.process(file_content)
        
        corrections = result.get("corrections", {})
        total_corrections = (
            corrections.get("artifacts_removed", 0) +
            corrections.get("duplicate_vertices_removed", 0) +
            corrections.get("spikes_removed", 0) +
            corrections.get("self_intersections_fixed", 0) +
            corrections.get("invalid_geometries_fixed", 0)
        ) if corrections else 0
        
        # Sauvegarder les exports GeoJSON
        if result.get("polygon_geojson"):
            with open(os.path.join("exports", f"{entry_id}_polygon.geojson"), "w") as f:
                json.dump(result["polygon_geojson"], f, indent=2)
        
        if result.get("original_geojson"):
            with open(os.path.join("exports", f"{entry_id}_points.geojson"), "w") as f:
                json.dump(result["original_geojson"], f, indent=2)
        
        # Ajouter à l'historique
        status = "completed" if result["validation"]["is_valid"] else "error"
        storage.add_to_history({
            "id": entry_id,
            "filename": filename,
            "uploaded_at": now.isoformat(),
            "status": status,
            "area_hectares": result["area"]["area_hectares"] if result.get("area") else None,
            "total_corrections": total_corrections,
            "total_points": result["validation"].get("total_points", 0)
        })
        
        return {
            "id": entry_id,
            "filename": filename,
            "uploaded_at": now.isoformat(),
            "validation": result["validation"],
            "corrections": result.get("corrections"),
            "area": result.get("area"),
            "original_geojson": result.get("original_geojson"),
            "corrected_geojson": result.get("corrected_geojson"),
            "polygon_geojson": result.get("polygon_geojson"),
            "line_geojson": result.get("line_geojson"),
            "status": status,
            "error_message": None
        }
        
    except Exception as e:
        return {
            "id": entry_id,
            "filename": filename,
            "uploaded_at": now.isoformat(),
            "validation": {"is_valid": False, "errors": [str(e)], "warnings": [], "total_points": 0},
            "corrections": None,
            "area": None,
            "original_geojson": None,
            "corrected_geojson": None,
            "polygon_geojson": None,
            "line_geojson": None,
            "status": "error",
            "error_message": str(e)
        }


# ==========================================================
# UPLOAD SIMPLE (1 fichier)
# ==========================================================
@router.post("/upload")
async def upload_gpx(file: UploadFile = File(...)):
    """Upload et traitement d'un seul fichier GPX."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="Aucun fichier fourni")
    if not file.filename.lower().endswith(".gpx"):
        raise HTTPException(status_code=400, detail="Le fichier doit être au format .gpx")
    
    try:
        content = await file.read()
        file_content = content.decode("utf-8")
    except UnicodeDecodeError:
        file_content = content.decode("latin-1")
    
    return _process_single_file(file_content, file.filename)


# ==========================================================
# UPLOAD MULTIPLE (N fichiers en parallèle)
# ==========================================================
@router.post("/upload-batch")
async def upload_batch(files: List[UploadFile] = File(...)):
    """
    Upload et traitement de PLUSIEURS fichiers GPX en parallèle.
    Maximum 50 fichiers par batch.
    """
    if not files:
        raise HTTPException(status_code=400, detail="Aucun fichier fourni")
    if len(files) > 50:
        raise HTTPException(status_code=400, detail="Maximum 50 fichiers par batch")
    
    # Lire tous les fichiers
    file_contents = []
    skipped = []
    
    for f in files:
        if not f.filename.lower().endswith(".gpx"):
            skipped.append({"filename": f.filename, "reason": "Format non supporté (.gpx requis)"})
            continue
        try:
            content = await f.read()
            try:
                text = content.decode("utf-8")
            except UnicodeDecodeError:
                text = content.decode("latin-1")
            file_contents.append({"filename": f.filename, "content": text})
        except Exception as e:
            skipped.append({"filename": f.filename, "reason": str(e)})
    
    if not file_contents:
        raise HTTPException(status_code=400, detail="Aucun fichier GPX valide")
    
    # Traitement en parallèle
    results = []
    futures = {}
    
    for fc in file_contents:
        future = thread_pool.submit(_process_single_file, fc["content"], fc["filename"])
        futures[future] = fc["filename"]
    
    for future in as_completed(futures):
        try:
            result = future.result(timeout=120)
            results.append(result)
        except Exception as e:
            results.append({
                "filename": futures[future],
                "status": "error",
                "error_message": f"Timeout ou erreur : {str(e)}"
            })
    
    # Trier par nom de fichier
    results.sort(key=lambda r: r.get("filename", ""))
    
    # Statistiques groupées
    completed = [r for r in results if r.get("status") == "completed"]
    errors = [r for r in results if r.get("status") == "error"]
    
    total_area = sum(r["area"]["area_hectares"] for r in completed if r.get("area"))
    total_corrections = sum(
        (r["corrections"]["artifacts_removed"] or 0) +
        (r["corrections"]["duplicate_vertices_removed"] or 0) +
        (r["corrections"]["spikes_removed"] or 0) +
        (r["corrections"]["self_intersections_fixed"] or 0) +
        (r["corrections"]["invalid_geometries_fixed"] or 0)
        for r in completed if r.get("corrections")
    )
    
    return {
        "batch_summary": {
            "total_files": len(files),
            "processed": len(completed),
            "errors": len(errors),
            "skipped": len(skipped),
            "total_area_hectares": round(total_area, 4),
            "total_corrections": total_corrections,
        },
        "results": results,
        "skipped_files": skipped
    }


# ==========================================================
# EXPORTS
# ==========================================================
@router.get("/export/{entry_id}/geojson")
async def export_geojson(entry_id: str):
    filepath = os.path.join("exports", f"{entry_id}_polygon.geojson")
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Export non trouvé")
    return FileResponse(filepath, media_type="application/geo+json", filename=f"{entry_id}_polygon.geojson")


@router.get("/export/{entry_id}/shapefile")
async def export_shapefile(entry_id: str):
    geojson_path = os.path.join("exports", f"{entry_id}_polygon.geojson")
    if not os.path.exists(geojson_path):
        raise HTTPException(status_code=404, detail="Export non trouvé")
    try:
        import geopandas as gpd
        gdf = gpd.read_file(geojson_path)
        shp_dir = os.path.join("exports", f"{entry_id}_shp")
        os.makedirs(shp_dir, exist_ok=True)
        gdf.to_file(os.path.join(shp_dir, f"{entry_id}.shp"), driver="ESRI Shapefile")
        zip_path = os.path.join("exports", f"{entry_id}_shapefile.zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in os.listdir(shp_dir):
                zf.write(os.path.join(shp_dir, f), f)
        return FileResponse(zip_path, media_type="application/zip", filename=f"{entry_id}_shapefile.zip")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/export-batch")
async def export_batch_geojson(entry_ids: List[str]):
    """Exporte plusieurs polygones en un seul ZIP."""
    zip_path = os.path.join("exports", f"batch_{uuid.uuid4().hex[:8]}.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for eid in entry_ids:
            filepath = os.path.join("exports", f"{eid}_polygon.geojson")
            if os.path.exists(filepath):
                zf.write(filepath, f"{eid}_polygon.geojson")
    if os.path.getsize(zip_path) == 0:
        os.remove(zip_path)
        raise HTTPException(status_code=404, detail="Aucun export trouvé")
    return FileResponse(zip_path, media_type="application/zip", filename="batch_export.zip")


# ==========================================================
# RAPPORT PDF
# ==========================================================
@router.get("/report/{entry_id}")
async def generate_pdf_report(entry_id: str):
    entry = storage.get_entry(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Traitement non trouvé")
    upload_files = [f for f in os.listdir("uploads") if f.startswith(entry_id) and f.endswith(".gpx")]
    if not upload_files:
        raise HTTPException(status_code=404, detail="Fichier GPX original non trouvé")
    with open(os.path.join("uploads", upload_files[0]), "r", encoding="utf-8") as f:
        content = f.read()
    result = processor.process(content)
    try:
        pdf_path = generate_report(result, f"rapport_{entry_id}.pdf")
        return FileResponse(pdf_path, media_type="application/pdf", filename=f"rapport_{entry_id}.pdf")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
