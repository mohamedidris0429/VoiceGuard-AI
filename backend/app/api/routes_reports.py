"""PDF report generation/download endpoints."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_owned_analysis
from app.core.errors import AppError
from app.core.rate_limit import enforce
from app.database.session import get_db
from app.models.analysis import STATUS_COMPLETED
from app.models.user import User
from app.services import forensic_service, report_service, storage_service

router = APIRouter(prefix="/api/reports", tags=["Reports"])


@router.get(
    "/{analysis_id}/download",
    summary="Download the PDF report for an analysis",
    response_class=Response,
)
def download_report(
    analysis_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    enforce(request, "analysis", f"user:{current_user.id}")
    analysis = get_owned_analysis(db, current_user, analysis_id)
    if analysis.analysis_status != STATUS_COMPLETED:
        raise AppError(
            "A report can only be generated for a completed analysis.",
            code="report_unavailable",
            status_code=409,
        )

    report = report_service.get_or_create_report(db, analysis)

    # Signal-quality observations are recomputed from the stored file when it is
    # still present; the report is still produced (without them) if it is not.
    quality = None
    path = storage_service.audio_path_for(analysis.stored_file_reference)
    if path.exists():
        try:
            quality = forensic_service.quality_report(path)
        except Exception:  # noqa: BLE001 - optional section, never blocks the report
            quality = None

    pdf_bytes = report_service.build_report_pdf(
        analysis, current_user, report.report_reference, quality=quality
    )
    filename = f"voiceguard-report-{report.report_reference}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=\"{filename}\"; filename*=UTF-8''{quote(filename)}",
            "Content-Length": str(len(pdf_bytes)),
            "Cache-Control": "private, no-store",
        },
    )


@router.get("/{analysis_id}/metadata", summary="Report reference for an analysis")
def report_metadata(
    analysis_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    analysis = get_owned_analysis(db, current_user, analysis_id)
    if analysis.analysis_status != STATUS_COMPLETED:
        raise AppError(
            "No report is available for this analysis.",
            code="report_unavailable",
            status_code=409,
        )
    report = report_service.get_or_create_report(db, analysis)
    return {"report_reference": report.report_reference, "analysis_id": analysis.id}
