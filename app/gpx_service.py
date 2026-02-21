"""
============================================================
SERVICE DE TRAITEMENT GPX - LE CŒUR DU PROJET
============================================================
Ce fichier contient toute la logique métier :
  1. Parsing du fichier GPX (lire le XML)
  2. Validation (vérifier que le GPX est bon)
  3. Transformation (points → lignes → polygones)
  4. Corrections géométriques
  5. Calcul de superficie

CONCEPTS PYTHON vs PHP :
- Les fonctions sont définies avec "def"
- Les types sont optionnels mais recommandés (type hints)
- "self" = "$this" en PHP
- Les classes n'ont pas besoin de getters/setters
- Les listes sont comme les arrays PHP : []
- Les dictionnaires sont comme les arrays associatifs : {}
============================================================
"""

import xml.etree.ElementTree as ET
import numpy as np
from shapely.geometry import Point, LineString, Polygon, mapping, MultiPoint
from shapely.validation import make_valid, explain_validity
from shapely.ops import polygonize, unary_union
import pyproj
from pyproj import Transformer
from typing import Optional
import math
import json


class GPXProcessor:
    """
    Classe principale de traitement GPX.
    
    En PHP, tu aurais une classe similaire avec des méthodes.
    La différence : en Python, __init__ = le constructeur (__construct en PHP).
    """
    
    # --- Projection UTM Zone 30N (Côte d'Ivoire) ---
    # WGS84 = le système GPS standard (lat/lon en degrés)
    # UTM 30N = projection en mètres, adaptée à la Côte d'Ivoire
    # On DOIT projeter pour calculer des surfaces précises en m²
    WGS84 = "EPSG:4326"
    UTM_30N = "EPSG:32630"  # Zone UTM couvrant la Côte d'Ivoire
    
    def __init__(self):
        """
        Constructeur - initialise le transformateur de coordonnées.
        Equivalent de __construct() en PHP.
        """
        # Crée un objet qui convertit les coordonnées WGS84 ↔ UTM
        self.transformer_to_utm = Transformer.from_crs(
            self.WGS84, self.UTM_30N, always_xy=True
        )
        self.transformer_to_wgs = Transformer.from_crs(
            self.UTM_30N, self.WGS84, always_xy=True
        )
    
    # ==========================================================
    # ÉTAPE 1 : PARSING DU FICHIER GPX
    # ==========================================================
    def parse_gpx(self, file_content: str) -> dict:
        """
        Lit un fichier GPX et extrait les points GPS.
        
        Un fichier GPX est du XML avec des balises <trkpt> (track points)
        ou <wpt> (waypoints) contenant lat/lon.
        
        Retourne un dict avec les points et les métadonnées.
        
        En PHP, tu utiliserais SimpleXML ou DOMDocument.
        En Python, on utilise ElementTree (ET).
        """
        result = {
            "points": [],
            "metadata": {},
            "errors": [],
            "warnings": []
        }
        
        try:
            # Parser le XML
            root = ET.fromstring(file_content)
            
            # Le namespace GPX (les fichiers GPX utilisent un namespace XML)
            # C'est comme un préfixe pour éviter les conflits de noms de balises
            ns = {"gpx": "http://www.topografix.com/GPX/1/1"}
            
            # Essayer aussi sans namespace (certains GPX mal formés)
            if root.tag.startswith("{"):
                ns_uri = root.tag.split("}")[0] + "}"
                ns = {"gpx": ns_uri.strip("{}")}
            
            # --- Extraire les métadonnées ---
            metadata = root.find("gpx:metadata", ns)
            if metadata is not None:
                name = metadata.find("gpx:name", ns)
                if name is not None:
                    result["metadata"]["name"] = name.text
            
            # --- Extraire les track points (trkpt) ---
            # Structure GPX : <trk> → <trkseg> → <trkpt lat="..." lon="...">
            points = []
            
            for trkpt in root.iter("{%s}trkpt" % ns.get("gpx", "")):
                lat = trkpt.get("lat")
                lon = trkpt.get("lon")
                
                if lat is not None and lon is not None:
                    try:
                        lat_f = float(lat)
                        lon_f = float(lon)
                        
                        # Extraire l'élévation si disponible
                        ele = trkpt.find("{%s}ele" % ns.get("gpx", ""))
                        elevation = float(ele.text) if ele is not None and ele.text else None
                        
                        # Extraire le timestamp si disponible
                        time = trkpt.find("{%s}time" % ns.get("gpx", ""))
                        timestamp = time.text if time is not None else None
                        
                        points.append({
                            "lat": lat_f,
                            "lon": lon_f,
                            "ele": elevation,
                            "time": timestamp
                        })
                    except ValueError:
                        result["warnings"].append(
                            f"Point ignoré : coordonnées invalides ({lat}, {lon})"
                        )
            
            # --- Si pas de trkpt, essayer les waypoints (wpt) ---
            if not points:
                for wpt in root.iter("{%s}wpt" % ns.get("gpx", "")):
                    lat = wpt.get("lat")
                    lon = wpt.get("lon")
                    if lat and lon:
                        try:
                            points.append({
                                "lat": float(lat),
                                "lon": float(lon),
                                "ele": None,
                                "time": None
                            })
                        except ValueError:
                            pass
            
            # --- Si pas de wpt non plus, essayer les route points (rtept) ---
            if not points:
                for rtept in root.iter("{%s}rtept" % ns.get("gpx", "")):
                    lat = rtept.get("lat")
                    lon = rtept.get("lon")
                    if lat and lon:
                        try:
                            points.append({
                                "lat": float(lat),
                                "lon": float(lon),
                                "ele": None,
                                "time": None
                            })
                        except ValueError:
                            pass
            
            result["points"] = points
            
            if not points:
                result["errors"].append("Aucun point GPS trouvé dans le fichier")
                
        except ET.ParseError as e:
            result["errors"].append(f"Erreur de parsing XML : {str(e)}")
        except Exception as e:
            result["errors"].append(f"Erreur inattendue : {str(e)}")
        
        return result

    # ==========================================================
    # ÉTAPE 2 : VALIDATION DU GPX
    # ==========================================================
    def validate(self, parsed_data: dict) -> dict:
        """
        Valide les données GPS extraites.
        
        Vérifie :
        - Qu'il y a assez de points (minimum 3 pour un polygone)
        - Que les coordonnées sont dans des plages valides
        - Que les points ne sont pas tous identiques
        - Que la trace n'est pas trop petite ou trop grande
        """
        errors = list(parsed_data.get("errors", []))
        warnings = list(parsed_data.get("warnings", []))
        points = parsed_data.get("points", [])
        
        # --- Vérification du nombre de points ---
        if len(points) == 0:
            errors.append("Le fichier ne contient aucun point GPS")
            return {"is_valid": False, "errors": errors, "warnings": warnings, "total_points": 0}
        
        if len(points) < 3:
            errors.append(
                f"Pas assez de points ({len(points)}). "
                f"Il faut minimum 3 points pour créer un polygone."
            )
        
        # --- Vérification des coordonnées ---
        invalid_coords = 0
        for i, p in enumerate(points):
            # Latitude : -90 à +90 | Longitude : -180 à +180
            if not (-90 <= p["lat"] <= 90):
                invalid_coords += 1
                warnings.append(f"Point {i+1} : latitude hors limites ({p['lat']})")
            if not (-180 <= p["lon"] <= 180):
                invalid_coords += 1
                warnings.append(f"Point {i+1} : longitude hors limites ({p['lon']})")
        
        if invalid_coords > 0:
            errors.append(f"{invalid_coords} coordonnée(s) hors limites détectée(s)")
        
        # --- Vérifier que les points ne sont pas tous identiques ---
        if len(points) >= 2:
            unique_points = set((p["lat"], p["lon"]) for p in points)
            if len(unique_points) == 1:
                errors.append("Tous les points ont les mêmes coordonnées")
            elif len(unique_points) < 3:
                warnings.append(
                    f"Seulement {len(unique_points)} points uniques sur {len(points)}"
                )
        
        # --- Vérifier la zone couverte (pas trop grande = erreur probable) ---
        if len(points) >= 2:
            lats = [p["lat"] for p in points]
            lons = [p["lon"] for p in points]
            lat_range = max(lats) - min(lats)
            lon_range = max(lons) - min(lons)
            
            # Si la zone couvre plus de 1 degré (~111km), c'est suspect
            if lat_range > 1 or lon_range > 1:
                warnings.append(
                    f"Zone très étendue ({lat_range:.3f}° lat × {lon_range:.3f}° lon). "
                    f"Vérifiez que le fichier est correct."
                )
        
        is_valid = len(errors) == 0
        
        return {
            "is_valid": is_valid,
            "errors": errors,
            "warnings": warnings,
            "total_points": len(points)
        }

    # ==========================================================
    # ÉTAPE 3 : TRANSFORMATION Points → Lignes → Polygones
    # ==========================================================
    def points_to_linestring(self, points: list) -> Optional[LineString]:
        """
        Convertit une liste de points GPS en LineString (ligne).
        
        Shapely LineString = une ligne qui connecte des points dans l'ordre.
        C'est la première étape avant de créer un polygone.
        
        Note : Shapely utilise (lon, lat) et non (lat, lon) !
        C'est le standard (x, y) = (longitude, latitude).
        """
        if len(points) < 2:
            return None
        
        # Convertir les points en tuples (lon, lat) pour Shapely
        coords = [(p["lon"], p["lat"]) for p in points]
        
        try:
            line = LineString(coords)
            return line
        except Exception:
            return None
    
    def linestring_to_polygon(self, line: LineString) -> Optional[Polygon]:
        """
        Convertit une LineString en Polygon.
        
        Pour créer un polygone, il faut que la ligne soit "fermée"
        (le dernier point = le premier point).
        Si ce n'est pas le cas, on ferme automatiquement.
        """
        if line is None or len(line.coords) < 3:
            return None
        
        coords = list(line.coords)
        
        # Fermer le polygone si nécessaire
        # (le premier et dernier point doivent être identiques)
        if coords[0] != coords[-1]:
            coords.append(coords[0])
        
        try:
            polygon = Polygon(coords)
            return polygon
        except Exception:
            return None

    # ==========================================================
    # ÉTAPE 4 : CORRECTIONS GÉOMÉTRIQUES
    # ==========================================================
    def correct_geometry(self, polygon: Polygon, points: list) -> dict:
        """
        Applique toutes les corrections géométriques.
        
        C'est LE morceau le plus important du projet.
        On corrige dans l'ordre :
          1. Suppression des artefacts (points aberrants)
          2. Suppression des vertices en double
          3. Correction des spikes (pics)
          4. Correction des auto-intersections
          5. Validation finale de la géométrie
        
        Retourne le polygone corrigé + détails des corrections.
        """
        corrections = {
            "artifacts_removed": 0,
            "self_intersections_fixed": 0,
            "invalid_geometries_fixed": 0,
            "duplicate_vertices_removed": 0,
            "spikes_removed": 0,
            "details": []
        }
        
        coords = list(polygon.exterior.coords)
        
        # --- 4.1 Suppression des artefacts ---
        coords, n_artifacts = self._remove_artifacts(coords)
        corrections["artifacts_removed"] = n_artifacts
        if n_artifacts > 0:
            corrections["details"].append(
                f"{n_artifacts} artefact(s) supprimé(s) (points aberrants)"
            )
        
        # --- 4.2 Suppression des vertices en double ---
        coords, n_dupes = self._remove_duplicate_vertices(coords)
        corrections["duplicate_vertices_removed"] = n_dupes
        if n_dupes > 0:
            corrections["details"].append(
                f"{n_dupes} vertex en double supprimé(s)"
            )
        
        # --- 4.3 Correction des spikes (pics) ---
        coords, n_spikes = self._remove_spikes(coords)
        corrections["spikes_removed"] = n_spikes
        if n_spikes > 0:
            corrections["details"].append(
                f"{n_spikes} spike(s) corrigé(s)"
            )
        
        # --- Recréer le polygone avec les coords corrigées ---
        if len(coords) < 4:  # Minimum 4 points pour un polygone fermé
            corrections["details"].append(
                "ERREUR : Pas assez de points après corrections"
            )
            return {
                "corrected_polygon": polygon,  # On garde l'original
                "corrections": corrections
            }
        
        # Fermer le polygone
        if coords[0] != coords[-1]:
            coords.append(coords[0])
        
        try:
            corrected = Polygon(coords)
        except Exception:
            corrected = polygon
        
        # --- 4.4 Correction des auto-intersections ---
        if not corrected.is_valid:
            reason = explain_validity(corrected)
            corrections["details"].append(
                f"Géométrie invalide détectée : {reason}"
            )
            
            # make_valid() de Shapely corrige automatiquement
            # les auto-intersections et autres problèmes
            corrected = make_valid(corrected)
            
            # make_valid peut retourner un MultiPolygon ou une GeometryCollection
            # On prend le plus grand polygone
            if corrected.geom_type == "MultiPolygon":
                corrected = max(corrected.geoms, key=lambda g: g.area)
                corrections["self_intersections_fixed"] += 1
                corrections["details"].append(
                    "Auto-intersection corrigée (polygone principal conservé)"
                )
            elif corrected.geom_type == "GeometryCollection":
                polygons = [g for g in corrected.geoms if g.geom_type == "Polygon"]
                if polygons:
                    corrected = max(polygons, key=lambda g: g.area)
                else:
                    corrected = polygon  # Fallback à l'original
                corrections["self_intersections_fixed"] += 1
            elif corrected.geom_type == "Polygon":
                corrections["invalid_geometries_fixed"] += 1
                corrections["details"].append("Géométrie réparée avec succès")
        
        # --- 4.5 Vérification finale ---
        if corrected.is_valid:
            corrections["details"].append("✓ Géométrie finale valide")
        else:
            corrections["details"].append(
                f"⚠ Géométrie encore invalide : {explain_validity(corrected)}"
            )
        
        return {
            "corrected_polygon": corrected,
            "corrections": corrections
        }
    
    def _remove_artifacts(self, coords: list, threshold_factor: float = 3.0) -> tuple:
        """
        Supprime les points aberrants (artefacts).
        
        Algorithme : On calcule la distance moyenne entre points consécutifs.
        Si un point est à plus de [threshold_factor] fois cette distance
        de ses voisins, c'est probablement un artefact GPS.
        
        Imagine : tu as des points tous les 5 mètres, et soudain un point
        à 500m → c'est un artefact du GPS.
        """
        if len(coords) < 4:
            return coords, 0
        
        # Calculer les distances entre points consécutifs
        distances = []
        for i in range(len(coords) - 1):
            d = self._distance(coords[i], coords[i + 1])
            distances.append(d)
        
        if not distances:
            return coords, 0
            
        # Distance médiane (plus robuste que la moyenne)
        median_dist = float(np.median(distances))
        
        if median_dist == 0:
            return coords, 0
        
        threshold = median_dist * threshold_factor
        
        # Filtrer les points aberrants
        clean_coords = [coords[0]]  # Garder le premier point
        removed = 0
        
        for i in range(1, len(coords) - 1):
            dist_prev = self._distance(coords[i - 1], coords[i])
            dist_next = self._distance(coords[i], coords[i + 1])
            
            # Si le point est loin des DEUX voisins, c'est un artefact
            if dist_prev > threshold and dist_next > threshold:
                removed += 1
            else:
                clean_coords.append(coords[i])
        
        clean_coords.append(coords[-1])  # Garder le dernier point
        
        return clean_coords, removed
    
    def _remove_duplicate_vertices(self, coords: list, tolerance: float = 1e-8) -> tuple:
        """
        Supprime les vertices en double (points identiques consécutifs).
        
        tolerance = distance minimale entre deux points pour les considérer
        comme différents. 1e-8 degrés ≈ ~1mm sur le terrain.
        """
        if len(coords) < 2:
            return coords, 0
        
        clean = [coords[0]]
        removed = 0
        
        for i in range(1, len(coords)):
            dist = self._distance(coords[i - 1], coords[i])
            if dist > tolerance:
                clean.append(coords[i])
            else:
                removed += 1
        
        return clean, removed
    
    def _remove_spikes(self, coords: list, min_angle: float = 5.0) -> tuple:
        """
        Supprime les spikes (pics aigus) dans le tracé.
        
        Un spike = un angle très aigu formé par 3 points consécutifs.
        Si l'angle est inférieur à min_angle degrés, le point central
        est probablement un artefact.
        
        Imagine un tracé lisse avec soudain un point qui "pique" très loin
        puis revient → c'est un spike.
        """
        if len(coords) < 4:
            return coords, 0
        
        clean = [coords[0]]
        removed = 0
        
        for i in range(1, len(coords) - 1):
            angle = self._angle_between(coords[i - 1], coords[i], coords[i + 1])
            
            if angle is not None and angle < min_angle:
                removed += 1  # On enlève ce point (spike)
            else:
                clean.append(coords[i])
        
        clean.append(coords[-1])
        return clean, removed
    
    def _distance(self, p1: tuple, p2: tuple) -> float:
        """Distance euclidienne entre deux points (en degrés)."""
        return math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)
    
    def _angle_between(self, p1: tuple, p2: tuple, p3: tuple) -> Optional[float]:
        """
        Calcule l'angle au point p2 formé par le segment p1-p2-p3.
        Retourne l'angle en degrés.
        """
        # Vecteurs
        v1 = (p1[0] - p2[0], p1[1] - p2[1])
        v2 = (p3[0] - p2[0], p3[1] - p2[1])
        
        # Longueurs
        len1 = math.sqrt(v1[0]**2 + v1[1]**2)
        len2 = math.sqrt(v2[0]**2 + v2[1]**2)
        
        if len1 == 0 or len2 == 0:
            return None
        
        # Produit scalaire
        dot = v1[0] * v2[0] + v1[1] * v2[1]
        
        # Cosinus de l'angle
        cos_angle = dot / (len1 * len2)
        cos_angle = max(-1, min(1, cos_angle))  # Clamp pour éviter erreurs float
        
        return math.degrees(math.acos(cos_angle))

    # ==========================================================
    # ÉTAPE 5 : CALCUL DE SUPERFICIE
    # ==========================================================
    def calculate_area(self, polygon: Polygon) -> dict:
        """
        Calcule la superficie du polygone.
        
        IMPORTANT : On ne peut PAS calculer la surface directement en WGS84
        (lat/lon en degrés) car 1° de longitude ≠ 1° de latitude en distance.
        
        Solution : On projette en UTM (mètres) → on calcule → on convertit.
        
        UTM Zone 30N couvre la Côte d'Ivoire.
        """
        # Reprojeter les coordonnées en UTM (mètres)
        exterior_coords = list(polygon.exterior.coords)
        
        projected_coords = []
        for lon, lat in exterior_coords:
            x, y = self.transformer_to_utm.transform(lon, lat)
            projected_coords.append((x, y))
        
        # Créer le polygone projeté
        projected_polygon = Polygon(projected_coords)
        
        # Calculer surface et périmètre (en mètres)
        area_m2 = projected_polygon.area
        perimeter_m = projected_polygon.length
        
        return {
            "area_sq_meters": round(area_m2, 2),
            "area_hectares": round(area_m2 / 10000, 4),
            "area_sq_km": round(area_m2 / 1000000, 6),
            "perimeter_meters": round(perimeter_m, 2),
            "projection_used": self.UTM_30N
        }

    # ==========================================================
    # UTILITAIRES : Conversion en GeoJSON
    # ==========================================================
    def to_geojson(self, geometry, properties: dict = None) -> dict:
        """
        Convertit une géométrie Shapely en GeoJSON.
        
        GeoJSON = le format standard pour envoyer des données géo au frontend.
        Leaflet/Mapbox/etc. comprennent tous le GeoJSON nativement.
        """
        feature = {
            "type": "Feature",
            "geometry": mapping(geometry),
            "properties": properties or {}
        }
        
        return {
            "type": "FeatureCollection",
            "features": [feature]
        }
    
    def points_to_geojson(self, points: list) -> dict:
        """Convertit une liste de points en GeoJSON MultiPoint."""
        coordinates = [[p["lon"], p["lat"]] for p in points]
        
        return {
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "geometry": {
                    "type": "MultiPoint",
                    "coordinates": coordinates
                },
                "properties": {"type": "original_points", "count": len(points)}
            }]
        }
    
    # ==========================================================
    # PIPELINE COMPLET
    # ==========================================================
    def process(self, file_content: str) -> dict:
        """
        Pipeline complet de traitement.
        
        Enchaîne toutes les étapes et retourne le résultat complet.
        C'est cette méthode qu'on appelle depuis la route API.
        """
        result = {
            "validation": None,
            "corrections": None,
            "area": None,
            "original_geojson": None,
            "corrected_geojson": None,
            "polygon_geojson": None,
            "line_geojson": None,
        }
        
        # 1. Parser le GPX
        parsed = self.parse_gpx(file_content)
        
        # 2. Valider
        validation = self.validate(parsed)
        result["validation"] = validation
        
        if not validation["is_valid"]:
            return result
        
        points = parsed["points"]
        
        # GeoJSON des points originaux
        result["original_geojson"] = self.points_to_geojson(points)
        
        # 3. Points → LineString
        line = self.points_to_linestring(points)
        if line is None:
            validation["errors"].append("Impossible de créer une ligne à partir des points")
            validation["is_valid"] = False
            return result
        
        result["line_geojson"] = self.to_geojson(line, {"type": "line"})
        
        # 4. LineString → Polygon
        polygon = self.linestring_to_polygon(line)
        if polygon is None:
            validation["errors"].append("Impossible de créer un polygone à partir de la ligne")
            validation["is_valid"] = False
            return result
        
        # 5. Corrections géométriques
        correction_result = self.correct_geometry(polygon, points)
        corrected_polygon = correction_result["corrected_polygon"]
        result["corrections"] = correction_result["corrections"]
        
        # GeoJSON du polygone corrigé
        result["corrected_geojson"] = self.to_geojson(
            corrected_polygon,
            {"type": "corrected_polygon"}
        )
        result["polygon_geojson"] = result["corrected_geojson"]
        
        # 6. Calcul de superficie
        if corrected_polygon.is_valid and not corrected_polygon.is_empty:
            result["area"] = self.calculate_area(corrected_polygon)
        
        return result
