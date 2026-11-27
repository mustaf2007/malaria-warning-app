"""PDF country intelligence reports built from the observations supplied by the app."""
from __future__ import annotations

from io import BytesIO
from math import isfinite
from xml.sax.saxutils import escape

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    Flowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)


class TrendChart(Flowable):
    """Small vector line chart; avoids image-rendering and browser dependencies."""

    def __init__(self, frame: pd.DataFrame, title: str, width: float = 165 * mm, height: float = 58 * mm):
        super().__init__()
        self.frame = frame.copy()
        self.title = title
        self.width = width
        self.height = height

    def wrap(self, avail_width, avail_height):
        return min(self.width, avail_width), self.height

    def draw(self):
        c = self.canv
        left, right, bottom, top = 16 * mm, self.width - 5 * mm, 12 * mm, self.height - 11 * mm
        c.setFont("Helvetica-Bold", 9)
        c.setFillColor(colors.HexColor("#183B35"))
        c.drawString(0, self.height - 7 * mm, self.title[:100])
        values = self.frame[["year", "value"]].dropna().sort_values("year")
        if values.empty:
            c.setFont("Helvetica", 8)
            c.drawString(left, self.height / 2, "No non-missing observations for this indicator.")
            return
        xs = values["year"].astype(float).tolist()
        ys = values["value"].astype(float).tolist()
        if not all(isfinite(v) for v in xs + ys):
            return
        xmin, xmax = min(xs), max(xs)
        ymin, ymax = min(ys), max(ys)
        if xmin == xmax:
            xmin, xmax = xmin - 1, xmax + 1
        if ymin == ymax:
            pad = abs(ymin) * 0.05 or 1
            ymin, ymax = ymin - pad, ymax + pad
        else:
            pad = (ymax - ymin) * 0.08
            ymin, ymax = ymin - pad, ymax + pad
        c.setStrokeColor(colors.HexColor("#D7E2DE"))
        c.setLineWidth(0.6)
        c.line(left, bottom, right, bottom)
        c.line(left, bottom, left, top)
        c.setFont("Helvetica", 7)
        c.setFillColor(colors.HexColor("#53645F"))
        c.drawString(left, 2 * mm, str(int(min(xs))))
        c.drawRightString(right, 2 * mm, str(int(max(xs))))
        c.drawString(0, top, f"{max(ys):,.3g}")
        c.drawString(0, bottom, f"{min(ys):,.3g}")
        points = [
            (left + (x - xmin) / (xmax - xmin) * (right - left),
             bottom + (y - ymin) / (ymax - ymin) * (top - bottom))
            for x, y in zip(xs, ys)
        ]
        c.setStrokeColor(colors.HexColor("#087F69"))
        c.setFillColor(colors.HexColor("#087F69"))
        c.setLineWidth(1.6)
        path = c.beginPath()
        path.moveTo(*points[0])
        for point in points[1:]:
            path.lineTo(*point)
        c.drawPath(path)
        for x, y in points:
            c.circle(x, y, 1.5, stroke=0, fill=1)


def _safe(value) -> str:
    if pd.isna(value):
        return "Not reported"
    return escape(str(value))


def _country_year_summary(frame: pd.DataFrame) -> pd.DataFrame:
    """Collapse source rows within a country-indicator-year before regional summaries.

    The median is an explicit descriptive compromise, not source harmonisation.
    Source count and labels are retained so disagreement remains visible.
    """
    valid = frame.dropna(subset=["value"]).copy()
    if valid.empty:
        return pd.DataFrame(columns=[
            "iso3", "country", "year", "value", "source_count", "sources"
        ])
    return (
        valid.groupby(["iso3", "country", "year"], as_index=False, dropna=False)
        .agg(
            value=("value", "median"),
            source_count=("source", "nunique"),
            sources=("source", lambda values: ", ".join(sorted(set(values.dropna().astype(str))))),
        )
        .sort_values(["iso3", "year"])
        .reset_index(drop=True)
    )


def build_country_report_pdf(
    observations: pd.DataFrame,
    country_iso: str,
    country_name: str,
    start_year: int,
    end_year: int,
    max_indicators: int = 8,
) -> bytes:
    """Create a source-aware country PDF; values are never imputed or fabricated."""
    required = {"iso3", "country", "year", "indicator_code", "value", "source"}
    missing = required - set(observations.columns)
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")
    if int(start_year) > int(end_year):
        raise ValueError("Start year must be less than or equal to end year.")
    iso = str(country_iso).strip().upper()
    if len(iso) != 3 or not iso.isalpha():
        raise ValueError("Country must be a three-letter ISO3 code.")
    data = observations[
        observations["iso3"].astype(str).str.upper().eq(iso)
        & pd.to_numeric(observations["year"], errors="coerce").between(int(start_year), int(end_year))
    ].copy()
    if data.empty:
        raise ValueError(f"No observations are available for {iso} in {start_year}–{end_year}.")
    data["year"] = pd.to_numeric(data["year"], errors="coerce")
    data["value"] = pd.to_numeric(data["value"], errors="coerce")
    data = data.dropna(subset=["year", "indicator_code"])
    if data.empty:
        raise ValueError("The selected country has no usable indicator-year observations.")
    data["year"] = data["year"].astype(int)
    data = data.sort_values(["indicator_code", "year"])
    usable = data[data["value"].notna()].copy()
    indicator_codes = sorted(data["indicator_code"].dropna().astype(str).unique())[:max(1, int(max_indicators))]
    if not indicator_codes:
        raise ValueError("No indicators are available for this country and period.")

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="ReportTitle", parent=styles["Title"], textColor=colors.HexColor("#123B32"), fontSize=22, leading=27, alignment=TA_CENTER, spaceAfter=5))
    styles.add(ParagraphStyle(name="Subtle", parent=styles["Normal"], textColor=colors.HexColor("#53645F"), fontSize=8, leading=11))
    styles.add(ParagraphStyle(name="SectionAMI", parent=styles["Heading2"], textColor=colors.HexColor("#087F69"), spaceBefore=10, spaceAfter=6))
    styles.add(ParagraphStyle(name="BodyAMI", parent=styles["BodyText"], fontSize=9, leading=13, spaceAfter=5))
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=18*mm, leftMargin=18*mm, topMargin=18*mm, bottomMargin=17*mm, title=f"{country_name} Malaria Intelligence Report", author="Africa Malaria Intelligence")
    story = [
        Spacer(1, 7*mm),
        Paragraph("AFRICA MALARIA INTELLIGENCE", styles["Subtle"]),
        Paragraph(f"{_safe(country_name)}", styles["ReportTitle"]),
        Paragraph("Country Malaria Intelligence Report", styles["Heading2"]),
        Paragraph(f"Reference period: {int(start_year)}–{int(end_year)} · ISO3: {iso}", styles["Subtle"]),
        Spacer(1, 5*mm),
        Paragraph("Executive snapshot", styles["SectionAMI"]),
        Paragraph(
            f"This report summarises {len(usable):,} non-missing observations across "
            f"{len(indicator_codes)} selected indicators and {data['year'].nunique()} reference years. "
            "The report reflects only the data supplied to the application for this country and period; "
            "it does not estimate missing values.", styles["BodyAMI"]
        ),
    ]
    summary_rows = [["Indicator", "Latest value", "Year", "Earliest value", "Year", "Source(s)"]]
    charts = []
    for code in indicator_codes:
        series = data[data["indicator_code"].astype(str) == code].sort_values("year")
        valid = _country_year_summary(series.assign(iso3=iso, country=country_name))
        if valid.empty:
            summary_rows.append([code, "Not available", "—", "Not available", "—", "No non-missing values"])
            continue
        first, last = valid.iloc[0], valid.iloc[-1]
        sources = ", ".join(sorted(series["source"].dropna().astype(str).unique()))
        summary_rows.append([
            code, f"{last['value']:,.4g}", str(int(last["year"])),
            f"{first['value']:,.4g}", str(int(first["year"])), _safe(sources[:100]),
        ])
        charts.append(TrendChart(valid[["year", "value"]], f"{code} · annual median across sources"))
    table = Table(summary_rows, repeatRows=1, colWidths=[34*mm, 23*mm, 12*mm, 23*mm, 12*mm, 48*mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#123B32")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 7),
        ("LEADING", (0,0), (-1,-1), 9),
        ("GRID", (0,0), (-1,-1), 0.35, colors.HexColor("#D7E2DE")),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#F2F7F5")]),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING", (0,0), (-1,-1), 4),
        ("RIGHTPADDING", (0,0), (-1,-1), 4),
        ("TOPPADDING", (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
    ]))
    story.extend([Paragraph("Indicator summary", styles["SectionAMI"]), table])
    if charts:
        story.append(Paragraph("Historical indicator trends", styles["SectionAMI"]))
        for chart in charts:
            story.extend([chart, Spacer(1, 2*mm)])
    story.append(Paragraph("Data coverage and provenance", styles["SectionAMI"]))
    source_rows = [["Source", "Observations", "Indicators", "Year coverage"]]
    for source, group in data.groupby("source", dropna=False):
        years = group["year"].dropna()
        source_rows.append([
            _safe(source), str(int(group["value"].notna().sum())),
            str(int(group["indicator_code"].nunique())),
            f"{int(years.min())}–{int(years.max())}" if not years.empty else "—",
        ])
    source_table = Table(source_rows, repeatRows=1, colWidths=[70*mm, 28*mm, 25*mm, 30*mm])
    source_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#E3EFEB")),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 8),
        ("GRID", (0,0), (-1,-1), 0.35, colors.HexColor("#D7E2DE")),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING", (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
    ]))
    story.extend([
        source_table, Spacer(1, 4*mm),
        Paragraph(
            "Interpretation notes: reported cases, modelled estimates and contextual health indicators are not interchangeable. "
            "Reference years can differ by indicator. Missing observations are not zero. MAP outputs, where present in the input, "
            "are modelled estimates rather than individual case reports. Trends are descriptive and do not constitute outbreak "
            "prediction, early warning, diagnosis or treatment advice.", styles["BodyAMI"]),
        Paragraph(
            "Source URLs and detailed indicator definitions should be checked in the application’s Data Quality & Sources workspace. "
            "This PDF is generated from the currently loaded dataset; cached upstream data may not be real-time.", styles["Subtle"]),
    ])

    def footer(canvas, document):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#D7E2DE"))
        canvas.line(18*mm, 13*mm, A4[0]-18*mm, 13*mm)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#53645F"))
        canvas.drawString(18*mm, 8*mm, "Africa Malaria Intelligence · Research and programme intelligence")
        canvas.drawRightString(A4[0]-18*mm, 8*mm, f"Page {document.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()



def build_africa_report_pdf(
    observations: pd.DataFrame,
    start_year: int,
    end_year: int,
    indicator_codes: list[str],
    indicator_labels: dict[str, str] | None = None,
    max_countries_per_indicator: int = 15,
) -> bytes:
    """Build a continental report using country-level observations without pooling unlike indicators."""
    required = {"iso3", "country", "year", "indicator_code", "value", "source"}
    missing = required - set(observations.columns)
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")
    if int(start_year) > int(end_year):
        raise ValueError("Start year must be less than or equal to end year.")
    selected = list(dict.fromkeys(str(code) for code in (indicator_codes or [])))
    if not selected:
        raise ValueError("Select at least one indicator for the Africa report.")
    if len(selected) > 8:
        raise ValueError("Select no more than eight indicators per report.")

    data = observations.copy()
    data["year"] = pd.to_numeric(data["year"], errors="coerce")
    data["value"] = pd.to_numeric(data["value"], errors="coerce")
    data["iso3"] = data["iso3"].astype(str).str.upper().str.strip()
    data = data[
        data["year"].between(int(start_year), int(end_year))
        & data["indicator_code"].astype(str).isin(selected)
        & data["iso3"].str.fullmatch(r"[A-Z]{3}", na=False)
    ].dropna(subset=["year", "indicator_code", "country"])
    if data.empty or not data["value"].notna().any():
        raise ValueError("No non-missing observations are available for the selected indicators and period.")
    data["year"] = data["year"].astype(int)
    labels = indicator_labels or {}
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="AfricaTitle", parent=styles["Title"], textColor=colors.HexColor("#123B32"), fontSize=22, leading=27, alignment=TA_CENTER, spaceAfter=5))
    styles.add(ParagraphStyle(name="AfricaSubtle", parent=styles["Normal"], textColor=colors.HexColor("#53645F"), fontSize=8, leading=11))
    styles.add(ParagraphStyle(name="AfricaSection", parent=styles["Heading2"], textColor=colors.HexColor("#087F69"), spaceBefore=10, spaceAfter=6))
    styles.add(ParagraphStyle(name="AfricaBody", parent=styles["BodyText"], fontSize=9, leading=13, spaceAfter=5))
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=18*mm, leftMargin=18*mm, topMargin=18*mm, bottomMargin=17*mm, title="Africa Malaria Annual Intelligence Report", author="Africa Malaria Intelligence")
    country_year = _country_year_summary(data)
    total_countries = int(country_year["iso3"].nunique())
    total_rows = int(len(country_year))
    story = [
        Spacer(1, 7*mm),
        Paragraph("AFRICA MALARIA INTELLIGENCE", styles["AfricaSubtle"]),
        Paragraph("AFRICA", styles["AfricaTitle"]),
        Paragraph("Continental Malaria Intelligence Report", styles["Heading2"]),
        Paragraph(f"Reference period: {int(start_year)}–{int(end_year)} · {len(selected)} selected indicators", styles["AfricaSubtle"]),
        Spacer(1, 5*mm),
        Paragraph("Continental snapshot", styles["AfricaSection"]),
        Paragraph(
            f"The selected dataset contains {total_rows:,} non-missing indicator observations across "
            f"{total_countries} African countries and {data['year'].nunique()} reference years. "
            "Country and indicator coverage varies; the statistics below are calculated separately for each indicator.",
            styles["AfricaBody"]),
        Paragraph(
            "Method: annual regional summaries are the unweighted median of available country observations for that indicator-year. "
            "They are not population-weighted continental rates or totals. Each country's latest available observation is shown with its year; "
            "countries are not forced onto a common reference year. Values from different indicators and units must not be compared directly.",
            styles["AfricaBody"]),
    ]
    overview_rows = [["Indicator", "Countries", "Observations", "Year span", "Latest year"]]
    for code in selected:
        valid = _country_year_summary(data[data["indicator_code"].astype(str) == code])
        overview_rows.append([
            _safe(labels.get(code, code)), str(valid["iso3"].nunique()), str(len(valid)),
            f"{int(valid['year'].min())}–{int(valid['year'].max())}" if not valid.empty else "—",
            str(int(valid['year'].max())) if not valid.empty else "—",
        ])
    overview = Table(overview_rows, repeatRows=1, colWidths=[65*mm, 23*mm, 28*mm, 28*mm, 22*mm])
    overview.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#123B32")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 7),
        ("GRID", (0,0), (-1,-1), 0.35, colors.HexColor("#D7E2DE")),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#F2F7F5")]),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING", (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
    ]))
    story.extend([Paragraph("Indicator coverage", styles["AfricaSection"]), overview])

    for code in selected:
        subset = data[data["indicator_code"].astype(str) == code].copy()
        valid_source_rows = subset[subset["value"].notna()].copy()
        valid = _country_year_summary(valid_source_rows)
        title = labels.get(code, code)
        story.append(Paragraph(_safe(title), styles["AfricaSection"]))
        if valid.empty:
            story.append(Paragraph("No non-missing observations are available for this indicator in the selected period.", styles["AfricaBody"]))
            continue
        annual = valid.groupby("year", as_index=False).agg(value=("value", "median"), countries=("iso3", "nunique"))
        story.append(Paragraph(
            f"Available source rows: {len(valid_source_rows):,}; country-year values after within-country source aggregation: "
            f"{len(valid):,} across {valid['iso3'].nunique()} countries. "
            "Each country contributes once per year using the median of its available source values; the continental line is the unweighted median of those country-level values. "
            "This does not harmonise differences in source definitions or methods.",
            styles["AfricaBody"]))
        story.append(TrendChart(annual[["year", "value"]], f"Unweighted country median · {title}", width=165*mm, height=55*mm))
        coverage_rows = [["Year", "Countries contributing", "Median value"]]
        for row in annual.itertuples(index=False):
            coverage_rows.append([str(int(row.year)), str(int(row.countries)), f"{row.value:,.4g}"])
        coverage = Table(coverage_rows, repeatRows=1, colWidths=[30*mm, 55*mm, 45*mm])
        coverage.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#E3EFEB")),
            ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE", (0,0), (-1,-1), 8),
            ("GRID", (0,0), (-1,-1), 0.35, colors.HexColor("#D7E2DE")),
            ("TOPPADDING", (0,0), (-1,-1), 4),
            ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ]))
        story.extend([coverage, Spacer(1, 3*mm)])
        latest_year = valid.groupby("iso3")["year"].max().rename("latest_year")
        latest = valid.join(latest_year, on="iso3")
        latest = latest[latest["year"] == latest["latest_year"]].sort_values(["value", "iso3"], ascending=[False, True])
        latest = latest.head(max(1, int(max_countries_per_indicator)))
        country_rows = [["Country", "ISO3", "Value", "Reference year", "Sources", "Source count"]]
        for row in latest.itertuples(index=False):
            country_rows.append([_safe(row.country), row.iso3, f"{row.value:,.4g}", str(int(row.year)), _safe(str(row.sources)[:45]), str(int(row.source_count))])
        country_table = Table(country_rows, repeatRows=1, colWidths=[38*mm, 15*mm, 22*mm, 22*mm, 50*mm, 20*mm])
        country_table.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#123B32")),
            ("TEXTCOLOR", (0,0), (-1,0), colors.white),
            ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE", (0,0), (-1,-1), 7),
            ("GRID", (0,0), (-1,-1), 0.35, colors.HexColor("#D7E2DE")),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#F2F7F5")]),
            ("TOPPADDING", (0,0), (-1,-1), 4),
            ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ]))
        story.extend([
            Paragraph("Country observations sorted by value (not a performance ranking)", styles["Heading3"]),
            country_table,
            Paragraph(
                "Latest available country values may refer to different years. Sorting is descriptive only; a high or low value is not automatically better or worse, "
                "and this table is not a league table of programme performance.", styles["AfricaSubtle"]),
        ])

    story.extend([
        Paragraph("Sources and interpretation", styles["AfricaSection"]),
        Paragraph(
            "The report is generated only from observations currently loaded in the application. It does not independently refresh upstream sources, "
            "impute missing values or harmonise different indicator definitions. Source labels are retained in country tables. "
            "Modelled malaria estimates, nationally reported cases, intervention indicators and contextual health measures are distinct evidence types. "
            "MAP estimates, where included, are modelled outputs rather than individual surveillance reports. This report is descriptive research and programme intelligence, "
            "not real-time surveillance, outbreak detection, prediction, diagnosis or treatment advice.", styles["AfricaBody"]),
        Paragraph(
            "Always consult the Data Quality & Sources workspace and the original source documentation before policy or programme decisions. "
            "Coverage, release dates, definitions and reporting years can differ across countries and indicators.", styles["AfricaSubtle"]),
    ])

    def footer(canvas, document):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#D7E2DE"))
        canvas.line(18*mm, 13*mm, A4[0]-18*mm, 13*mm)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#53645F"))
        canvas.drawString(18*mm, 8*mm, "Africa Malaria Intelligence · Continental research and programme intelligence")
        canvas.drawRightString(A4[0]-18*mm, 8*mm, f"Page {document.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
