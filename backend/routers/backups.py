from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from backend.auth import is_valid_token, require_auth
from backend.database import get_session
from backend.models import BackupLog, BackupStatus, Connection

router = APIRouter(tags=["backups"])


class BackupLogOut(BaseModel):
    id: int
    connection_id: int
    started_at: str
    finished_at: Optional[str]
    status: BackupStatus
    fbk_path: Optional[str]
    fbk_size_bytes: Optional[int]
    duration_seconds: Optional[float]
    error_message: Optional[str]
    gbak_output: Optional[str]

    model_config = {"from_attributes": True}


def _enrich_log(log: BackupLog) -> dict:
    return {
        "id": log.id,
        "connection_id": log.connection_id,
        "started_at": log.started_at.isoformat(),
        "finished_at": log.finished_at.isoformat() if log.finished_at else None,
        "status": log.status,
        "fbk_path": log.fbk_path,
        "fbk_size_bytes": log.fbk_size_bytes,
        "duration_seconds": log.duration_seconds,
        "error_message": log.error_message,
        "gbak_output": log.gbak_output,
    }


@router.get("/api/logs", response_model=list[BackupLogOut], dependencies=[Depends(require_auth)])
def list_logs(
    connection_id: Optional[int] = None,
    limit: int = 50,
    session: Session = Depends(get_session),
):
    q = select(BackupLog).order_by(BackupLog.started_at.desc()).limit(limit)
    if connection_id:
        q = q.where(BackupLog.connection_id == connection_id)
    return [_enrich_log(lg) for lg in session.exec(q).all()]


@router.get("/api/backups/{connection_id}/run")
async def run_backup_stream(
    connection_id: int,
    token: Optional[str] = Query(None),        # para EventSource (não suporta headers)
    authorization: Optional[str] = Query(None, include_in_schema=False),
    session: Session = Depends(get_session),
):
    """SSE: executa o backup e transmite a saída do gbak em tempo real."""
    # Valida token de query param (EventSource) ou header Authorization
    actual_token = token
    if not actual_token and authorization and authorization.startswith("Bearer "):
        actual_token = authorization[len("Bearer "):].strip()
    if not actual_token or not is_valid_token(actual_token):
        raise HTTPException(status_code=401, detail="Não autenticado")

    conn = session.get(Connection, connection_id)
    if not conn:
        raise HTTPException(status_code=404, detail="Conexão não encontrada")

    from backend.backup import run_backup_stream

    return StreamingResponse(
        run_backup_stream(conn, session),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
