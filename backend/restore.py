"""
Lógica de restore e reindexação de bancos Firebird via gbak.

Restore:
  - CONNECTION: restaura um .fbk sobre o banco da própria conexão (com cópia de segurança opcional)
  - SIMPLE: restaura um .fbk para qualquer caminho .fdb, aproveitando credenciais de uma conexão

Reindexação (manutenção):
  Executa ciclo backup → restore sobre o próprio banco para reconstruir índices e melhorar
  performance. Usa arquivo temporário e, opcionalmente, cria cópia de segurança antes.
"""

import asyncio
import json
import logging
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator, Optional

from sqlmodel import Session

from backend.backup import decrypt_password, build_connection_string, _build_gbak_cmd, _name_slug
from backend.models import BackupLog, BackupStatus, Connection, RestoreLog, RestoreType

logger = logging.getLogger(__name__)


# ── Utilitários ──────────────────────────────────────────────────────────────

def _safety_copy(db_path: str) -> str:
    """Copia o .fdb para .fdb.bkp como ponto de rollback rápido.

    Assume que db_path é acessível como arquivo local (manager no mesmo host
    do Firebird, ou caminho de rede mapeado).

    Retorna o caminho do arquivo .bkp criado.
    """
    src = Path(db_path)
    dst = Path(db_path + ".bkp")
    shutil.copy2(src, dst)
    logger.info("Cópia de segurança criada: %s", dst)
    return str(dst)


def _build_restore_cmd(
    connection: Connection,
    fbk_path: str,
    target_db_path: str,
    password: str,
    replace: bool = True,
) -> list[str]:
    """Monta o comando gbak para restore.

    fbk_path     — caminho LOCAL do .fbk (na máquina do manager/cliente gbak)
    target_db_path — caminho NO SERVIDOR Firebird onde o .fdb será criado/substituído
    replace=True  → flag -rep (substituir banco existente)
    replace=False → flag -cre (criar novo banco)
    """
    gbak_exe = connection.gbak_path
    if not gbak_exe:
        raise RuntimeError(
            "Caminho do gbak.exe não configurado. Informe o caminho nas opções da conexão."
        )
    flag = "-rep" if replace else "-cre"
    target_str = f"{connection.host}/{connection.port}:{target_db_path}"
    return [
        gbak_exe,
        flag, "-v",
        "-user", connection.username,
        "-password", password,
        fbk_path,
        target_str,
    ]


def _finalize_restore_log(
    log: RestoreLog,
    session: Session,
    started: datetime,
    output_lines: list[str],
    error: Optional[str],
) -> RestoreLog:
    finished = datetime.utcnow()
    log.finished_at = finished
    log.duration_seconds = (finished - started).total_seconds()
    log.gbak_output = "\n".join(output_lines)
    if error:
        log.status = BackupStatus.FAILED
        log.error_message = error
    else:
        log.status = BackupStatus.SUCCESS
    session.add(log)
    session.commit()
    session.refresh(log)
    return log


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


# ── Restore com streaming SSE ─────────────────────────────────────────────────

async def run_restore_stream(
    connection: Connection,
    fbk_path: str,
    target_db_path: str,
    restore_type: RestoreType,
    session: Session,
    skip_safety_backup: bool = False,
    replace: bool = True,
) -> AsyncGenerator[str, None]:
    """Gera eventos SSE com as linhas do gbak restore em tempo real."""

    log = RestoreLog(
        connection_id=connection.id,
        restore_type=restore_type,
        fbk_path=fbk_path,
        target_db_path=target_db_path,
        status=BackupStatus.RUNNING,
    )
    session.add(log)
    session.commit()
    session.refresh(log)

    yield _sse({"type": "start", "log_id": log.id, "connection": connection.name})

    started = datetime.utcnow()
    error: Optional[str] = None
    output_lines: list[str] = []

    try:
        password = decrypt_password(connection.password)

        # Cópia de segurança antes do restore (apenas para restore sobre banco existente)
        if restore_type == RestoreType.CONNECTION and not skip_safety_backup:
            try:
                yield _sse({"type": "line", "text": f"Criando cópia de segurança: {target_db_path}.bkp ..."})
                bkp_path = _safety_copy(target_db_path)
                log.safety_bkp_path = bkp_path
                session.add(log)
                session.commit()
                yield _sse({"type": "line", "text": f"Cópia criada: {bkp_path}"})
            except Exception as exc:
                yield _sse({"type": "line", "text": f"AVISO: Não foi possível criar cópia de segurança: {exc}"})

        cmd = _build_restore_cmd(connection, fbk_path, target_db_path, password, replace)
        yield _sse({"type": "cmd", "text": f"Iniciando restore para: {target_db_path}"})

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

    except Exception as exc:
        error = str(exc)
        logger.error("Falha no restore (stream) de %s: %s", connection.name, error)
        yield _sse({"type": "line", "text": f"ERRO: {error}"})

    log = _finalize_restore_log(log, session, started, output_lines, error)

    yield _sse({
        "type": "done",
        "status": log.status,
        "duration": log.duration_seconds,
        "error": log.error_message,
        "log_id": log.id,
    })


# ── Restore síncrono (usado internamente pela reindexação) ────────────────────

def run_restore_sync(
    connection: Connection,
    fbk_path: str,
    target_db_path: str,
    restore_type: RestoreType,
    session: Session,
    replace: bool = True,
) -> RestoreLog:
    log = RestoreLog(
        connection_id=connection.id,
        restore_type=restore_type,
        fbk_path=fbk_path,
        target_db_path=target_db_path,
        status=BackupStatus.RUNNING,
    )
    session.add(log)
    session.commit()
    session.refresh(log)

    started = datetime.utcnow()
    error: Optional[str] = None
    output_lines: list[str] = []

    try:
        password = decrypt_password(connection.password)
        cmd = _build_restore_cmd(connection, fbk_path, target_db_path, password, replace)
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
        output_lines = ((result.stdout or "") + (result.stderr or "")).splitlines()

        if result.returncode != 0:
            error_lines = [l for l in output_lines if any(
                kw in l.lower() for kw in ("error", "failed", "unavailable", "exiting", "cannot", "unable")
            )]
            error = "\n".join(error_lines) if error_lines else f"código {result.returncode}"

    except Exception as exc:
        error = str(exc)
        logger.error("Falha no restore de %s: %s", connection.name, error)

    return _finalize_restore_log(log, session, started, output_lines, error)


# ── Reindexação com streaming SSE ─────────────────────────────────────────────

async def run_reindex_stream(
    connection: Connection,
    session: Session,
    skip_safety_backup: bool = False,
) -> AsyncGenerator[str, None]:
    """Reindexação via ciclo gbak backup → restore.

    Fluxo:
      1. (opcional) Cópia de segurança: db_path → db_path.bkp
      2. Backup para arquivo temporário
      3. Restore do temporário sobre o banco original
      4. Remoção do temporário
    """
    yield _sse({"type": "start", "connection": connection.name})

    started = datetime.utcnow()

    try:
        password = decrypt_password(connection.password)
        dest_dir = Path(connection.backup_path)
        dest_dir.mkdir(parents=True, exist_ok=True)
        slug = _name_slug(connection.name)
        ts = started.strftime("%Y%m%d_%H%M")
        temp_fbk = str(dest_dir / f"{slug}_reindex_temp_{ts}.fbk")

        # ── Fase 0: cópia de segurança ─────────────────────────────────────
        if not skip_safety_backup:
            try:
                yield _sse({"type": "phase", "text": "Fase 0/2 — Criando cópia de segurança (.fdb.bkp) ..."})
                bkp_path = _safety_copy(connection.db_path)
                yield _sse({"type": "line", "text": f"Cópia criada: {bkp_path}"})
            except Exception as exc:
                yield _sse({"type": "line", "text": f"AVISO: Não foi possível criar cópia de segurança: {exc}"})

        # ── Fase 1: backup para temporário ────────────────────────────────
        yield _sse({"type": "phase", "text": "Fase 1/2 — Backup temporário para reindexação ..."})

        # Cria BackupLog para rastrear a fase de backup
        bkp_log = BackupLog(
            connection_id=connection.id,
            status=BackupStatus.RUNNING,
            operation_type="REINDEX",
            fbk_path=temp_fbk,
        )
        session.add(bkp_log)
        session.commit()
        session.refresh(bkp_log)

        bkp_cmd = _build_gbak_cmd(connection, temp_fbk, password)
        bkp_output: list[str] = []
        bkp_error: Optional[str] = None
        bkp_started = datetime.utcnow()

        loop = asyncio.get_event_loop()
        proc = await loop.run_in_executor(
            None,
            lambda: subprocess.Popen(
                bkp_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1,
            ),
        )

        while True:
            line = await loop.run_in_executor(None, proc.stdout.readline)
            if not line:
                break
            line = line.rstrip()
            bkp_output.append(line)
            yield _sse({"type": "line", "text": line})

        await loop.run_in_executor(None, proc.wait)

        if proc.returncode != 0:
            error_lines = [l for l in bkp_output if any(
                kw in l.lower() for kw in ("error", "failed", "unavailable", "exiting", "cannot", "unable")
            )]
            bkp_error = "\n".join(error_lines) if error_lines else f"código {proc.returncode}"

        # Finaliza BackupLog da fase 1
        bkp_finished = datetime.utcnow()
        temp_path = Path(temp_fbk)
        bkp_log.finished_at = bkp_finished
        bkp_log.duration_seconds = (bkp_finished - bkp_started).total_seconds()
        bkp_log.gbak_output = "\n".join(bkp_output)
        if bkp_error or not temp_path.exists() or temp_path.stat().st_size == 0:
            bkp_log.status = BackupStatus.FAILED
            bkp_log.error_message = bkp_error or "Arquivo temporário não gerado"
        else:
            bkp_log.status = BackupStatus.SUCCESS
            bkp_log.fbk_size_bytes = temp_path.stat().st_size
        session.add(bkp_log)
        session.commit()

        if bkp_log.status == BackupStatus.FAILED:
            yield _sse({
                "type": "done",
                "status": "FAILED",
                "error": bkp_log.error_message,
                "phase": "backup",
            })
            return

        # ── Fase 2: restore sobre banco original ──────────────────────────
        yield _sse({"type": "phase", "text": "Fase 2/2 — Restore sobre banco original ..."})

        rest_log = RestoreLog(
            connection_id=connection.id,
            restore_type=RestoreType.CONNECTION,
            fbk_path=temp_fbk,
            target_db_path=connection.db_path,
            status=BackupStatus.RUNNING,
        )
        session.add(rest_log)
        session.commit()
        session.refresh(rest_log)

        rest_cmd = _build_restore_cmd(connection, temp_fbk, connection.db_path, password, replace=True)
        rest_output: list[str] = []
        rest_error: Optional[str] = None
        rest_started = datetime.utcnow()

        proc2 = await loop.run_in_executor(
            None,
            lambda: subprocess.Popen(
                rest_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1,
            ),
        )

        while True:
            line = await loop.run_in_executor(None, proc2.stdout.readline)
            if not line:
                break
            line = line.rstrip()
            rest_output.append(line)
            yield _sse({"type": "line", "text": line})

        await loop.run_in_executor(None, proc2.wait)

        if proc2.returncode != 0:
            error_lines = [l for l in rest_output if any(
                kw in l.lower() for kw in ("error", "failed", "unavailable", "exiting", "cannot", "unable")
            )]
            rest_error = "\n".join(error_lines) if error_lines else f"código {proc2.returncode}"

        rest_log = _finalize_restore_log(rest_log, session, rest_started, rest_output, rest_error)

        # Remove arquivo temporário
        try:
            Path(temp_fbk).unlink(missing_ok=True)
            yield _sse({"type": "line", "text": f"Arquivo temporário removido: {temp_fbk}"})
        except Exception as exc:
            yield _sse({"type": "line", "text": f"AVISO: Não foi possível remover temporário: {exc}"})

        yield _sse({
            "type": "done",
            "status": rest_log.status,
            "duration": (datetime.utcnow() - started).total_seconds(),
            "error": rest_log.error_message,
        })

    except Exception as exc:
        logger.error("Falha na reindexação de %s: %s", connection.name, exc)
        yield _sse({"type": "done", "status": "FAILED", "error": str(exc)})


# ── Reindexação síncrona (usada pelo scheduler) ───────────────────────────────

def run_reindex(connection: Connection, session: Session) -> None:
    """Reindexação síncrona via ciclo backup → restore. Usado pelo APScheduler."""
    started = datetime.utcnow()
    password = decrypt_password(connection.password)
    dest_dir = Path(connection.backup_path)
    dest_dir.mkdir(parents=True, exist_ok=True)
    slug = _name_slug(connection.name)
    ts = started.strftime("%Y%m%d_%H%M")
    temp_fbk = str(dest_dir / f"{slug}_reindex_temp_{ts}.fbk")

    # Fase 1: backup para temporário
    bkp_log = BackupLog(
        connection_id=connection.id,
        status=BackupStatus.RUNNING,
        operation_type="REINDEX",
        fbk_path=temp_fbk,
    )
    session.add(bkp_log)
    session.commit()
    session.refresh(bkp_log)

    bkp_cmd = _build_gbak_cmd(connection, temp_fbk, password)
    bkp_started = datetime.utcnow()
    result = subprocess.run(bkp_cmd, capture_output=True, text=True, timeout=3600)
    bkp_output = ((result.stdout or "") + (result.stderr or "")).splitlines()
    bkp_error: Optional[str] = None

    if result.returncode != 0:
        error_lines = [l for l in bkp_output if any(
            kw in l.lower() for kw in ("error", "failed", "unavailable", "exiting", "cannot", "unable")
        )]
        bkp_error = "\n".join(error_lines) if error_lines else f"código {result.returncode}"

    bkp_finished = datetime.utcnow()
    temp_path = Path(temp_fbk)
    bkp_log.finished_at = bkp_finished
    bkp_log.duration_seconds = (bkp_finished - bkp_started).total_seconds()
    bkp_log.gbak_output = "\n".join(bkp_output)
    if bkp_error or not temp_path.exists() or temp_path.stat().st_size == 0:
        bkp_log.status = BackupStatus.FAILED
        bkp_log.error_message = bkp_error or "Arquivo temporário não gerado"
        session.add(bkp_log)
        session.commit()
        logger.error("Reindexação (backup) falhou para %s: %s", connection.name, bkp_log.error_message)
        return
    else:
        bkp_log.status = BackupStatus.SUCCESS
        bkp_log.fbk_size_bytes = temp_path.stat().st_size
    session.add(bkp_log)
    session.commit()

    # Fase 2: restore sobre banco original
    rest_log = run_restore_sync(
        connection, temp_fbk, connection.db_path,
        RestoreType.CONNECTION, session, replace=True,
    )

    # Remove temporário
    try:
        temp_path.unlink(missing_ok=True)
    except Exception as exc:
        logger.warning("Não foi possível remover temporário %s: %s", temp_fbk, exc)

    if rest_log.status == BackupStatus.FAILED:
        logger.error("Reindexação (restore) falhou para %s: %s", connection.name, rest_log.error_message)
    else:
        logger.info("Reindexação concluída para %s em %.1fs", connection.name, rest_log.duration_seconds)
