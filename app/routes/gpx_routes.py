"""
============================================================
ROUTES GPX - Upload simple + batch + exports fusionnés + rapports
============================================================
NOUVEAU :
  - /api/gpx/export-merged : exporte tous les polygones fusionnés en 1 GeoJSON
  - /api/gpx/export-merged-shapefile : idem en Shapefile
  - /api/gpx/report-batch : rapport PDF global du batch
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
from app.report_service import generate_report, generate_batch_report
from app import storage

router = APIRouter()
processor = GPXProcessor()
thread_pool = ThreadPoolExecutor(max_workers=4)


def _process_single_file(file_content: str, filename: str) -> dict:
    """Traite UN fichier GPX dans un thread séparé."""
    entry_id = str(uuid.uuid4())[:8]
    now = datetime.now()
    
    try:
        upload_path = os.path.join("uploads", f"{entry_id}_{filename}")
        with open(upload_path, "w", encoding="utf-8") as f:
            f.write(file_content)
        
        result = processor.process(file_content)
        
        corrections = result.get("corrections", {})
        total_corrections = (
            corrections.get("artifacts_removed", 0) +
            corrections.get("duplicate_vertices_removed", 0) +
            corrections.get("spikes_removed", 0) +
            corrections.get("self_intersections_fixed", 0) +
            corrections.get("invalid_geometries_fixed", 0)
        ) if corrections else 0
        
        if result.get("polygon_geojson"):
            with open(os.path.join("exports", f"{entry_id}_polygon.geojson"), "w") as f:
                json.dump(result["polygon_geojson"], f, indent=2)
        
        if result.get("original_geojson"):
            with open(os.path.join("exports", f"{entry_id}_points.geojson"), "w") as f:
                json.dump(result["original_geojson"], f, indent=2)
        
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
            "corrections": None, "area": None,
            "original_geojson": None, "corrected_geojson": None,
            "polygon_geojson": None, "line_geojson": None,
            "status": "error", "error_message": str(e)
        }


# ==========================================================
# UPLOAD SIMPLE
# ==========================================================
@router.post("/upload")
async def upload_gpx(file: UploadFile = File(...)):
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
# UPLOAD BATCH
# ==========================================================
@router.post("/upload-batch")
async def upload_batch(files: List[UploadFile] = File(...)):
    if not files:
        raise HTTPException(status_code=400, detail="Aucun fichier fourni")
    if len(files) > 50:
        raise HTTPException(status_code=400, detail="Maximum 50 fichiers par batch")
    
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
            results.append({"filename": futures[future], "status": "error", "error_message": str(e)})
    
    results.sort(key=lambda r: r.get("filename", ""))
    
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
    
    # --- Créer le GeoJSON fusionné (tous les polygones ensemble) ---
    merged_features = []
    for r in completed:
        if r.get("polygon_geojson") and r["polygon_geojson"].get("features"):
            for feat in r["polygon_geojson"]["features"]:
                # Ajouter le nom du fichier dans les propriétés
                feat_copy = dict(feat)
                props = dict(feat_copy.get("properties", {}))
                props["filename"] = r["filename"]
                props["id"] = r["id"]
                props["area_hectares"] = r["area"]["area_hectares"] if r.get("area") else None
                feat_copy["properties"] = props
                merged_features.append(feat_copy)
    
    merged_geojson = {
        "type": "FeatureCollection",
        "features": merged_features
    }
    
    # Sauvegarder le GeoJSON fusionné
    batch_id = str(uuid.uuid4())[:8]
    merged_path = os.path.join("exports", f"batch_{batch_id}_merged.geojson")
    with open(merged_path, "w") as f:
        json.dump(merged_geojson, f, indent=2)
    
    return {
        "batch_id": batch_id,
        "batch_summary": {
            "total_files": len(files),
            "processed": len(completed),
            "errors": len(errors),
            "skipped": len(skipped),
            "total_area_hectares": round(total_area, 4),
            "total_corrections": total_corrections,
        },
        "results": results,
        "skipped_files": skipped,
        "merged_geojson": merged_geojson
    }


# ==========================================================
# EXPORTS INDIVIDUELS
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


# ==========================================================
# EXPORTS FUSIONNÉS (tous les polygones d'un batch)
# ==========================================================
@router.get("/export-merged/{batch_id}/geojson")
async def export_merged_geojson(batch_id: str):
    """Exporte le GeoJSON fusionné d'un batch."""
    filepath = os.path.join("exports", f"batch_{batch_id}_merged.geojson")
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Export fusionné non trouvé")
    return FileResponse(filepath, media_type="application/geo+json", filename=f"batch_{batch_id}_merged.geojson")


@router.get("/export-merged/{batch_id}/shapefile")
async def export_merged_shapefile(batch_id: str):
    """Exporte le Shapefile fusionné d'un batch."""
    geojson_path = os.path.join("exports", f"batch_{batch_id}_merged.geojson")
    if not os.path.exists(geojson_path):
        raise HTTPException(status_code=404, detail="Export fusionné non trouvé")
    try:
        import geopandas as gpd
        gdf = gpd.read_file(geojson_path)
        shp_dir = os.path.join("exports", f"batch_{batch_id}_merged_shp")
        os.makedirs(shp_dir, exist_ok=True)
        gdf.to_file(os.path.join(shp_dir, "merged.shp"), driver="ESRI Shapefile")
        zip_path = os.path.join("exports", f"batch_{batch_id}_merged_shapefile.zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in os.listdir(shp_dir):
                zf.write(os.path.join(shp_dir, f), f)
        return FileResponse(zip_path, media_type="application/zip", filename=f"batch_merged_shapefile.zip")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/export-batch-individual")
async def export_batch_individual(entry_ids: List[str]):
    """Exporte chaque fichier séparément dans un ZIP."""
    zip_path = os.path.join("exports", f"batch_individual_{uuid.uuid4().hex[:8]}.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for eid in entry_ids:
            filepath = os.path.join("exports", f"{eid}_polygon.geojson")
            if os.path.exists(filepath):
                # Trouver le nom original
                entry = storage.get_entry(eid)
                fname = entry["filename"].replace(".gpx", ".geojson") if entry else f"{eid}.geojson"
                zf.write(filepath, fname)
    if os.path.getsize(zip_path) == 0:
        os.remove(zip_path)
        raise HTTPException(status_code=404, detail="Aucun export trouvé")
    return FileResponse(zip_path, media_type="application/zip", filename="exports_individuels.zip")


# ==========================================================
# RAPPORTS PDF
# ==========================================================
@router.get("/report/{entry_id}")
async def generate_pdf_report(entry_id: str):
    """Rapport PDF pour un seul fichier."""
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


@router.post("/report-batch")
async def generate_batch_pdf_report(entry_ids: List[str]):
    """Rapport PDF global pour tout un batch."""
    all_results = []
    
    for eid in entry_ids:
        upload_files = [f for f in os.listdir("uploads") if f.startswith(eid) and f.endswith(".gpx")]
        if not upload_files:
            continue
        with open(os.path.join("uploads", upload_files[0]), "r", encoding="utf-8") as f:
            content = f.read()
        result = processor.process(content)
        entry = storage.get_entry(eid)
        result["filename"] = entry["filename"] if entry else upload_files[0]
        result["id"] = eid
        all_results.append(result)
    
    if not all_results:
        raise HTTPException(status_code=404, detail="Aucun résultat trouvé")
    
    try:
        pdf_path = generate_batch_report(all_results, f"rapport_batch_{uuid.uuid4().hex[:8]}.pdf")
        return FileResponse(pdf_path, media_type="application/pdf", filename="rapport_batch.pdf")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
