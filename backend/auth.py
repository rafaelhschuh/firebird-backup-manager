"""
Gerenciamento de sessões em memória para autenticação do painel web.

Sessões são perdidas ao reiniciar o serviço — comportamento esperado.
"""

import secrets
import threading
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Header, HTTPException

SESSION_DURATION_HOURS = 8

_sessions: dict[str, datetime] = {}  # token → expiry (UTC)
_lock = threading.Lock()


def create_session() -> str:
    token = secrets.token_hex(32)
    expiry = datetime.utcnow() + timedelta(hours=SESSION_DURATION_HOURS)
    with _lock:
        _sessions[token] = expiry
    return token


def is_valid_token(token: str) -> bool:
    with _lock:
        expiry = _sessions.get(token)
    if expiry is None:
        return False
    if datetime.utcnow() > expiry:
        with _lock:
            _sessions.pop(token, None)
        return False
    return True


def delete_session(token: str) -> None:
    with _lock:
        _sessions.pop(token, None)


def require_auth(authorization: Optional[str] = Header(None)) -> str:
    """FastAPI dependency — extrai e valida Bearer token. Levanta 401 se inválido."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Não autenticado")
    token = authorization[len("Bearer "):].strip()
    if not is_valid_token(token):
        raise HTTPException(status_code=401, detail="Sessão inválida ou expirada")
    return token
