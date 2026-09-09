from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from backend.app.schemas.pdf import ExcelGenerateRequest
from backend.app.services.excel_service import generate_excel_report


router = APIRouter(prefix="/api/v1", tags=["excel"])


def _content_disposition(filename: str) -> str:
    return f"attachment; filename*=UTF-8''{quote(filename, safe='')}"


@router.post("/excel")
def generate_excel(req: ExcelGenerateRequest) -> Response:
    from uuid import UUID, uuid4

    from backend.app.core.config import settings
    from backend.app.core.shared_storage import HistoryStorageUnavailable, publish, require_root
    from backend.app.repositories.history_repository import history_repository

    try:
        require_root(settings.DATA_DIR / "reports")
        record_id = str(UUID(req.record_id)) if req.record_id else "standalone"
        if req.record_id and not history_repository.get(record_id):
            raise HTTPException(status_code=404, detail="対象の履歴が見つかりません。")
        report_bytes = generate_excel_report(req.model_dump())
        filename = f"{uuid4()}.xlsx"
        publish(settings.DATA_DIR / "reports" / record_id / filename, report_bytes)
    except HistoryStorageUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Excelを保存できませんでした。NASの接続・書き込み権限を確認してください。") from None

    return Response(
        content=report_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": _content_disposition(req.output_filename),
            "X-Report-Url": f"/reports/{record_id}/{filename}",
        },
    )
