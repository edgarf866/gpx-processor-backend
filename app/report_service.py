"""
============================================================
SERVICE DE GÉNÉRATION DE RAPPORTS PDF
============================================================
- generate_report() : rapport pour 1 fichier
- generate_batch_report() : rapport global pour N fichiers
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

PRIMARY = HexColor("#1a5632")
SECONDARY = HexColor("#2d8a4e")
ACCENT = HexColor("#e8f5e9")
DANGER = HexColor("#d32f2f")
WARNING = HexColor("#f57c00")
SUCCESS = HexColor("#2e7d32")
TEXT_DARK = HexColor("#212121")
TEXT_LIGHT = HexColor("#757575")
WHITE = HexColor("#ffffff")


def _get_styles():
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle("CustomTitle", parent=styles["Title"],
        fontSize=22, textColor=PRIMARY, spaceAfter=6*mm, alignment=TA_CENTER)
    
    subtitle_style = ParagraphStyle("CustomSubtitle", parent=styles["Normal"],
        fontSize=10, textColor=TEXT_LIGHT, alignment=TA_CENTER, spaceAfter=10*mm)
    
    heading_style = ParagraphStyle("CustomHeading", parent=styles["Heading2"],
        fontSize=14, textColor=PRIMARY, spaceBefore=8*mm, spaceAfter=4*mm,
        borderWidth=1, borderColor=PRIMARY, borderPadding=4)
    
    body_style = ParagraphStyle("CustomBody", parent=styles["Normal"],
        fontSize=10, textColor=TEXT_DARK, spaceAfter=3*mm, leading=14)
    
    return styles, title_style, subtitle_style, heading_style, body_style


def generate_report(processing_result: dict, filename: str = None) -> str:
    """Rapport PDF pour un seul fichier GPX."""
    if filename is None:
        filename = f"rapport_gpx_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    
    filepath = os.path.join("reports", filename)
    doc = SimpleDocTemplate(filepath, pagesize=A4,
        rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
    
    styles, title_style, subtitle_style, heading_style, body_style = _get_styles()
    elements = []
    
    # En-tête
    elements.append(Paragraph("Rapport de Traitement GPX", title_style))
    elements.append(Paragraph(
        f"Genere le {datetime.now().strftime('%d/%m/%Y a %H:%M:%S')}", subtitle_style))
    elements.append(HRFlowable(width="100%", thickness=2, color=PRIMARY, spaceAfter=8*mm))
    
    # Validation
    validation = processing_result.get("validation", {})
    elements.append(Paragraph("1. Validation du fichier GPX", heading_style))
    
    status = "VALIDE" if validation.get("is_valid") else "INVALIDE"
    val_data = [
        ["Statut", status],
        ["Points GPS detectes", str(validation.get("total_points", 0))],
    ]
    val_table = Table(val_data, colWidths=[6*cm, 10*cm])
    val_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), ACCENT),
        ("TEXTCOLOR", (0, 0), (0, -1), PRIMARY),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("PADDING", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, TEXT_LIGHT),
    ]))
    elements.append(val_table)
    elements.append(Spacer(1, 4*mm))
    
    for err in validation.get("errors", []):
        elements.append(Paragraph(f"  Erreur: {err}", body_style))
    for warn in validation.get("warnings", []):
        elements.append(Paragraph(f"  Avertissement: {warn}", body_style))
    
    # Corrections
    corrections = processing_result.get("corrections")
    if corrections:
        elements.append(Paragraph("2. Corrections geometriques", heading_style))
        total = sum([
            corrections.get("artifacts_removed", 0),
            corrections.get("duplicate_vertices_removed", 0),
            corrections.get("spikes_removed", 0),
            corrections.get("self_intersections_fixed", 0),
            corrections.get("invalid_geometries_fixed", 0),
        ])
        corr_data = [
            ["Type de correction", "Nombre"],
            ["Artefacts supprimes", str(corrections.get("artifacts_removed", 0))],
            ["Vertices en double", str(corrections.get("duplicate_vertices_removed", 0))],
            ["Spikes corriges", str(corrections.get("spikes_removed", 0))],
            ["Auto-intersections", str(corrections.get("self_intersections_fixed", 0))],
            ["Geometries reparees", str(corrections.get("invalid_geometries_fixed", 0))],
            ["TOTAL", str(total)],
        ]
        corr_table = Table(corr_data, colWidths=[10*cm, 6*cm])
        corr_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), PRIMARY), ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("BACKGROUND", (0, -1), (-1, -1), ACCENT),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 10), ("PADDING", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, TEXT_LIGHT),
            ("ALIGN", (1, 0), (1, -1), "CENTER"),
        ]))
        elements.append(corr_table)
    
    # Superficie
    area = processing_result.get("area")
    if area:
        elements.append(Paragraph("3. Calcul de superficie", heading_style))
        area_data = [
            ["Mesure", "Valeur"],
            ["Surface", f"{area['area_hectares']} hectares"],
            ["Surface (m2)", f"{area['area_sq_meters']:,.2f} m2"],
            ["Surface (km2)", f"{area['area_sq_km']} km2"],
            ["Perimetre", f"{area['perimeter_meters']:,.2f} metres"],
            ["Projection", area["projection_used"]],
        ]
        area_table = Table(area_data, colWidths=[8*cm, 8*cm])
        area_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), PRIMARY), ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 10), ("PADDING", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, TEXT_LIGHT),
            ("ALIGN", (1, 1), (1, -1), "RIGHT"),
        ]))
        elements.append(area_table)
    
    # Footer
    elements.append(Spacer(1, 15*mm))
    elements.append(HRFlowable(width="100%", thickness=1, color=TEXT_LIGHT, spaceAfter=4*mm))
    footer_style = ParagraphStyle("Footer", parent=styles["Normal"],
        fontSize=8, textColor=TEXT_LIGHT, alignment=TA_CENTER)
    elements.append(Paragraph("GPX Processor v1.0 - MEDEV GROUP", footer_style))
    
    doc.build(elements)
    return filepath


def generate_batch_report(all_results: list, filename: str = None) -> str:
    """
    Rapport PDF GLOBAL pour un batch de fichiers GPX.
    Contient un résumé + détail de chaque fichier.
    """
    if filename is None:
        filename = f"rapport_batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    
    filepath = os.path.join("reports", filename)
    doc = SimpleDocTemplate(filepath, pagesize=A4,
        rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
    
    styles, title_style, subtitle_style, heading_style, body_style = _get_styles()
    elements = []
    
    # ===== PAGE 1 : RÉSUMÉ GLOBAL =====
    elements.append(Paragraph("Rapport Batch - Traitement GPX", title_style))
    elements.append(Paragraph(
        f"{len(all_results)} fichiers traites - {datetime.now().strftime('%d/%m/%Y a %H:%M:%S')}",
        subtitle_style))
    elements.append(HRFlowable(width="100%", thickness=2, color=PRIMARY, spaceAfter=8*mm))
    
    elements.append(Paragraph("Resume global", heading_style))
    
    # Stats globales
    total_area = sum(r["area"]["area_hectares"] for r in all_results if r.get("area"))
    total_points = sum(r["validation"].get("total_points", 0) for r in all_results if r.get("validation"))
    total_corrections = 0
    for r in all_results:
        c = r.get("corrections", {})
        if c:
            total_corrections += sum([
                c.get("artifacts_removed", 0), c.get("duplicate_vertices_removed", 0),
                c.get("spikes_removed", 0), c.get("self_intersections_fixed", 0),
                c.get("invalid_geometries_fixed", 0),
            ])
    
    summary_data = [
        ["Indicateur", "Valeur"],
        ["Nombre de fichiers", str(len(all_results))],
        ["Points GPS total", str(total_points)],
        ["Superficie totale", f"{total_area:.4f} hectares"],
        ["Corrections totales", str(total_corrections)],
    ]
    summary_table = Table(summary_data, colWidths=[8*cm, 8*cm])
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PRIMARY), ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10), ("PADDING", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, TEXT_LIGHT),
        ("ALIGN", (1, 1), (1, -1), "RIGHT"),
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 6*mm))
    
    # Tableau détaillé de chaque fichier
    elements.append(Paragraph("Detail par fichier", heading_style))
    
    detail_data = [["#", "Fichier", "Points", "Surface (ha)", "Corrections"]]
    for i, r in enumerate(all_results):
        fname = r.get("filename", "?")
        if len(fname) > 35:
            fname = fname[:32] + "..."
        pts = str(r["validation"].get("total_points", 0)) if r.get("validation") else "0"
        area_ha = str(r["area"]["area_hectares"]) if r.get("area") else "-"
        corr = "0"
        if r.get("corrections"):
            c = r["corrections"]
            corr = str(sum([
                c.get("artifacts_removed", 0), c.get("duplicate_vertices_removed", 0),
                c.get("spikes_removed", 0), c.get("self_intersections_fixed", 0),
                c.get("invalid_geometries_fixed", 0),
            ]))
        detail_data.append([str(i+1), Paragraph(fname, body_style), pts, area_ha, corr])
    
    detail_table = Table(detail_data, colWidths=[1.2*cm, 7.5*cm, 2*cm, 3*cm, 2.5*cm])
    detail_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PRIMARY), ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9), ("PADDING", (0, 0), (-1, -1), 6),
        ("GRID", (0, 0), (-1, -1), 0.5, TEXT_LIGHT),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (2, 0), (-1, -1), "CENTER"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, ACCENT]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    elements.append(detail_table)
    
    # ===== PAGES SUIVANTES : DÉTAIL PAR FICHIER =====
    for i, r in enumerate(all_results):
        elements.append(PageBreak())
        elements.append(Paragraph(
            f"Fichier {i+1}/{len(all_results)} : {r.get('filename', '?')}", heading_style))
        
        # Validation
        validation = r.get("validation", {})
        status = "VALIDE" if validation.get("is_valid") else "INVALIDE"
        elements.append(Paragraph(f"Statut : {status} | Points : {validation.get('total_points', 0)}", body_style))
        
        # Corrections
        if r.get("corrections"):
            c = r["corrections"]
            corr_text = (
                f"Artefacts: {c.get('artifacts_removed', 0)} | "
                f"Doublons: {c.get('duplicate_vertices_removed', 0)} | "
                f"Spikes: {c.get('spikes_removed', 0)} | "
                f"Intersections: {c.get('self_intersections_fixed', 0)} | "
                f"Geometries: {c.get('invalid_geometries_fixed', 0)}"
            )
            elements.append(Paragraph(f"Corrections : {corr_text}", body_style))
            
            for d in c.get("details", []):
                elements.append(Paragraph(f"  > {d}", body_style))
        
        # Superficie
        if r.get("area"):
            a = r["area"]
            elements.append(Paragraph(
                f"Surface : {a['area_hectares']} ha ({a['area_sq_meters']:,.2f} m2) | "
                f"Perimetre : {a['perimeter_meters']:,.2f} m", body_style))
        
        elements.append(Spacer(1, 4*mm))
    
    # Footer
    elements.append(Spacer(1, 10*mm))
    elements.append(HRFlowable(width="100%", thickness=1, color=TEXT_LIGHT, spaceAfter=4*mm))
    footer_style = ParagraphStyle("Footer", parent=styles["Normal"],
        fontSize=8, textColor=TEXT_LIGHT, alignment=TA_CENTER)
    elements.append(Paragraph("GPX Processor v1.0 - MEDEV GROUP", footer_style))
    
    doc.build(elements)
    return filepath
