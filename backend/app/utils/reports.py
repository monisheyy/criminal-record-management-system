from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from datetime import datetime
import io


DARK_BLUE = colors.HexColor('#0d1b2a')
ACCENT_BLUE = colors.HexColor('#1e90ff')
ACCENT_RED = colors.HexColor('#e63946')
LIGHT_GRAY = colors.HexColor('#f0f4f8')
MID_GRAY = colors.HexColor('#8899aa')
WHITE = colors.white


def _header_style():
    return ParagraphStyle(
        'HeaderStyle',
        fontName='Helvetica-Bold',
        fontSize=22,
        textColor=WHITE,
        spaceAfter=4,
        alignment=TA_CENTER
    )


def _sub_header_style():
    return ParagraphStyle(
        'SubHeader',
        fontName='Helvetica',
        fontSize=11,
        textColor=MID_GRAY,
        spaceAfter=2,
        alignment=TA_CENTER
    )


def _section_style():
    return ParagraphStyle(
        'Section',
        fontName='Helvetica-Bold',
        fontSize=12,
        textColor=ACCENT_BLUE,
        spaceBefore=12,
        spaceAfter=6,
    )


def _body_style():
    return ParagraphStyle(
        'Body',
        fontName='Helvetica',
        fontSize=10,
        textColor=DARK_BLUE,
        spaceAfter=4,
    )


def _warning_style():
    return ParagraphStyle(
        'Warning',
        fontName='Helvetica-Bold',
        fontSize=11,
        textColor=ACCENT_RED,
        spaceAfter=4,
        alignment=TA_CENTER
    )


def generate_criminal_report(criminal_data: dict, predictions: list = None) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        rightMargin=2*cm, leftMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm
    )
    story = []
    styles = getSampleStyleSheet()

    # Header banner
    header_data = [[
        Paragraph("⚖ AI-CRMS — Criminal Intelligence Report", _header_style()),
    ]]
    header_table = Table(header_data, colWidths=[17*cm])
    header_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), DARK_BLUE),
        ('TOPPADDING', (0, 0), (-1, -1), 14),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 14),
        ('ROUNDEDCORNERS', [6, 6, 6, 6]),
    ]))
    story.append(header_table)
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}  |  CONFIDENTIAL", _sub_header_style()))
    story.append(Spacer(1, 0.4*cm))

    # Risk alert banner
    risk_score = criminal_data.get('risk_score', 0)
    if risk_score >= 75:
        risk_data = [[Paragraph(f"⚠ HIGH RISK — Risk Score: {risk_score:.0f}/100", _warning_style())]]
        risk_table = Table(risk_data, colWidths=[17*cm])
        risk_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#fff0f0')),
            ('BOX', (0, 0), (-1, -1), 2, ACCENT_RED),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        story.append(risk_table)
        story.append(Spacer(1, 0.3*cm))

    # Personal Info
    story.append(Paragraph("Personal Information", _section_style()))
    story.append(HRFlowable(width='100%', color=ACCENT_BLUE, thickness=1))
    story.append(Spacer(1, 0.2*cm))

    personal_data = [
        ['CRN', criminal_data.get('crn', 'N/A'), 'Full Name', f"{criminal_data.get('first_name','')} {criminal_data.get('last_name','')}"],
        ['Date of Birth', str(criminal_data.get('date_of_birth', 'N/A'))[:10], 'Gender', criminal_data.get('gender', 'N/A')],
        ['Nationality', criminal_data.get('nationality', 'N/A'), 'Occupation', criminal_data.get('occupation', 'N/A')],
        ['Phone', criminal_data.get('phone', 'N/A'), 'Email', criminal_data.get('email', 'N/A')],
        ['Address', criminal_data.get('address', 'N/A'), '', ''],
    ]
    personal_table = Table(personal_data, colWidths=[3.5*cm, 5*cm, 3.5*cm, 5*cm])
    personal_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BACKGROUND', (0, 0), (-1, -1), LIGHT_GRAY),
        ('ROWBACKGROUNDS', (0, 0), (-1, -1), [LIGHT_GRAY, WHITE]),
        ('GRID', (0, 0), (-1, -1), 0.5, MID_GRAY),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(personal_table)

    # Criminal Profile
    story.append(Paragraph("Criminal Profile", _section_style()))
    story.append(HRFlowable(width='100%', color=ACCENT_BLUE, thickness=1))
    story.append(Spacer(1, 0.2*cm))

    profile_data = [
        ['Crime Type', criminal_data.get('crime_type', 'N/A'), 'Category', criminal_data.get('crime_category', 'N/A')],
        ['Prior Convictions', str(criminal_data.get('prior_convictions', 0)), 'Threat Level', criminal_data.get('threat_level', 'N/A').upper()],
        ['Is Wanted', 'YES' if criminal_data.get('is_wanted') else 'No', 'Incarcerated', 'YES' if criminal_data.get('is_incarcerated') else 'No'],
        ['Gang Affiliation', criminal_data.get('gang_name', 'None'), 'Gang Rank', criminal_data.get('gang_rank', 'N/A')],
        ['Risk Score', f"{risk_score:.0f}/100", '', ''],
    ]
    profile_table = Table(profile_data, colWidths=[3.5*cm, 5*cm, 3.5*cm, 5*cm])
    profile_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ROWBACKGROUNDS', (0, 0), (-1, -1), [LIGHT_GRAY, WHITE]),
        ('GRID', (0, 0), (-1, -1), 0.5, MID_GRAY),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(profile_table)

    if criminal_data.get('modus_operandi'):
        story.append(Spacer(1, 0.2*cm))
        story.append(Paragraph(f"<b>Modus Operandi:</b> {criminal_data['modus_operandi']}", _body_style()))

    # AI Predictions
    if predictions:
        story.append(Paragraph("AI Advisory Predictions (Not Legal Conclusions)", _section_style()))
        story.append(HRFlowable(width='100%', color=ACCENT_BLUE, thickness=1))
        story.append(Spacer(1, 0.2*cm))
        story.append(Paragraph(
            "⚠ The following predictions are generated by an AI model and are advisory only. "
            "They must be reviewed and verified by a qualified officer before taking any action.",
            ParagraphStyle('Disclaimer', fontName='Helvetica-Oblique', fontSize=8, textColor=MID_GRAY)
        ))
        story.append(Spacer(1, 0.2*cm))

        for pred in predictions[:3]:
            pred_data = [
                ['Predicted Crime', pred.get('predicted_crime_type', 'N/A'), 'Confidence', f"{pred.get('crime_type_confidence', 0):.1f}%"],
                ['Risk Score', f"{pred.get('risk_score', 0):.1f}/100", 'Risk Level', pred.get('risk_level', 'N/A').upper()],
                ['Gang Probability', f"{pred.get('gang_affiliation_probability', 0):.1f}%", 'Status', pred.get('review_status', 'pending').upper()],
            ]
            pred_table = Table(pred_data, colWidths=[3.5*cm, 5*cm, 3.5*cm, 5*cm])
            pred_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.HexColor('#eef4ff'), WHITE]),
                ('GRID', (0, 0), (-1, -1), 0.5, MID_GRAY),
                ('TOPPADDING', (0, 0), (-1, -1), 5),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ]))
            story.append(pred_table)
            story.append(Spacer(1, 0.2*cm))

    # Footer
    story.append(Spacer(1, 0.5*cm))
    story.append(HRFlowable(width='100%', color=MID_GRAY, thickness=0.5))
    story.append(Paragraph(
        "This document is classified CONFIDENTIAL. Unauthorized disclosure is prohibited. "
        "AI-CRMS v1.0 — For official use only.",
        ParagraphStyle('Footer', fontName='Helvetica-Oblique', fontSize=7, textColor=MID_GRAY, alignment=TA_CENTER)
    ))

    doc.build(story)
    return buffer.getvalue()


def generate_case_report(case_data: dict) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        rightMargin=2*cm, leftMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm
    )
    story = []

    # Header
    header_data = [[Paragraph("⚖ AI-CRMS — Case Investigation Report", _header_style())]]
    header_table = Table(header_data, colWidths=[17*cm])
    header_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), DARK_BLUE),
        ('TOPPADDING', (0, 0), (-1, -1), 14),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 14),
    ]))
    story.append(header_table)
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}  |  CONFIDENTIAL", _sub_header_style()))
    story.append(Spacer(1, 0.4*cm))

    # Case Details
    story.append(Paragraph("Case Details", _section_style()))
    story.append(HRFlowable(width='100%', color=ACCENT_BLUE, thickness=1))
    story.append(Spacer(1, 0.2*cm))

    case_table_data = [
        ['Case Number', case_data.get('case_number', 'N/A'), 'Status', case_data.get('status', 'N/A').upper()],
        ['Title', case_data.get('title', 'N/A'), 'Priority', case_data.get('priority', 'N/A').upper()],
        ['Crime Type', case_data.get('crime_type', 'N/A'), 'Category', case_data.get('crime_category', 'N/A')],
        ['Location', case_data.get('location', 'N/A'), 'Incident Date', str(case_data.get('incident_date', 'N/A'))[:10]],
        ['FIR Number', case_data.get('fir_number', 'N/A'), 'FIR Date', str(case_data.get('fir_date', 'N/A'))[:10]],
        ['Officer', case_data.get('officer_name', 'Unassigned'), '', ''],
    ]
    ct = Table(case_table_data, colWidths=[3.5*cm, 5*cm, 3.5*cm, 5*cm])
    ct.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTNAME', (3, 0), (3, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ROWBACKGROUNDS', (0, 0), (-1, -1), [LIGHT_GRAY, WHITE]),
        ('GRID', (0, 0), (-1, -1), 0.5, MID_GRAY),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(ct)

    # Suspects
    criminals = case_data.get('criminals', [])
    if criminals:
        story.append(Paragraph(f"Suspects / Accused ({len(criminals)})", _section_style()))
        story.append(HRFlowable(width='100%', color=ACCENT_BLUE, thickness=1))
        story.append(Spacer(1, 0.2*cm))
        headers = [['#', 'Name', 'CRN', 'Crime Type', 'Risk', 'Role']]
        rows = []
        for i, cc in enumerate(criminals, 1):
            c = cc.get('criminal', cc)
            rows.append([
                str(i),
                f"{c.get('first_name','')} {c.get('last_name','')}",
                c.get('crn', 'N/A'),
                c.get('crime_type', 'N/A'),
                f"{c.get('risk_score', 0):.0f}",
                cc.get('role', 'suspect')
            ])
        ct2 = Table(headers + rows, colWidths=[0.7*cm, 4*cm, 2.5*cm, 3*cm, 1.5*cm, 5.3*cm])
        ct2.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), DARK_BLUE),
            ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [LIGHT_GRAY, WHITE]),
            ('GRID', (0, 0), (-1, -1), 0.5, MID_GRAY),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(ct2)

    # Evidence
    evidence = case_data.get('evidence', [])
    if evidence:
        story.append(Paragraph(f"Evidence ({len(evidence)} items)", _section_style()))
        story.append(HRFlowable(width='100%', color=ACCENT_BLUE, thickness=1))
        story.append(Spacer(1, 0.2*cm))
        ev_headers = [['#', 'Evidence No.', 'Type', 'Description', 'Collected By', 'Status']]
        ev_rows = []
        for i, e in enumerate(evidence, 1):
            ev_rows.append([str(i), e.get('evidence_number','N/A'), e.get('type','N/A'),
                           (e.get('description','') or '')[:40], e.get('collected_by','N/A'), e.get('status','N/A')])
        ev_table = Table(ev_headers + ev_rows, colWidths=[0.7*cm, 2.5*cm, 2*cm, 5*cm, 3*cm, 3.8*cm])
        ev_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), DARK_BLUE),
            ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [LIGHT_GRAY, WHITE]),
            ('GRID', (0, 0), (-1, -1), 0.5, MID_GRAY),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(ev_table)

    # Footer
    story.append(Spacer(1, 0.5*cm))
    story.append(HRFlowable(width='100%', color=MID_GRAY, thickness=0.5))
    story.append(Paragraph(
        "CONFIDENTIAL — AI-CRMS v1.0 — For official use only.",
        ParagraphStyle('Footer', fontName='Helvetica-Oblique', fontSize=7, textColor=MID_GRAY, alignment=TA_CENTER)
    ))

    doc.build(story)
    return buffer.getvalue()
