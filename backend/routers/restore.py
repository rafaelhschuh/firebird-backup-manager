from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from backend.auth import is_valid_token, require_auth
from backend.database import get_session
from backend.models import BackupLog, BackupStatus, Connection, RestoreLog, RestoreType

router = APIRouter(prefix="/api/restore", tags=["restore"])


class RestoreLogOut(BaseModel):
    id: int
    connection_id: int
    restore_type: RestoreType
    fbk_path: str
    target_db_path: str
    safety_bkp_path: Optional[str]
    started_at: str
    finished_at: Optional[str]
    status: BackupStatus
    duration_seconds: Optional[float]
    error_message: Optional[str]

    model_config = {"from_attributes": True}


class AvailableBackup(BaseModel):
    log_id: int
    fbk_path: str
    started_at: str
    fbk_size_bytes: Optional[int]

    model_config = {"from_attributes": True}


def _enrich_restore_log(log: RestoreLog) -> dict:
    return {
        "id": log.id,
        "connection_id": log.connection_id,
        "restore_type": log.restore_type,
        "fbk_path": log.fbk_path,
        "target_db_path": log.target_db_path,
        "safety_bkp_path": log.safety_bkp_path,
        "started_at": log.started_at.isoformat(),
        "finished_at": log.finished_at.isoformat() if log.finished_at else None,
        "status": log.status,
        "duration_seconds": log.duration_seconds,
        "error_message": log.error_message,
    }


@router.get("/{connection_id}/files", dependencies=[Depends(require_auth)])
def list_available_backups(
    connection_id: int,
    session: Session = Depends(get_session),
) -> list[AvailableBackup]:
    """Lista os backups disponíveis (SUCCESS) para uma conexão."""
    conn = session.get(Connection, connection_id)
    if not conn:
        raise HTTPException(status_code=404, detail="Conexão não encontrada")

    logs = session.exec(
        select(BackupLog)
        .where(BackupLog.connection_id == connection_id)
        .where(BackupLog.status == BackupStatus.SUCCESS)
        .where(BackupLog.fbk_path != None)
        .order_by(BackupLog.started_at.desc())
        .limit(50)
    ).all()

    result = []
    for lg in logs:
        if lg.fbk_path:
            from pathlib import Path
            if Path(lg.fbk_path).exists():
                result.append({
                    "log_id": lg.id,
                    "fbk_path": lg.fbk_path,
                    "started_at": lg.started_at.isoformat(),
                    "fbk_size_bytes": lg.fbk_size_bytes,
                })
    return result


@router.get("/{connection_id}/run")
async def run_connection_restore(
    connection_id: int,
    fbk_path: str = Query(...),
    skip_safety_backup: bool = Query(False),
    token: Optional[str] = Query(None),
    session: Session = Depends(get_session),
):
    """SSE: restaura um .fbk sobre o banco da conexão existente."""
    actual_token = token
    if not actual_token or not is_valid_token(actual_token):
        raise HTTPException(status_code=401, detail="Não autenticado")

    conn = session.get(Connection, connection_id)
    if not conn:
        raise HTTPException(status_code=404, detail="Conexão não encontrada")
    if not fbk_path:
        raise HTTPException(status_code=400, detail="fbk_path é obrigatório")

    from backend.restore import run_restore_stream

    return StreamingResponse(
        run_restore_stream(
            connection=conn,
            fbk_path=fbk_path,
            target_db_path=conn.db_path,
            restore_type=RestoreType.CONNECTION,
            session=session,
            skip_safety_backup=skip_safety_backup,
            replace=True,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/simple/run")
async def run_simple_restore(
    server_connection_id: int = Query(...),
    fbk_path: str = Query(...),
    target_db_path: str = Query(...),
    token: Optional[str] = Query(None),
    session: Session = Depends(get_session),
):
    """SSE: restaura um .fbk para qualquer caminho .fdb (restore simples).

    Usa as credenciais da conexão selecionada para autenticar no servidor Firebird,
    mas NÃO modifica o banco da conexão.
    """
    actual_token = token
    if not actual_token or not is_valid_token(actual_token):
        raise HTTPException(status_code=401, detail="Não autenticado")

    conn = session.get(Connection, server_connection_id)
    if not conn:
        raise HTTPException(status_code=404, detail="Conexão não encontrada")
    if not fbk_path or not target_db_path:
        raise HTTPException(status_code=400, detail="fbk_path e target_db_path são obrigatórios")

    from backend.restore import run_restore_stream

    return StreamingResponse(
        run_restore_stream(
            connection=conn,
            fbk_path=fbk_path,
            target_db_path=target_db_path,
            restore_type=RestoreType.SIMPLE,
            session=session,
            skip_safety_backup=True,
            replace=False,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/logs", dependencies=[Depends(require_auth)])
def list_restore_logs(
    connection_id: Optional[int] = None,
    limit: int = 50,
    session: Session = Depends(get_session),
) -> list[RestoreLogOut]:
    """Histórico de operações de restore."""
    q = select(RestoreLog).order_by(RestoreLog.started_at.desc()).limit(limit)
    if connection_id:
        q = q.where(RestoreLog.connection_id == connection_id)
    return [_enrich_restore_log(lg) for lg in session.exec(q).all()]
