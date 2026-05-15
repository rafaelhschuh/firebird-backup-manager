#!/usr/bin/env bash
# build.sh — Gera fb_backup_manager.exe + instalador Inno Setup via Wine
# Uso: ./build.sh
# Requisito único: wine instalado no sistema

set -euo pipefail

# ── Cores ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ── Verificar wine ─────────────────────────────────────────────────────────
command -v wine >/dev/null 2>&1 || error "wine não encontrado. Instale com: sudo apt install wine  (ou dnf/pacman)"

WINE_PREFIX="${WINEPREFIX:-$HOME/.wine}"
WINE_C="$WINE_PREFIX/drive_c"

# ── Inicializar prefixo Wine se necessário ────────────────────────────────
if [[ ! -d "$WINE_C" ]]; then
  info "Prefixo Wine não encontrado — inicializando (pode demorar ~1 min na primeira vez)..."
  WINEDEBUG=-all WINEPREFIX="$WINE_PREFIX" wineboot --init 2>/dev/null || true
  [[ -d "$WINE_C" ]] || error "Falha ao inicializar o prefixo Wine em: $WINE_PREFIX"
  ok "Prefixo Wine inicializado."
fi

# ── URLs e cache de instaladores ───────────────────────────────────────────
PYTHON_URL="https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe"
INNOSETUP_URL="https://github.com/jrsoftware/issrc/releases/download/is-6_7_1/innosetup-6.7.1.exe"

CACHE_DIR="$(pwd)/.build-cache"
mkdir -p "$CACHE_DIR"

PYTHON_INSTALLER="$CACHE_DIR/python-3.12.10-amd64.exe"
INNOSETUP_INSTALLER="$CACHE_DIR/innosetup-6.7.1.exe"

# ── Função de download (curl ou wget) ──────────────────────────────────────
download() {
  local url="$1" dest="$2" name
  name="$(basename "$dest")"
  if [[ -f "$dest" ]]; then
    ok "Cache: $name"
    return
  fi
  info "Baixando $name..."
  if command -v curl >/dev/null 2>&1; then
    curl -L --progress-bar -o "$dest" "$url" || error "Falha ao baixar $url"
  elif command -v wget >/dev/null 2>&1; then
    wget -q --show-progress -O "$dest" "$url" || error "Falha ao baixar $url"
  else
    error "curl ou wget é necessário para o download automático."
  fi
  ok "Download OK: $name"
}

# ── Localizar ou instalar Python no Wine ───────────────────────────────────
info "Procurando Python no prefixo Wine: $WINE_PREFIX"

PYTHON_EXE=$(find "$WINE_C" -maxdepth 8 -name "python.exe" \
  ! -path "*/venv/*" ! -path "*/Lib/*" 2>/dev/null | head -1 || true)

if [[ -z "$PYTHON_EXE" ]]; then
  warn "python.exe não encontrado — instalando Python 3.12.10 via Wine..."
  download "$PYTHON_URL" "$PYTHON_INSTALLER"
  info "Instalando Python 3.12.10 (aguarde, pode demorar 1-2 min)..."
  WINEDEBUG=-all wine "$PYTHON_INSTALLER" \
    /quiet InstallAllUsers=0 PrependPath=0 Include_launcher=0 \
    || error "Falha ao instalar Python no Wine."
  ok "Python instalado."

  PYTHON_EXE=$(find "$WINE_C" -maxdepth 8 -name "python.exe" \
    ! -path "*/venv/*" ! -path "*/Lib/*" 2>/dev/null | head -1 || true)
  [[ -z "$PYTHON_EXE" ]] && error "python.exe não encontrado mesmo após instalação."
fi

ok "Python: $PYTHON_EXE"

PYTHON_SCRIPTS_DIR="$(dirname "$PYTHON_EXE")/Scripts"
PYINSTALLER_EXE="$PYTHON_SCRIPTS_DIR/pyinstaller.exe"

# ── Localizar ou instalar Inno Setup no Wine ──────────────────────────────
info "Procurando Inno Setup (ISCC.exe)..."

ISCC_EXE=$(find "$WINE_C" -maxdepth 6 -iname "ISCC.exe" 2>/dev/null | head -1 || true)

if [[ -z "$ISCC_EXE" ]]; then
  warn "ISCC.exe não encontrado — instalando Inno Setup 6.7.1 via Wine..."
  download "$INNOSETUP_URL" "$INNOSETUP_INSTALLER"
  info "Instalando Inno Setup 6.7.1 (aguarde)..."
  WINEDEBUG=-all wine "$INNOSETUP_INSTALLER" \
    /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP- \
    || error "Falha ao instalar Inno Setup no Wine."
  ok "Inno Setup instalado."

  ISCC_EXE=$(find "$WINE_C" -maxdepth 6 -iname "ISCC.exe" 2>/dev/null | head -1 || true)
  [[ -z "$ISCC_EXE" ]] && error "ISCC.exe não encontrado mesmo após instalação."
fi

ok "Inno Setup: $ISCC_EXE"

# ── Verificar / instalar dependências Python ───────────────────────────────
if [[ ! -f "$PYINSTALLER_EXE" ]]; then
  warn "pyinstaller.exe não encontrado — instalando dependências..."
  WINEDEBUG=-all wine "$PYTHON_EXE" -m pip install -r requirements.txt --quiet \
    || error "Falha ao instalar dependências no Wine Python."
  ok "Dependências instaladas."
fi

info "Verificando pacotes obrigatórios no Wine Python..."
REQUIRED=(fastapi uvicorn sqlmodel apscheduler cryptography pywin32)
for pkg in "${REQUIRED[@]}"; do
  WINEDEBUG=-all wine "$PYTHON_EXE" -c "import importlib; importlib.import_module('${pkg//-/_}')" 2>/dev/null \
    || {
      warn "$pkg não encontrado — instalando dependências..."
      WINEDEBUG=-all wine "$PYTHON_EXE" -m pip install -r requirements.txt --quiet \
        || error "Falha ao instalar dependências."
      break
    }
done
ok "Dependências OK."

# ── Limpar build anterior ──────────────────────────────────────────────────
info "Limpando artefatos anteriores..."
rm -rf build dist/__pycache__
mkdir -p dist

# ── PyInstaller ────────────────────────────────────────────────────────────
info "Rodando PyInstaller (isso pode levar alguns minutos)..."
WINEDEBUG=-all wine "$PYINSTALLER_EXE" \
  --onedir \
  --name fb_backup_manager \
  --add-data "frontend/index.html;frontend" \
  --hidden-import uvicorn.logging \
  --hidden-import uvicorn.loops \
  --hidden-import uvicorn.loops.auto \
  --hidden-import uvicorn.protocols \
  --hidden-import uvicorn.protocols.http \
  --hidden-import uvicorn.protocols.http.auto \
  --hidden-import uvicorn.protocols.websockets \
  --hidden-import uvicorn.protocols.websockets.auto \
  --hidden-import uvicorn.lifespan \
  --hidden-import uvicorn.lifespan.on \
  --hidden-import apscheduler.triggers.cron \
  --hidden-import apscheduler.schedulers.background \
  --hidden-import sqlmodel \
  --hidden-import win32serviceutil \
  --hidden-import win32service \
  --hidden-import win32event \
  --noconfirm \
  backend/main.py 2>&1 \
  | grep -E "(^\s*(INFO|WARNING|ERROR|CRITICAL):? (Build|Complet|Error|Cannot|copy)|completed successfully|Building EXE|Failed)" \
  || true

EXE="dist/fb_backup_manager/fb_backup_manager.exe"
[[ -f "$EXE" ]] || error "PyInstaller falhou — $EXE não gerado. Rode sem o filtro de log para ver detalhes."
ok "Executável gerado: $EXE ($(du -sh "dist/fb_backup_manager" | cut -f1) total)"

# ── Inno Setup ─────────────────────────────────────────────────────────────
info "Compilando instalador com Inno Setup..."
WINEDEBUG=-all wine "$ISCC_EXE" installer.iss 2>&1 \
  | grep -v "^$" \
  || true

INSTALLER="dist/FBBackupManager_Setup_1.0.0.exe"
[[ -f "$INSTALLER" ]] || error "Inno Setup falhou — $INSTALLER não gerado."
ok "Instalador gerado: $INSTALLER ($(du -sh "$INSTALLER" | cut -f1))"

# ── Resumo ─────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║           Build concluída com sucesso        ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════╝${NC}"
echo ""
ls -lh dist/*.exe
echo ""
info "Copie '$INSTALLER' para a máquina Windows e execute como Administrador."
