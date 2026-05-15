import mimetypes
import sys
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlmodel import Session

from backend.auth import require_auth
from backend.database import DATA_DIR, get_app_config, get_session
from backend.models import AppConfig

router = APIRouter(prefix="/api", tags=["config"])

APP_VERSION = "1.0.0"
_start_time = time.time()

ALLOWED_LOGO_EXTENSIONS = {".png", ".jpg", ".jpeg", ".svg", ".ico"}
MAX_LOGO_SIZE_BYTES = 2 * 1024 * 1024  # 2 MB


class ConfigOut(BaseModel):
    app_port: int

    model_config = {"from_attributes": True}


class ConfigUpdate(BaseModel):
    app_port: Optional[int] = None


class StatusOut(BaseModel):
    version: str
    uptime_seconds: float
    service_status: str


@router.get("/config", response_model=ConfigOut, dependencies=[Depends(require_auth)])
def get_config():
    config = get_app_config()
    return ConfigOut(app_port=config.app_port if config else 8099)


@router.put("/config", response_model=ConfigOut, dependencies=[Depends(require_auth)])
def update_config(body: ConfigUpdate, session: Session = Depends(get_session)):
    config = session.get(AppConfig, 1)
    if body.app_port is not None:
        config.app_port = body.app_port
    session.add(config)
    session.commit()
    session.refresh(config)
    return ConfigOut(app_port=config.app_port)


@router.get("/status", response_model=StatusOut, dependencies=[Depends(require_auth)])
def get_status():
    service_status = "N/A"
    if sys.platform == "win32":
        try:
            import win32serviceutil
            status_code = win32serviceutil.QueryServiceStatus("FBBackupManager")[1]
            service_status = "running" if status_code == 4 else "stopped"
        except Exception:
            service_status = "unknown"

    return StatusOut(
        version=APP_VERSION,
        uptime_seconds=round(time.time() - _start_time, 1),
        service_status=service_status,
    )


# ── Logo ──────────────────────────────────────────────────────────────────────

@router.get("/config/logo")  # SEM auth — público para tela de login e favicon
def get_logo():
    config = get_app_config()
    if not config or not config.logo_filename:
        raise HTTPException(status_code=404, detail="Nenhum logo configurado")
    logo_path = DATA_DIR / config.logo_filename
    if not logo_path.exists():
        raise HTTPException(status_code=404, detail="Arquivo de logo não encontrado")
    mime, _ = mimetypes.guess_type(str(logo_path))
    return FileResponse(str(logo_path), media_type=mime or "application/octet-stream")


@router.post("/config/logo", dependencies=[Depends(require_auth)])
async def upload_logo(
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
):
    suffix = Path(file.filename).suffix.lower() if file.filename else ""
    if suffix not in ALLOWED_LOGO_EXTENSIONS:
        raise HTTPException(400, "Formato não suportado. Use PNG, JPG, SVG ou ICO.")

    data = await file.read()
    if len(data) > MAX_LOGO_SIZE_BYTES:
        raise HTTPException(400, "Arquivo muito grande (máx. 2 MB).")

    filename = f"logo{suffix}"
    logo_path = DATA_DIR / filename

    # Remove logo antigo se tiver extensão diferente
    config = session.get(AppConfig, 1)
    if config and config.logo_filename and config.logo_filename != filename:
        old_path = DATA_DIR / config.logo_filename
        if old_path.exists():
            old_path.unlink()

    logo_path.write_bytes(data)

    if config:
        config.logo_filename = filename
        session.add(config)
        session.commit()

    return {"filename": filename}


@router.delete("/config/logo", status_code=204, dependencies=[Depends(require_auth)])
def delete_logo(session: Session = Depends(get_session)):
    config = session.get(AppConfig, 1)
    if config and config.logo_filename:
        old_path = DATA_DIR / config.logo_filename
        if old_path.exists():
            old_path.unlink()
        config.logo_filename = None
        session.add(config)
        session.commit()
    return None
