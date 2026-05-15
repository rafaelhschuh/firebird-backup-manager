import logging
import sys
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session

from backend.database import create_db_and_tables, engine, init_app_config
from backend.scheduler import scheduler, load_schedules
from backend.routers import connections, backups, scheduler as sched_router, config
from backend.routers import auth as auth_router

# ---------------------------------------------------------------------------
# Logging — warns/errors sempre gravados em arquivo na pasta da aplicação
# ---------------------------------------------------------------------------
if getattr(sys, "frozen", False):
    _APP_DIR = Path(sys.executable).parent
else:
    _APP_DIR = Path(__file__).parent.parent

LOG_FILE = _APP_DIR / "fb_backup_manager.log"

_fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

_file_handler = RotatingFileHandler(LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=3, encoding="utf-8")
_file_handler.setFormatter(_fmt)

# Configura root logger diretamente (basicConfig é no-op se uvicorn já
# adicionou handlers; limpar e reconfigurar garante que o arquivo seja sempre usado).
_root = logging.getLogger()
_root.handlers.clear()
_root.setLevel(logging.WARNING)       # terceiros: só WARNING+
_root.addHandler(_file_handler)

logging.getLogger("backend").setLevel(logging.INFO)    # nossos módulos: INFO+
logging.getLogger("uvicorn").setLevel(logging.INFO)
logging.getLogger("uvicorn.error").setLevel(logging.INFO)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

# Console apenas se stdout disponível (ausente em modo serviço Windows)
if sys.stdout is not None:
    try:
        _con = logging.StreamHandler(sys.stdout)
        _con.setFormatter(_fmt)
        _root.addHandler(_con)
    except Exception:
        pass

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Frontend path (dev vs PyInstaller bundle)
# ---------------------------------------------------------------------------
if getattr(sys, "frozen", False):
    _FRONTEND_DIR = Path(sys._MEIPASS) / "frontend"
else:
    _FRONTEND_DIR = _APP_DIR / "frontend"


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    init_app_config()
    with Session(engine) as session:
        load_schedules(session)
    scheduler.start()
    logger.info("FB Backup Manager iniciado.")
    yield
    scheduler.shutdown(wait=False)
    logger.info("FB Backup Manager encerrado.")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="FB Backup Manager", version="1.0.0", lifespan=lifespan)

app.include_router(auth_router.router)
app.include_router(connections.router)
app.include_router(backups.router)
app.include_router(sched_router.router)
app.include_router(config.router)

# Serve o frontend por último (catch-all)
if _FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIR), html=True), name="frontend")
else:
    logger.warning("Diretório frontend não encontrado: %s", _FRONTEND_DIR)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    from backend.service import handle_service_args

    # Comando para definir a senha do admin (usado pelo instalador)
    if "--admin-password" in sys.argv:
        idx = sys.argv.index("--admin-password")
        if idx + 1 >= len(sys.argv):
            print("Erro: --admin-password requer um valor.", file=sys.stderr)
            sys.exit(1)
        pwd = sys.argv[idx + 1]
        from backend.database import set_admin_password
        create_db_and_tables()
        init_app_config()
        set_admin_password(pwd)
        print("Senha do administrador configurada.")
        sys.exit(0)

    if handle_service_args():
        sys.exit(0)

    from backend.database import get_app_config

    create_db_and_tables()
    init_app_config()
    cfg = get_app_config()
    port = cfg.app_port if cfg else 8099

    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=port, log_config=None)
