from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from backend.auth import is_valid_token, require_auth
from backend.database import get_session
from backend.models import BackupLog, BackupStatus, Connection

router = APIRouter(prefix="/api/maintenance", tags=["maintenance"])


class ReindexLogOut(BaseModel):
    id: int
    connection_id: int
    operation_type: str
    started_at: str
    finished_at: Optional[str]
    status: BackupStatus
    duration_seconds: Optional[float]
    error_message: Optional[str]

    model_config = {"from_attributes": True}


def _enrich_reindex_log(log: BackupLog) -> dict:
    return {
        "id": log.id,
        "connection_id": log.connection_id,
        "operation_type": log.operation_type,
        "started_at": log.started_at.isoformat(),
        "finished_at": log.finished_at.isoformat() if log.finished_at else None,
        "status": log.status,
        "duration_seconds": log.duration_seconds,
        "error_message": log.error_message,
    }


@router.get("/{connection_id}/reindex")
async def run_reindex(
    connection_id: int,
    skip_safety_backup: bool = Query(False),
    token: Optional[str] = Query(None),
    session: Session = Depends(get_session),
):
    """SSE: reindexação completa via ciclo backup → restore.

    Reconstrói os índices do banco Firebird, melhorando performance.
    Opcionalmente cria uma cópia .fdb.bkp antes de iniciar.
    """
    actual_token = token
    if not actual_token or not is_valid_token(actual_token):
        raise HTTPException(status_code=401, detail="Não autenticado")

    conn = session.get(Connection, connection_id)
    if not conn:
        raise HTTPException(status_code=404, detail="Conexão não encontrada")

    from backend.restore import run_reindex_stream

    return StreamingResponse(
        run_reindex_stream(
            connection=conn,
            session=session,
            skip_safety_backup=skip_safety_backup,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/logs", dependencies=[Depends(require_auth)])
def list_reindex_logs(
    connection_id: Optional[int] = None,
    limit: int = 50,
    session: Session = Depends(get_session),
) -> list[ReindexLogOut]:
    """Histórico de operações de reindexação."""
    q = (
        select(BackupLog)
        .where(BackupLog.operation_type == "REINDEX")
        .order_by(BackupLog.started_at.desc())
        .limit(limit)
    )
    if connection_id:
        q = q.where(BackupLog.connection_id == connection_id)
    return [_enrich_reindex_log(lg) for lg in session.exec(q).all()]
