from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from datetime import datetime, timezone


def _generated_stamp() -> str:
    """Report timestamps are always UTC and labelled, so readers in other zones aren't misled."""
    return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')


def _pct(value) -> str:
    """Format a model score stored as a 0-1 fraction (legacy rows may hold 0-100)."""
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return "N/A"
    if number <= 1.0:
        number *= 100
    return f"{number:.1f}%"


_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _excel_safe(value):
    """Neutralise spreadsheet formula injection (CWE-1236) in exported cells."""
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value
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
    story.append(Paragraph(f"Generated: {_generated_stamp()}  |  By: {criminal_data.get('generated_by', 'N/A')}  |  CONFIDENTIAL", _sub_header_style()))
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

    # Associated Cases
    associated_cases = criminal_data.get('cases', [])
    if associated_cases:
        story.append(Paragraph(f"Associated Cases ({len(associated_cases)})", _section_style()))
        story.append(HRFlowable(width='100%', color=ACCENT_BLUE, thickness=1))
        rows = [['Case Number', 'Status', 'Crime Type', 'Role']] + [
            [c.get('case_number', 'N/A'), c.get('status', 'N/A'), c.get('crime_type', 'N/A'), c.get('role', 'N/A')]
            for c in associated_cases
        ]
        table = Table(rows, colWidths=[4*cm, 3*cm, 5*cm, 5*cm])
        table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),DARK_BLUE),('TEXTCOLOR',(0,0),(-1,0),WHITE),
                                   ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),8),
                                   ('ROWBACKGROUNDS',(0,1),(-1,-1),[LIGHT_GRAY,WHITE]),('GRID',(0,0),(-1,-1),0.5,MID_GRAY)]))
        story.append(table)

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
                ['Predicted Crime', pred.get('predicted_crime_type', 'N/A'), 'Confidence', _pct(pred.get('crime_type_confidence', 0))],
                ['Risk Score', f"{pred.get('risk_score', 0):.1f}/100", 'Risk Level', pred.get('risk_level', 'N/A').upper()],
                ['Gang Probability', _pct(pred.get('gang_affiliation_probability', 0)), 'Status', pred.get('review_status', 'pending').upper()],
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


# The case report is the FIR-style layout in app/utils/fir_report.py.
from app.utils.fir_report import generate_case_report  # noqa: E402,F401


# ── Excel exports ────────────────────────────────────────────────────────────
def _excel_workbook():
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    wb = Workbook()
    return wb


def _style_excel_sheet(ws):
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    header_fill = PatternFill('solid', fgColor='0D1B2A')
    header_font = Font(color='FFFFFF', bold=True)
    thin = Side(style='thin', color='D0D5DD')
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center', vertical='center')
        cell.border = Border(bottom=thin)
    ws.freeze_panes = 'A2'
    ws.auto_filter.ref = ws.dimensions
    for column_cells in ws.columns:
        width = min(max(max((len(str(c.value)) if c.value is not None else 0) for c in column_cells) + 2, 12), 42)
        ws.column_dimensions[column_cells[0].column_letter].width = width


def _write_sheet(wb, title, headers, rows):
    ws = wb.active if wb.active.title == 'Sheet' and wb.active.max_row == 1 and wb.active['A1'].value is None else wb.create_sheet()
    ws.title = title[:31]
    # openpyxl creates a blank first row on a new workbook. Remove it so the
    # exported sheet has a real header in row 1 rather than an empty row.
    if ws.max_row == 1 and all(cell.value is None for cell in ws[1]):
        ws.delete_rows(1, 1)
    ws.append(headers)
    for row in rows:
        ws.append([_excel_safe(cell) for cell in row])
    _style_excel_sheet(ws)
    return ws


def generate_criminal_excel(criminal_data: dict) -> bytes:
    wb = _excel_workbook()
    _write_sheet(wb, 'Criminal Profile',
        ['CRN', 'Name', 'Crime Category', 'Prior Convictions', 'Gang', 'Risk Score',
         'AI Prediction (unverified)', 'Model Score', 'Review Status', 'Generated (UTC)'],
        [[criminal_data.get('crn', 'N/A'), criminal_data.get('name', 'N/A'), criminal_data.get('crime_category', 'N/A'),
          criminal_data.get('prior_convictions', 0), criminal_data.get('gang_name', 'None'), criminal_data.get('risk_score', 0),
          criminal_data.get('prediction') or 'Not included', _pct(criminal_data.get('confidence', 0)) if criminal_data.get('prediction') else 'N/A',
          criminal_data.get('prediction_review_status') or 'N/A', _generated_stamp()]])

    cases = criminal_data.get('cases', [])
    _write_sheet(wb, 'Cases', ['Case Number', 'Status', 'Crime Type', 'Role'], [
        [c.get('case_number', 'N/A'), c.get('status', 'N/A'), c.get('crime_type', 'N/A'), c.get('role', 'N/A')] for c in cases
    ])

    bio = io.BytesIO()
    wb.save(bio)
    return bio.getvalue()


def generate_case_excel(case_data: dict) -> bytes:
    wb = _excel_workbook()
    _write_sheet(wb, 'Case Summary',
        ['Case Number', 'FIR Number', 'FIR Date', 'Status', 'Officer'],
        [[case_data.get('case_number', 'N/A'), case_data.get('fir_number', 'N/A'), case_data.get('fir_date', 'N/A'),
          case_data.get('status', 'N/A'), case_data.get('officer_name', 'Unassigned')]])

    _write_sheet(wb, 'Criminals', ['CRN', 'Name', 'Role'], [
        [c.get('criminal', c).get('crn', 'N/A'),
         f"{c.get('criminal', c).get('first_name', '')} {c.get('criminal', c).get('last_name', '')}".strip() or 'N/A',
         c.get('role', 'N/A')] for c in case_data.get('criminals', [])
    ])
    _write_sheet(wb, 'Victims', ['Name', 'Age', 'Gender', 'Status', 'Injury Description'], [
        [v.get('name', 'N/A'), v.get('age'), v.get('gender', 'N/A'), v.get('status', 'N/A'), v.get('injury_description', 'N/A')]
        for v in case_data.get('victims', [])
    ])
    _write_sheet(wb, 'Evidence', ['Evidence Number', 'Type', 'Description', 'Collected By', 'Status'], [
        [e.get('evidence_number', 'N/A'), e.get('type', 'N/A'), e.get('description', 'N/A'), e.get('collected_by', 'N/A'), e.get('status', 'N/A')]
        for e in case_data.get('evidence', [])
    ])

    bio = io.BytesIO()
    wb.save(bio)
    return bio.getvalue()


def generate_analytics_excel(analytics: dict) -> bytes:
    wb = _excel_workbook()
    _write_sheet(wb, 'KPI Summary', ['Metric', 'Value'], [
        ['Total Criminals', analytics.get('total_criminals', 0)],
        ['Total Cases', analytics.get('total_cases', 0)],
        ['Open Cases', analytics.get('open_cases', 0)],
        ['High Risk Criminals', analytics.get('high_risk_criminals', 0)],
        ['Pending AI Reviews', analytics.get('pending_reviews', 0)],
        ['Unread Alerts', analytics.get('unread_alerts', 0)],
        ['Reviewer Agreement Rate (%) - not model accuracy', analytics.get('reviewer_agreement_rate', analytics.get('prediction_accuracy', 0))],
        ['Generated (UTC)', _generated_stamp()],
    ])
    _write_sheet(wb, 'Cases by Status', ['Status', 'Count'], [[k, v] for k, v in analytics.get('cases_by_status', {}).items()])
    _write_sheet(wb, 'Crimes by Type', ['Crime Type', 'Count'], [[k, v] for k, v in analytics.get('crimes_by_type', {}).items()])
    _write_sheet(wb, 'Monthly Cases', ['Month', 'Cases'], [[m.get('month'), m.get('cases', 0)] for m in analytics.get('monthly_cases', [])])
    _write_sheet(wb, 'Officer Workload', ['Officer', 'Active Cases'], [[o.get('officer'), o.get('cases', 0)] for o in analytics.get('officer_workload', [])])
    bio = io.BytesIO()
    wb.save(bio)
    return bio.getvalue()


def generate_analytics_report(analytics: dict) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
    story = [Paragraph('AI-CRMS — Dashboard Analytics Report', _header_style()),
             Paragraph(f"Generated: {_generated_stamp()} | CONFIDENTIAL", _sub_header_style()), Spacer(1, 0.4*cm)]
    story.append(Paragraph('Key Performance Indicators', _section_style()))
    kpis = [
        ['Total Criminals', analytics.get('total_criminals', 0)], ['Total Cases', analytics.get('total_cases', 0)],
        ['Open Cases', analytics.get('open_cases', 0)], ['High Risk Criminals', analytics.get('high_risk_criminals', 0)],
        ['Pending AI Reviews', analytics.get('pending_reviews', 0)], ['Unread Alerts', analytics.get('unread_alerts', 0)],
        ['Reviewer Agreement Rate*', f"{analytics.get('reviewer_agreement_rate', analytics.get('prediction_accuracy', 0))}%"],
    ]
    t = Table(kpis, colWidths=[8*cm, 8*cm])
    t.setStyle(TableStyle([('FONTNAME',(0,0),(0,-1),'Helvetica-Bold'),('ROWBACKGROUNDS',(0,0),(-1,-1),[LIGHT_GRAY,WHITE]),('GRID',(0,0),(-1,-1),0.5,MID_GRAY),('FONTSIZE',(0,0),(-1,-1),9),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
    story.append(t)
    for title, key in [('Cases by Status','cases_by_status'), ('Crimes by Type','crimes_by_type')]:
        story.append(Paragraph(title, _section_style()))
        rows = [['Category','Count']] + [[str(k), str(v)] for k,v in analytics.get(key, {}).items()]
        if len(rows) == 1: rows.append(['No data', '0'])
        tt = Table(rows, colWidths=[11*cm,5*cm])
        tt.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),DARK_BLUE),('TEXTCOLOR',(0,0),(-1,0),WHITE),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('ROWBACKGROUNDS',(0,1),(-1,-1),[LIGHT_GRAY,WHITE]),('GRID',(0,0),(-1,-1),0.5,MID_GRAY),('FONTSIZE',(0,0),(-1,-1),9)]))
        story.append(tt)
    story.append(Paragraph('Monthly Cases', _section_style()))
    rows = [['Month','Cases']] + [[m.get('month','N/A'), str(m.get('cases',0))] for m in analytics.get('monthly_cases', [])]
    mt = Table(rows, colWidths=[11*cm,5*cm])
    mt.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),DARK_BLUE),('TEXTCOLOR',(0,0),(-1,0),WHITE),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('GRID',(0,0),(-1,-1),0.5,MID_GRAY),('ROWBACKGROUNDS',(0,1),(-1,-1),[LIGHT_GRAY,WHITE])]))
    story.append(mt)
    story.append(Spacer(1, 0.4*cm))
    story.append(Paragraph('* Share of human-reviewed AI predictions that reviewers confirmed. This measures reviewer '
                           'agreement, not model accuracy, and is not evidence of real-world predictive validity.', _body_style()))
    doc.build(story)
    return buffer.getvalue()
