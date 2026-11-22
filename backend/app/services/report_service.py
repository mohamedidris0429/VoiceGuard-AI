"""PDF report generation (ReportLab) from real analysis records."""

from __future__ import annotations

import io
import uuid
from datetime import datetime, timezone
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.analysis import (
    STATUS_COMPLETED,
    AudioAnalysis,
    Report,
)
from app.models.user import User

NAVY = colors.HexColor("#080F1C")
SURFACE = colors.HexColor("#142238")
BORDER = colors.HexColor("#24344F")
GREEN = colors.HexColor("#22C55E")
TEAL = colors.HexColor("#14B8A6")
AMBER = colors.HexColor("#F59E0B")
RED = colors.HexColor("#EF4444")
TEXT = colors.HexColor("#0F172A")
MUTED = colors.HexColor("#475569")
LIGHT_ROW = colors.HexColor("#F1F5F9")

DISCLAIMER = (
    "AI voice detection is not 100% reliable. Results should be treated as indicators, "
    "not conclusive evidence. This report is produced by an automated model and does not "
    "verify the identity of any speaker. Do not use it as the sole basis for disciplinary, "
    "legal, financial or safety decisions."
)


def create_report_reference() -> str:
    return f"VG-{uuid.uuid4().hex[:10].upper()}"


def get_or_create_report(db: Session, analysis: AudioAnalysis) -> Report:
    existing = db.scalar(select(Report).where(Report.analysis_id == analysis.id))
    if existing:
        return existing
    report = Report(
        user_id=analysis.user_id,
        analysis_id=analysis.id,
        report_reference=create_report_reference(),
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def _verdict_text(analysis: AudioAnalysis) -> tuple[str, colors.Color]:
    if analysis.analysis_status != STATUS_COMPLETED or not analysis.predicted_class:
        return "Unable to analyse", AMBER
    if analysis.predicted_class == "synthetic":
        return "Potentially synthetic speech", RED
    return "Likely genuine human speech", GREEN


def _fmt(value, suffix: str = "") -> str:
    if value is None or value == "":
        return "Not available"
    if isinstance(value, float):
        return f"{value:.2f}{suffix}"
    return f"{value}{suffix}"


def _fmt_datetime(value: datetime | None) -> str:
    if not value:
        return "Not available"
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone().strftime("%d %b %Y, %H:%M:%S")


def build_report_pdf(
    analysis: AudioAnalysis,
    user: User,
    report_reference: str,
    *,
    quality: dict | None = None,
) -> bytes:
    """Render a single-analysis PDF report.

    ``quality`` is optional measured signal quality (Phase 3). Nothing in the
    report is invented: missing data is printed as "Not available", and a
    partial window analysis is labelled as partial.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=18 * mm,
        title=f"VoiceGuard AI Report {report_reference}",
        author="VoiceGuard AI",
        subject="Voice authenticity analysis report",
    )

    styles = getSampleStyleSheet()
    brand = ParagraphStyle(
        "Brand",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=colors.white,
        alignment=TA_LEFT,
    )
    brand_sub = ParagraphStyle(
        "BrandSub",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#94A3B8"),
    )
    section = ParagraphStyle(
        "Section",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=11.5,
        leading=15,
        textColor=NAVY,
        spaceBefore=10,
        spaceAfter=5,
    )
    body = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9.2,
        leading=13.4,
        textColor=TEXT,
    )
    muted = ParagraphStyle(
        "Muted",
        parent=body,
        fontSize=8.4,
        leading=12,
        textColor=MUTED,
    )

    verdict_text, verdict_color = _verdict_text(analysis)

    story: list = []

    header = Table(
        [
            [Paragraph("VoiceGuard AI", brand)],
            [Paragraph("Voice authenticity analysis report", brand_sub)],
        ],
        colWidths=[doc.width],
    )
    header.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), NAVY),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (0, 0), 12),
                ("BOTTOMPADDING", (0, 1), (0, 1), 12),
                ("LINEBELOW", (0, -1), (-1, -1), 2.4, GREEN),
            ]
        )
    )
    story.append(header)
    story.append(Spacer(1, 12))

    meta = Table(
        [
            [
                Paragraph(f"<b>Report ID</b><br/>{escape(report_reference)}", body),
                Paragraph(f"<b>Analysis ID</b><br/>#{analysis.id}", body),
            ],
            [
                Paragraph(f"<b>Generated</b><br/>{_fmt_datetime(datetime.now(timezone.utc))}", body),
                Paragraph(f"<b>Account</b><br/>{escape(user.email)}", body),
            ],
        ],
        colWidths=[doc.width / 2.0, doc.width / 2.0],
    )
    meta.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), LIGHT_ROW),
                ("BOX", (0, 0), (-1, -1), 0.6, BORDER),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D8E1EE")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.append(meta)
    story.append(Spacer(1, 14))

    story.append(Paragraph("Result", section))
    verdict_style = ParagraphStyle(
        "Verdict", parent=body, textColor=colors.white, fontSize=11, leading=15
    )
    verdict = Table(
        [
            [Paragraph(escape(verdict_text), verdict_style)],
            [
                Paragraph(
                    f"<font color='#94A3B8'>Model score (probability of synthetic speech):</font> "
                    f"<b>{_fmt(analysis.model_score)}</b>",
                    verdict_style,
                )
            ],
        ],
        colWidths=[doc.width],
    )
    verdict.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#0B1524")),
                ("BOX", (0, 0), (-1, -1), 0.8, verdict_color),
                ("LINEBEFORE", (0, 0), (0, -1), 4, verdict_color),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.append(verdict)
    story.append(Spacer(1, 12))

    story.append(Paragraph("Recording", section))
    recording_rows = [
        ["Filename", analysis.filename],
        ["Format", (analysis.file_format or "").upper() or "Not available"],
        ["Duration", _fmt(analysis.audio_duration, " s")],
        ["Sample rate", _fmt(analysis.sample_rate, " Hz")],
        ["Channels", _fmt(analysis.channels)],
        ["File size", f"{(analysis.file_size_bytes or 0) / 1024:.1f} KB"],
        ["Source", "Microphone recording" if analysis.source == "recording" else "File upload"],
        ["Analysed at", _fmt_datetime(analysis.created_at)],
    ]
    story.append(_kv_table(recording_rows, doc.width, body))
    story.append(Spacer(1, 10))

    story.append(Paragraph("Model and processing", section))
    details = analysis.model_details or {}
    model_rows = [
        ["Detection model", (analysis.model_version or settings.model_id)],
        ["Model task", "Binary bonafide vs spoof speech classification"],
        ["Model version", analysis.model_version or "Not available"],
        ["Decision threshold", _fmt(details.get("threshold", 0.5))],
        ["Windows analysed", _fmt(details.get("windows_analyzed"))],
        ["Window length", _fmt(details.get("window_seconds"), " s")],
        ["Aggregation", details.get("aggregation") or "Not available"],
        ["Raw window scores", _score_list(details.get("window_scores"))],
        ["Processing time", _fmt((analysis.analysis_duration_ms or 0) / 1000, " s")],
        ["Status", analysis.analysis_status],
    ]
    story.append(_kv_table(model_rows, doc.width, body))

    segments = list(getattr(analysis, "segments", []) or [])
    segment_meta = analysis.segment_meta or {}
    aggregate = segment_meta.get("aggregate") if isinstance(segment_meta, dict) else None
    if segments:
        story.append(Paragraph("Window-by-window analysis", section))
        reliable = bool(aggregate and aggregate.get("whole_file_reliable"))
        if aggregate:
            coverage_ratio = float(aggregate.get("coverage_ratio") or 0.0)
            coverage_rows = [
                ["Windows", f"{aggregate.get('completed_segments', 0)} scored of {len(segments)}"],
                [
                    "Coverage",
                    f"{coverage_ratio * 100:.1f}% "
                    f"({_fmt(aggregate.get('coverage_seconds'), ' s')} of "
                    f"{_fmt(analysis.audio_duration, ' s')})",
                ],
                ["Excluded windows", _fmt(aggregate.get("excluded_segments", 0))],
                ["Aggregate score", _fmt(aggregate.get("score"))],
                ["Scope", "Whole file" if reliable else "Partial - not a whole-file conclusion"],
                [
                    "Aggregate label",
                    aggregate.get("label") if reliable else "None (partial result)",
                ],
                ["Whole-file model score", _fmt(aggregate.get("whole_file_score"))],
            ]
            story.append(_kv_table(coverage_rows, doc.width, body))
            if not reliable:
                story.append(Spacer(1, 6))
                story.append(
                    Paragraph(
                        "<b>Partial coverage.</b> "
                        + escape(
                            aggregate.get("reliability_note")
                            or "Coverage is below the 95% threshold or windows were excluded."
                        )
                        + " The aggregate describes only the scored windows and must not be "
                        "presented as a whole-file authenticity conclusion.",
                        muted,
                    )
                )

        header = ["Window", "State", "Score", "Model label"]
        data = [[Paragraph(f"<b>{escape(cell)}</b>", body) for cell in header]]
        for segment in segments[:40]:
            data.append(
                [
                    Paragraph(
                        f"{segment.start_seconds:.2f}-{segment.end_seconds:.2f} s", body
                    ),
                    Paragraph(escape(str(segment.state)), body),
                    Paragraph(_fmt(segment.score), body),
                    Paragraph(escape(str(segment.label or "-")), body),
                ]
            )
        table = Table(data, colWidths=[doc.width * 0.32, doc.width * 0.2, doc.width * 0.22, doc.width * 0.26])
        table.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D8E1EE")),
                    ("BACKGROUND", (0, 0), (-1, 0), LIGHT_ROW),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(Spacer(1, 6))
        story.append(table)
        if len(segments) > 40:
            story.append(
                Paragraph(
                    f"Only the first 40 of {len(segments)} windows are listed here.", muted
                )
            )
        story.append(
            Paragraph(
                "Window scores are independent probabilistic model outputs. They are not proof "
                "that the audio in a window is genuine or cloned.",
                muted,
            )
        )

    if quality:
        story.append(Paragraph("Recording-quality observations", section))
        quality_rows = [
            ["Peak level", _fmt(quality.get("peak_dbfs"), " dBFS")],
            ["RMS level", _fmt(quality.get("rms_dbfs"), " dBFS")],
            ["Crest factor", _fmt(quality.get("crest_factor_db"), " dB")],
            ["Estimated SNR", _fmt(quality.get("snr_estimate_db"), " dB")],
            ["Effective bandwidth", _fmt(quality.get("effective_bandwidth_hz"), " Hz")],
            ["Clipping", f"{float(quality.get('clipping_ratio') or 0.0) * 100:.3f}% of samples"],
            ["DC offset", _fmt(quality.get("dc_offset"))],
            ["Silence ratio", f"{float(quality.get('silence_ratio') or 0.0) * 100:.1f}% of frames"],
        ]
        story.append(_kv_table(quality_rows, doc.width, body))
        for observation in quality.get("observations") or []:
            story.append(
                Paragraph(
                    f"<b>{escape(str(observation.get('title', '')))}</b> "
                    f"({escape(str(observation.get('severity', 'info')))}) - "
                    + escape(str(observation.get("detail", ""))[:400]),
                    muted,
                )
            )
        story.append(
            Paragraph(
                "These observations describe recording quality and signal characteristics. "
                "They are not evidence of authenticity or of voice cloning.",
                muted,
            )
        )

    if analysis.audio_features:
        story.append(Paragraph("Descriptive signal features", section))
        features = analysis.audio_features
        feature_rows = [
            ["Spectral centroid", _fmt(features.get("spectral_centroid_hz"), " Hz")],
            ["Spectral roll-off (85%)", _fmt(features.get("spectral_rolloff_hz"), " Hz")],
            ["Spectral bandwidth", _fmt(features.get("spectral_bandwidth_hz"), " Hz")],
            ["Zero-crossing rate", _fmt(features.get("zero_crossing_rate"))],
            ["RMS energy", _fmt(features.get("rms_energy"))],
            ["Peak amplitude", _fmt(features.get("peak_amplitude"))],
            ["Silence ratio", _fmt(features.get("silence_ratio"))],
        ]
        story.append(_kv_table(feature_rows, doc.width, body))
        story.append(
            Paragraph(
                "These features describe the audio signal. They are not used by the model to "
                "reach its verdict and must not be interpreted as evidence on their own.",
                muted,
            )
        )

    if analysis.analysis_status != STATUS_COMPLETED:
        story.append(Spacer(1, 8))
        story.append(
            Paragraph(
                f"<b>Analysis not completed:</b> {escape(analysis.failure_reason or 'No result was produced.')}",
                body,
            )
        )

    story.append(Spacer(1, 14))
    disclaimer_box = Table(
        [
            [
                Paragraph(
                    "<b>Limitations and disclaimer</b><br/>" + escape(DISCLAIMER), muted
                )
            ]
        ],
        colWidths=[doc.width],
    )
    disclaimer_box.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FEF7E6")),
                ("BOX", (0, 0), (-1, -1), 0.8, AMBER),
                ("LEFTPADDING", (0, 0), (-1, -1), 9),
                ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(KeepTogether(disclaimer_box))

    def _footer(canvas, document):
        canvas.saveState()
        canvas.setStrokeColor(BORDER)
        canvas.setLineWidth(0.5)
        canvas.line(18 * mm, 14 * mm, A4[0] - 18 * mm, 14 * mm)
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(18 * mm, 9.5 * mm, f"VoiceGuard AI  |  Report {report_reference}")
        canvas.drawRightString(
            A4[0] - 18 * mm, 9.5 * mm, f"Page {document.page}  |  SIH26104"
        )
        canvas.restoreState()

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buffer.getvalue()


def _score_list(scores) -> str:
    if not scores:
        return "Not available"
    return ", ".join(f"{float(score):.3f}" for score in scores)


def _kv_table(rows: list[list[str]], width: float, body: ParagraphStyle) -> Table:
    data = [
        [Paragraph(f"<b>{escape(str(label))}</b>", body), Paragraph(escape(str(value)), body)]
        for label, value in rows
    ]
    table = Table(data, colWidths=[width * 0.3, width * 0.7])
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D8E1EE")),
                ("BACKGROUND", (0, 0), (0, -1), LIGHT_ROW),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table
