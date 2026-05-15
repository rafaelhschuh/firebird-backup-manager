import asyncio
import json
import logging
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator

from cryptography.fernet import Fernet
from sqlmodel import Session

from backend.database import get_fernet_key
from backend.models import BackupLog, BackupStatus, Connection

logger = logging.getLogger(__name__)

GBAK_DEFAULT_PATHS = [
    Path("C:/Program Files/Firebird/Firebird_5_0/gbak.exe"),
    Path("C:/Program Files/Firebird/Firebird_4_0/gbak.exe"),
    Path("C:/Program Files/Firebird/Firebird_3_0/gbak.exe"),
    Path("C:/Program Files (x86)/Firebird/Firebird_3_0/gbak.exe"),
]


def detect_gbak() -> str | None:
    for path in GBAK_DEFAULT_PATHS:
        if path.exists():
            return str(path)
    return shutil.which("gbak")


def decrypt_password(encrypted: str) -> str:
    f = Fernet(get_fernet_key())
    return f.decrypt(encrypted.encode()).decode()


def encrypt_password(plain: str) -> str:
    f = Fernet(get_fernet_key())
    return f.encrypt(plain.encode()).decode()


def _name_slug(name: str) -> str:
    slug = re.sub(r"[^\w\-]", "_", name.strip())
    return re.sub(r"_+", "_", slug).lower()


def build_connection_string(connection: Connection) -> str:
    """Monta host/port:path no formato aceito pelo Firebird."""
    return f"{connection.host}/{connection.port}:{connection.db_path}"


def _build_gbak_cmd(connection: Connection, fbk_path: str, password: str) -> list[str]:
    gbak_exe = connection.gbak_path
    if not gbak_exe:
        raise RuntimeError(
            "Caminho do gbak.exe não configurado. Informe o caminho nas opções da conexão."
        )
    conn_str = build_connection_string(connection)
    return [
        gbak_exe,
        "-b", "-v", "-g",
        "-user", connection.username,
        "-password", password,
        conn_str,
        fbk_path,
    ]


def _dest_path(connection: Connection, started: datetime) -> tuple[Path, str]:
    dest_dir = Path(connection.backup_path)
    dest_dir.mkdir(parents=True, exist_ok=True)
    ts = started.strftime("%Y%m%d_%H%M")
    slug = _name_slug(connection.name)
    filename = f"{slug}_{ts}.fbk"
    return dest_dir, str(dest_dir / filename)


def _apply_retention(dest_dir: Path, slug: str, retention_count: int) -> None:
    files = sorted(dest_dir.glob(f"{slug}_*.fbk"), key=lambda p: p.stat().st_mtime)
    for f in files[: max(0, len(files) - retention_count)]:
        try:
            f.unlink()
            logger.info("Retenção: removido %s", f)
        except Exception as exc:
            logger.warning("Falha ao remover %s: %s", f, exc)


def _finalize_log(
    log: BackupLog,
    session: Session,
    started: datetime,
    fbk_path: str,
    output_lines: list[str],
    error: str | None,
) -> BackupLog:
    finished = datetime.utcnow()
    dest_file = Path(fbk_path) if fbk_path else None

    if error or not dest_file or not dest_file.exists() or dest_file.stat().st_size == 0:
        log.status = BackupStatus.FAILED
        log.error_message = error or "Arquivo não gerado ou vazio"
    else:
        log.status = BackupStatus.SUCCESS
        log.fbk_path = fbk_path
        log.fbk_size_bytes = dest_file.stat().st_size

    log.finished_at = finished
    log.duration_seconds = (finished - started).total_seconds()
    log.gbak_output = "\n".join(output_lines)
    session.add(log)
    session.commit()
    session.refresh(log)
    return log


# ── Backup síncrono (usado pelo scheduler) ────────────────────────────────

def run_backup(connection: Connection, session: Session) -> BackupLog:
    log = BackupLog(connection_id=connection.id, status=BackupStatus.RUNNING)
    session.add(log)
    session.commit()
    session.refresh(log)

    started = datetime.utcnow()
    fbk_path = None
    error = None
    output_lines: list[str] = []

    try:
        password = decrypt_password(connection.password)
        dest_dir, fbk_path = _dest_path(connection, started)
        cmd = _build_gbak_cmd(connection, fbk_path, password)

        logger.info("Backup: %s → %s", connection.name, fbk_path)
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
        output_lines = ((result.stdout or "") + (result.stderr or "")).splitlines()

        if result.returncode != 0:
            error_lines = [l for l in output_lines if any(
                kw in l.lower() for kw in ("error", "failed", "unavailable", "exiting", "cannot", "unable")
            )]
            error = "\n".join(error_lines) if error_lines else f"código {result.returncode}"

        if not error:
            _apply_retention(dest_dir, _name_slug(connection.name), connection.retention_count)

    except Exception as exc:
        error = str(exc)
        logger.error("Falha no backup de %s: %s", connection.name, error)

    return _finalize_log(log, session, started, fbk_path or "", output_lines, error)


# ── Backup com streaming SSE (usado pela API manual) ─────────────────────

async def run_backup_stream(connection: Connection, session: Session) -> AsyncGenerator[str, None]:
    """Gera eventos SSE com as linhas do gbak em tempo real."""

    log = BackupLog(connection_id=connection.id, status=BackupStatus.RUNNING)
    session.add(log)
    session.commit()
    session.refresh(log)

    yield _sse({"type": "start", "log_id": log.id, "connection": connection.name})

    started = datetime.utcnow()
    fbk_path = None
    error = None
    output_lines: list[str] = []

    try:
        password = decrypt_password(connection.password)
        dest_dir, fbk_path = _dest_path(connection, started)
        cmd = _build_gbak_cmd(connection, fbk_path, password)

        yield _sse({"type": "cmd", "text": f"Executando backup de: {connection.name}"})

        loop = asyncio.get_event_loop()
        proc = await loop.run_in_executor(
            None,
            lambda: subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1,
            ),
        )

        while True:
            line = await loop.run_in_executor(None, proc.stdout.readline)
            if not line:
                break
            line = line.rstrip()
            output_lines.append(line)
            yield _sse({"type": "line", "text": line})

        await loop.run_in_executor(None, proc.wait)

        if proc.returncode != 0:
            error_lines = [l for l in output_lines if any(
                kw in l.lower() for kw in ("error", "failed", "unavailable", "exiting", "cannot", "unable")
            )]
            error = "\n".join(error_lines) if error_lines else f"código {proc.returncode}"

        if not error:
            _apply_retention(dest_dir, _name_slug(connection.name), connection.retention_count)

    except Exception as exc:
        error = str(exc)
        logger.error("Falha no backup (stream) de %s: %s", connection.name, error)
        yield _sse({"type": "line", "text": f"ERRO: {error}"})

    log = _finalize_log(log, session, started, fbk_path or "", output_lines, error)

    yield _sse({
        "type": "done",
        "status": log.status,
        "size": log.fbk_size_bytes,
        "duration": log.duration_seconds,
        "error": log.error_message,
        "log_id": log.id,
    })


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
