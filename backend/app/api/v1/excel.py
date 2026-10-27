from __future__ import annotations

import logging
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from backend.app.schemas.pdf import ExcelGenerateRequest
from backend.app.services.excel_service import generate_excel_report


router = APIRouter(prefix="/api/v1", tags=["excel"])
logger = logging.getLogger("genba_safety_rag_app.api.excel")


def _content_disposition(filename: str) -> str:
    return f"attachment; filename*=UTF-8''{quote(filename, safe='')}"


@router.post("/excel")
def generate_excel(req: ExcelGenerateRequest) -> Response:
    from uuid import UUID, uuid4

    from backend.app.core.config import settings
    from backend.app.core.shared_storage import HistoryStorageUnavailable, publish, require_root
    from backend.app.repositories.history_repository import history_repository

    try:
        record_id = str(UUID(req.record_id)) if req.record_id else "standalone"
    except ValueError:
        raise HTTPException(status_code=422, detail="履歴IDの形式が正しくありません。") from None

    if req.record_id:
        try:
            record = history_repository.get(record_id)
        except HistoryStorageUnavailable:
            logger.exception("Excel出力の履歴取得に失敗しました (record_id=%s)", record_id)
            raise HTTPException(
                status_code=503,
                detail="履歴を取得できませんでした。保存先への接続と読み取り権限を確認してください。",
            ) from None
        except Exception:
            logger.exception("Excel出力の履歴取得中に予期しないエラーが発生しました (record_id=%s)", record_id)
            raise HTTPException(status_code=500, detail="履歴の確認中にエラーが発生しました。") from None
        if not record:
            raise HTTPException(status_code=404, detail="対象の履歴が見つかりません。")

    try:
        report_bytes = generate_excel_report(req.model_dump())
    except Exception:
        logger.exception("Excelファイルの生成に失敗しました (record_id=%s)", record_id)
        raise HTTPException(
            status_code=500,
            detail="Excelファイルを生成できませんでした。入力内容を確認して再試行してください。",
        ) from None

    try:
        require_root(settings.DATA_DIR / "reports")
        filename = f"{uuid4()}.xlsx"
        publish(settings.DATA_DIR / "reports" / record_id / filename, report_bytes)
    except HistoryStorageUnavailable:
        logger.exception("Excelファイルの保存に失敗しました (record_id=%s)", record_id)
        raise HTTPException(
            status_code=503,
            detail="Excelファイルを保存できませんでした。保存先への接続、書き込み権限、空き容量を確認してください。",
        ) from None
    except Exception:
        logger.exception("Excelファイルの保存中に予期しないエラーが発生しました (record_id=%s)", record_id)
        raise HTTPException(status_code=500, detail="Excelファイルの保存中にエラーが発生しました。") from None

    return Response(
        content=report_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": _content_disposition(req.output_filename),
            "X-Report-Url": f"/reports/{record_id}/{filename}",
        },
    )
