---
title: Build e Distribuição
tags:
  - fb-backup-manager
  - build
  - pyinstaller
  - inno-setup
  - wine
---

# Build e Distribuição

![[index|← Voltar ao índice]]

O executável Windows é gerado a partir do Linux via **Wine**, usando o Python 3.12 Windows e o Inno Setup 6 instalados no prefixo Wine.

---

## Pré-requisitos

| Ferramenta | Onde instalar |
|---|---|
| `wine` | Pacote do sistema (`dnf install wine` / `apt install wine`) |
| Python 3.12 Windows | Baixe o instalador `.exe` e execute com `wine python-3.12-installer.exe` |
| Inno Setup 6 | Baixe em [jrsoftware.org](https://jrsoftware.org/isinfo.php) e execute com `wine is.exe` |

> [!note] Prefixo Wine
> O script usa `~/.wine` por padrão. Para usar outro prefixo, exporte `WINEPREFIX=/caminho/do/prefixo` antes de rodar o script.

---

## Executar o build

```bash
# Dentro do diretório do projeto
chmod +x build.sh
./build.sh
```

O script realiza automaticamente:

1. Verifica se `wine` está instalado
2. Localiza `python.exe` dentro de `~/.wine/drive_c` (busca recursiva)
3. Localiza `ISCC.exe` (Inno Setup compiler) dentro de `~/.wine/drive_c`
4. Instala dependências via `pip` no Python Windows (se necessário)
5. Roda **PyInstaller** para gerar `dist/fb_backup_manager.exe`
6. Roda **Inno Setup** para gerar `dist/FBBackupManager_Setup_1.0.0.exe`

**Output esperado:**

```
[INFO]  Procurando Python no prefixo Wine: /home/user/.wine
[OK]    Python: /home/user/.wine/drive_c/Python312/python.exe
[OK]    Inno Setup: /home/user/.wine/drive_c/.../ISCC.exe
[OK]    Dependências OK.
[INFO]  Rodando PyInstaller...
[OK]    Executável gerado: dist/fb_backup_manager.exe (52M)
[INFO]  Compilando instalador com Inno Setup...
[OK]    Instalador gerado: dist/FBBackupManager_Setup_1.0.0.exe (18M)

╔══════════════════════════════════════════════╗
║           Build concluída com sucesso        ║
╚══════════════════════════════════════════════╝
```

---

## Artefatos gerados

| Arquivo | Descrição |
|---|---|
| `dist/fb_backup_manager.exe` | Executável standalone (PyInstaller onefile) |
| `dist/FBBackupManager_Setup_1.0.0.exe` | Instalador Inno Setup para distribuição |

Copie **somente o instalador** para a máquina Windows alvo e execute como Administrador.

---

## PyInstaller — Detalhes

O `build.sh` invoca o PyInstaller com as seguintes opções relevantes:

```bash
pyinstaller \
  --onedir \
  --name fb_backup_manager \
  --add-data "frontend/index.html;frontend" \
  --hidden-import uvicorn.loops.auto \
  --hidden-import uvicorn.protocols.http.auto \
  --hidden-import apscheduler.triggers.cron \
  --hidden-import apscheduler.schedulers.background \
  --hidden-import win32serviceutil \
  backend/main.py
```

| Opção | Motivo |
|---|---|
| `--onedir` | Diretório com o exe + dependências. **Obrigatório para Windows Service** — com `--onefile` o bootloader do PyInstaller spawna um processo filho e depois morre, fazendo o SCM marcar o serviço como parado enquanto o processo filho fica órfão. |
| `--add-data "frontend/index.html;frontend"` | Inclui o SPA no bundle; separador `;` é Windows |
| `--hidden-import` | Módulos carregados dinamicamente que o PyInstaller não detecta sozinho |

> [!warning] Não use `--onefile` com Windows Service
> Com `--onefile`, o bootloader do PyInstaller extrai os arquivos em `%TEMP%\MEIxxxxxx\` e lança o Python real como processo filho. O SCM rastreia o PID do bootloader — quando ele termina, o serviço vai para `Stopped` e o processo filho fica órfão.

> [!note] sys._MEIPASS
> Em runtime, o PyInstaller extrai os dados em um diretório temporário apontado por `sys._MEIPASS`. O `main.py` usa essa variável para localizar o `frontend/`:
> ```python
> if getattr(sys, "frozen", False):
>     _FRONTEND_DIR = Path(sys._MEIPASS) / "frontend"
> ```

---

## Inno Setup — `installer.iss`

O script de instalação faz:

1. Detecta se o serviço `FBBackupManager` existe e para antes de instalar
2. **Apaga** `{app}\data\fb_backup.db` se existir (migração de schema)
3. Instala arquivos em `C:\Program Files\FBBackupManager\`
4. Registra e inicia o serviço Windows: `fb_backup_manager.exe --service install`
5. Cria atalho no Menu Iniciar que abre `http://localhost:8099`

> [!warning] Banco apagado na atualização
> O `installer.iss` apaga o banco SQLite antigo para evitar erros de schema. Após atualizar, reconfigure as conexões e agendamentos.

**Desinstalação:**
- Para o serviço: `net stop FBBackupManager`
- Remove o serviço: `fb_backup_manager.exe --service remove`
- Os arquivos `.fbk` de backup **não são apagados** (ficam nas pastas configuradas em cada conexão)

---

## Rodar em modo desenvolvimento (Linux)

Sem precisar do Wine ou Windows:

```bash
# Criar e ativar virtualenv
python3.12 -m venv venv
source venv/bin/activate

# Instalar dependências (pywin32 é ignorado no Linux)
pip install -r requirements.txt

# Iniciar o servidor
uvicorn backend.main:app --reload --port 8099
```

Acesse `http://localhost:8099` no browser.

> [!tip] Sem pywin32 no Linux
> O `requirements.txt` tem `pywin32==306; sys_platform == "win32"` — o pacote não é instalado no Linux. O `service.py` detecta a ausência e ignora o código de serviço Windows, rodando o app normalmente.

---

## Dependências (`requirements.txt`)

```
fastapi==0.111.0
uvicorn[standard]==0.29.0
sqlmodel==0.0.19
apscheduler==3.10.4
cryptography==42.0.7
pywin32==306; sys_platform == "win32"
pyinstaller==6.6.0
```

---

## Próximos passos

→ [[instalacao|Instalação]]
→ [[arquitetura|Arquitetura do projeto]]
