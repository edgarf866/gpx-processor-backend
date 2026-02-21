"""
============================================================
SERVICE DE GÉNÉRATION DE RAPPORTS PDF
============================================================
Utilise ReportLab pour créer des rapports PDF professionnels
avec les résultats du traitement GPX.

ReportLab fonctionne comme un "canvas" :
- Tu positionnes des éléments (texte, tableaux, images)
- Tu "dessines" le PDF page par page
- C'est similaire à TCPDF/FPDF en PHP
============================================================
"""

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm, mm
from reportlab.lib.colors import HexColor
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, 
    HRFlowable, PageBreak
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from datetime import datetime
import os


# --- Couleurs du thème ---
PRIMARY = HexColor("#1a5632")      # Vert foncé
SECONDARY = HexColor("#2d8a4e")    # Vert moyen
ACCENT = HexColor("#e8f5e9")       # Vert très clair (fond)
DANGER = HexColor("#d32f2f")       # Rouge
WARNING = HexColor("#f57c00")      # Orange
SUCCESS = HexColor("#2e7d32")      # Vert succès
TEXT_DARK = HexColor("#212121")
TEXT_LIGHT = HexColor("#757575")
WHITE = HexColor("#ffffff")


def generate_report(processing_result: dict, filename: str = None) -> str:
    """
    Génère un rapport PDF complet du traitement GPX.
    
    Paramètres :
    - processing_result : le résultat du GPXProcessor.process()
    - filename : nom du fichier de sortie (optionnel)
    
    Retourne le chemin du fichier PDF généré.
    """
    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"rapport_gpx_{timestamp}.pdf"
    
    filepath = os.path.join("reports", filename)
    
    # --- Créer le document PDF ---
    doc = SimpleDocTemplate(
        filepath,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm
    )
    
    # --- Styles de texte ---
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Title"],
        fontSize=22,
        textColor=PRIMARY,
        spaceAfter=6 * mm,
        alignment=TA_CENTER
    )
    
    subtitle_style = ParagraphStyle(
        "CustomSubtitle",
        parent=styles["Normal"],
        fontSize=10,
        textColor=TEXT_LIGHT,
        alignment=TA_CENTER,
        spaceAfter=10 * mm
    )
    
    heading_style = ParagraphStyle(
        "CustomHeading",
        parent=styles["Heading2"],
        fontSize=14,
        textColor=PRIMARY,
        spaceBefore=8 * mm,
        spaceAfter=4 * mm,
        borderWidth=1,
        borderColor=PRIMARY,
        borderPadding=4
    )
    
    body_style = ParagraphStyle(
        "CustomBody",
        parent=styles["Normal"],
        fontSize=10,
        textColor=TEXT_DARK,
        spaceAfter=3 * mm,
        leading=14
    )
    
    # --- Construire le contenu ---
    elements = []
    
    # ===== EN-TÊTE =====
    elements.append(Paragraph("📍 Rapport de Traitement GPX", title_style))
    elements.append(Paragraph(
        f"Généré le {datetime.now().strftime('%d/%m/%Y à %H:%M:%S')}",
        subtitle_style
    ))
    elements.append(HRFlowable(
        width="100%", thickness=2, color=PRIMARY, spaceAfter=8 * mm
    ))
    
    # ===== SECTION VALIDATION =====
    validation = processing_result.get("validation", {})
    elements.append(Paragraph("1. Validation du fichier GPX", heading_style))
    
    status = "✅ VALIDE" if validation.get("is_valid") else "❌ INVALIDE"
    status_color = SUCCESS if validation.get("is_valid") else DANGER
    
    val_data = [
        ["Statut", status],
        ["Points GPS détectés", str(validation.get("total_points", 0))],
    ]
    
    val_table = Table(val_data, colWidths=[6 * cm, 10 * cm])
    val_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), ACCENT),
        ("TEXTCOLOR", (0, 0), (0, -1), PRIMARY),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("PADDING", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, TEXT_LIGHT),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    elements.append(val_table)
    elements.append(Spacer(1, 4 * mm))
    
    # Erreurs
    errors = validation.get("errors", [])
    if errors:
        elements.append(Paragraph("Erreurs :", body_style))
        for err in errors:
            elements.append(Paragraph(f"  • {err}", body_style))
    
    # Avertissements
    warnings = validation.get("warnings", [])
    if warnings:
        elements.append(Paragraph("Avertissements :", body_style))
        for warn in warnings:
            elements.append(Paragraph(f"  ⚠ {warn}", body_style))
    
    # ===== SECTION CORRECTIONS =====
    corrections = processing_result.get("corrections")
    if corrections:
        elements.append(Paragraph("2. Corrections géométriques", heading_style))
        
        total = (
            corrections.get("artifacts_removed", 0) +
            corrections.get("duplicate_vertices_removed", 0) +
            corrections.get("spikes_removed", 0) +
            corrections.get("self_intersections_fixed", 0) +
            corrections.get("invalid_geometries_fixed", 0)
        )
        
        corr_data = [
            ["Type de correction", "Nombre"],
            ["Artefacts supprimés", str(corrections.get("artifacts_removed", 0))],
            ["Vertices en double supprimés", str(corrections.get("duplicate_vertices_removed", 0))],
            ["Spikes corrigés", str(corrections.get("spikes_removed", 0))],
            ["Auto-intersections corrigées", str(corrections.get("self_intersections_fixed", 0))],
            ["Géométries invalides réparées", str(corrections.get("invalid_geometries_fixed", 0))],
            ["TOTAL corrections", str(total)],
        ]
        
        corr_table = Table(corr_data, colWidths=[10 * cm, 6 * cm])
        corr_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
            ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("BACKGROUND", (0, -1), (-1, -1), ACCENT),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("PADDING", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, TEXT_LIGHT),
            ("ALIGN", (1, 0), (1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        elements.append(corr_table)
        elements.append(Spacer(1, 4 * mm))
        
        # Détails
        details = corrections.get("details", [])
        if details:
            elements.append(Paragraph("Détails des corrections :", body_style))
            for detail in details:
                elements.append(Paragraph(f"  → {detail}", body_style))
    
    # ===== SECTION SUPERFICIE =====
    area = processing_result.get("area")
    if area:
        elements.append(Paragraph("3. Calcul de superficie", heading_style))
        
        area_data = [
            ["Mesure", "Valeur"],
            ["Surface", f"{area['area_hectares']} hectares"],
            ["Surface (m²)", f"{area['area_sq_meters']:,.2f} m²"],
            ["Surface (km²)", f"{area['area_sq_km']} km²"],
            ["Périmètre", f"{area['perimeter_meters']:,.2f} mètres"],
            ["Projection utilisée", area["projection_used"]],
        ]
        
        area_table = Table(area_data, colWidths=[8 * cm, 8 * cm])
        area_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
            ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("BACKGROUND", (0, 1), (-1, 1), ACCENT),
            ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("PADDING", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, TEXT_LIGHT),
            ("ALIGN", (1, 1), (1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        elements.append(area_table)
    
    # ===== PIED DE PAGE =====
    elements.append(Spacer(1, 15 * mm))
    elements.append(HRFlowable(
        width="100%", thickness=1, color=TEXT_LIGHT, spaceAfter=4 * mm
    ))
    
    footer_style = ParagraphStyle(
        "Footer", parent=styles["Normal"],
        fontSize=8, textColor=TEXT_LIGHT, alignment=TA_CENTER
    )
    elements.append(Paragraph(
        "GPX Processor v1.0 — Rapport généré automatiquement — MEDEV GROUP",
        footer_style
    ))
    
    # --- Générer le PDF ---
    doc.build(elements)
    
    return filepath
