import os
import secrets
import sys
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine, select

def _default_data_dir() -> Path:
    # Dentro do bundle PyInstaller, __file__ aponta para o temp dir de extração.
    # sys.executable é sempre o .exe real — usamos ele para garantir que o banco
    # fique em <pasta do exe>\data\ independente de onde o serviço foi iniciado.
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent / "data"
    return Path(__file__).parent.parent / "data"

DATA_DIR = Path(os.environ.get("FB_DATA_DIR", _default_data_dir()))
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "fb_backup.db"
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})


def create_db_and_tables() -> None:
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session


def init_app_config() -> None:
    from backend.models import AppConfig

    with Session(engine) as session:
        config = session.get(AppConfig, 1)
        if config is None:
            config = AppConfig(id=1, app_secret_key=secrets.token_hex(32))
            session.add(config)
            session.commit()


def get_app_config():
    from backend.models import AppConfig

    with Session(engine) as session:
        return session.get(AppConfig, 1)


def set_admin_password(password: str) -> None:
    """Hash da senha com PBKDF2-HMAC-SHA256 e persiste no AppConfig id=1."""
    import hashlib
    from backend.models import AppConfig

    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 260_000)
    password_hash = dk.hex()

    with Session(engine) as session:
        config = session.get(AppConfig, 1)
        if config is None:
            config = AppConfig(id=1, app_secret_key=secrets.token_hex(32))
            session.add(config)
        config.admin_password_hash = password_hash
        config.admin_password_salt = salt
        session.add(config)
        session.commit()


def verify_admin_password(password: str) -> bool:
    """True se senha bate com hash, ou True se nenhum hash configurado (primeiro uso)."""
    import hashlib
    import hmac

    config = get_app_config()
    if not config or not config.admin_password_hash:
        return True  # sem senha definida: aceita qualquer coisa

    dk = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        config.admin_password_salt.encode("utf-8"),
        260_000,
    )
    return hmac.compare_digest(dk.hex(), config.admin_password_hash)


def get_fernet_key() -> bytes:
    """Deriva chave Fernet de 32 bytes a partir do app_secret_key."""
    import base64
    import hashlib

    config = get_app_config()
    key_bytes = hashlib.sha256(config.app_secret_key.encode()).digest()
    return base64.urlsafe_b64encode(key_bytes)
