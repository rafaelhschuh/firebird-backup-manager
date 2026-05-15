"""
Windows Service wrapper para o FB Backup Manager.

Uso pelo instalador:
  fb_backup_manager.exe --service install
  fb_backup_manager.exe --service start
  fb_backup_manager.exe --service stop
  fb_backup_manager.exe --service remove

Em Linux/dev este módulo é importado mas o código de serviço é ignorado.
"""

import logging
import os
import sys
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

IS_WINDOWS = sys.platform == "win32"


def _exe_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent.parent


def _start_uvicorn(port: int) -> None:
    try:
        import uvicorn
        from backend.main import app
        # Sem log_config próprio do uvicorn: seus loggers propagam para o root
        # logger que já tem o RotatingFileHandler configurado em main.py.
        _log_cfg = {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {},
            "handlers": {},
            "loggers": {
                "uvicorn":        {"handlers": [], "level": "INFO",    "propagate": True},
                "uvicorn.error":  {"handlers": [], "level": "INFO",    "propagate": True},
                "uvicorn.access": {"handlers": [], "level": "WARNING", "propagate": True},
            },
        }
        uvicorn.run(app, host="0.0.0.0", port=port, log_config=_log_cfg)
    except Exception:
        logger.exception("Erro fatal no thread uvicorn — servidor encerrado")


def run_dev(port: int = 8099) -> None:
    _start_uvicorn(port)


if IS_WINDOWS:
    try:
        import win32event
        import win32service
        import win32serviceutil

        class FBBackupService(win32serviceutil.ServiceFramework):
            _svc_name_ = "FBBackupManager"
            _svc_display_name_ = "FB Backup Manager"
            _svc_description_ = "Gerenciamento automatizado de backups de bancos Firebird"

            def __init__(self, args):
                win32serviceutil.ServiceFramework.__init__(self, args)
                self._stop_event = win32event.CreateEvent(None, 0, 0, None)

            def SvcStop(self):
                self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
                win32event.SetEvent(self._stop_event)

            def SvcDoRun(self):
                try:
                    # Garante que o diretório de trabalho é a pasta do exe
                    # (o serviço Windows inicia em System32 por padrão)
                    exe_dir = _exe_dir()
                    os.chdir(exe_dir)

                    # Cria tabelas e config antes de ler a porta
                    from backend.database import create_db_and_tables, init_app_config, get_app_config
                    create_db_and_tables()
                    init_app_config()
                    config = get_app_config()
                    port = config.app_port if config else 8099

                    thread = threading.Thread(target=_start_uvicorn, args=(port,), daemon=True)
                    thread.start()

                    # Aguarda uvicorn inicializar; se o thread morrer antes de 10 s
                    # é sinal de falha na inicialização — reporta STOPPED ao SCM.
                    time.sleep(10)
                    if not thread.is_alive():
                        raise RuntimeError("Thread uvicorn encerrou inesperadamente na inicialização")

                    self.ReportServiceStatus(win32service.SERVICE_RUNNING)
                    win32event.WaitForSingleObject(self._stop_event, win32event.INFINITE)

                except Exception as exc:
                    logger.exception("Erro fatal no serviço: %s", exc)
                    self.ReportServiceStatus(win32service.SERVICE_STOPPED)

        def _is_scm_context() -> bool:
            """True quando o processo não tem console — indica que foi iniciado pelo SCM."""
            import ctypes
            return ctypes.windll.kernel32.GetConsoleWindow() == 0

        def handle_service_args() -> bool:
            # Modo CLI: install / start / stop / remove
            if "--service" in sys.argv:
                idx = sys.argv.index("--service")
                if idx + 1 >= len(sys.argv):
                    return False
                action = sys.argv[idx + 1]
                sys.argv = [sys.argv[0], action]
                win32serviceutil.HandleCommandLine(FBBackupService)
                return True

            # Modo SCM: o exe frozen não tem console quando iniciado pelo Windows
            # Service Control Manager. GetConsoleWindow()==0 é o indicador correto.
            # HandleCommandLine sem args apenas exibe help e retorna sem chamar
            # StartServiceCtrlDispatcher — causando Error 1053. O padrão correto
            # para PyInstaller+pywin32 é usar servicemanager diretamente.
            if getattr(sys, "frozen", False) and _is_scm_context():
                import servicemanager
                servicemanager.Initialize()
                servicemanager.PrepareToHostSingle(FBBackupService)
                servicemanager.StartServiceCtrlDispatcher()
                return True

            return False

    except ImportError:
        logger.warning("pywin32 não disponível — modo serviço desabilitado.")

        def handle_service_args() -> bool:
            return False

else:
    def handle_service_args() -> bool:
        return False
