# FB Backup Manager

Aplicação web **self-hosted** para gerenciamento automatizado de backups de bancos de dados **Firebird**. Roda como **Windows Service** e expõe uma interface web em PT-BR acessível pelo browser.

---

## Funcionalidades

- **Dashboard** com resumo de status, últimos backups e próxima execução agendada
- **Conexões** — cadastro de múltiplos servidores Firebird com senhas criptografadas (Fernet/AES)
- **Agendamentos** — cron flexível por hora, minuto e dias da semana
- **Backup em tempo real** — saída do `gbak.exe` transmitida via SSE (Server-Sent Events)
- **Histórico** de execuções com tamanho, duração e log completo
- **Autenticação** — senha de admin definida no instalador (PBKDF2-SHA256)
- **Logo customizável** — troca favicon e banner do painel lateral
- **Windows Service** — inicia automaticamente com o sistema

---

## Stack

| Camada | Tecnologia |
|---|---|
| Backend | Python 3.12 + FastAPI + Uvicorn |
| Agendamento | APScheduler 3.10 (BackgroundScheduler) |
| Banco local | SQLite via SQLModel / SQLAlchemy |
| Criptografia | cryptography (Fernet) + stdlib PBKDF2 |
| Serviço Windows | pywin32 (ServiceFramework) |
| Frontend | HTML5 + CSS3 + Vanilla JS (single-file SPA) |
| Empacotamento | PyInstaller 6 (onedir) |
| Instalador | Inno Setup 6 |

---

## Build

### Pré-requisitos

| Requisito | Observação |
|---|---|
| Linux (host de build) | Ubuntu / Zorin / Debian / Fedora |
| `wine` | `sudo apt install wine` |
| Python 3.12 Windows | Baixado automaticamente |
| Inno Setup 6.7 | Baixado automaticamente |

### Executar

```bash
chmod +x build.sh
./build.sh
```

O script realiza automaticamente:

1. Inicializa o prefixo Wine se necessário
2. Baixa e instala **Python 3.12.10 Windows** (se ausente)
3. Baixa e instala **Inno Setup 6.7.1** (se ausente)
4. Instala as dependências Python via pip
5. Gera `dist/fb_backup_manager/fb_backup_manager.exe` via PyInstaller
6. Gera `dist/FBBackupManager_Setup_1.0.0.exe` via Inno Setup

Os instaladores são mantidos em cache em `.build-cache/` para builds subsequentes.

---

## Instalação no Windows

1. Copie `FBBackupManager_Setup_1.0.0.exe` para a máquina Windows
2. Execute como **Administrador**
3. Defina a senha de acesso no assistente de instalação (mín. 4 caracteres)
4. Acesse **http://localhost:8099** no browser ao final

> **Atualização:** o instalador para o serviço existente e recria o banco de dados. Reconfigure as conexões após atualizar.

---

## Desenvolvimento local (Linux)

```bash
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

uvicorn backend.main:app --reload --port 8099
```

> `pywin32` não é instalado no Linux — o código de serviço Windows é ignorado automaticamente.

---

## Estrutura do Projeto

```
fb-backup-manager/
├── backend/
│   ├── main.py          # FastAPI app + lifespan + CLI args
│   ├── models.py        # SQLModel (tabelas SQLite)
│   ├── database.py      # engine, sessões, criptografia, auth
│   ├── auth.py          # session store em memória
│   ├── backup.py        # lógica gbak, SSE stream, retenção
│   ├── scheduler.py     # APScheduler wrapper
│   ├── service.py       # Windows Service (pywin32)
│   └── routers/
│       ├── auth.py      # login, logout, troca de senha
│       ├── connections.py
│       ├── backups.py   # logs + SSE stream
│       ├── scheduler.py
│       └── config.py    # porta, status, logo
├── frontend/
│   └── index.html       # SPA single-file
├── docs/                # Documentação (Obsidian)
├── build.sh             # Script de build Linux → Wine → Windows
├── installer.iss        # Script Inno Setup
├── requirements.txt
└── .build-cache/        # Cache de instaladores (gerado pelo build.sh)
```

---

## Gerenciamento do Serviço Windows

```cmd
sc query FBBackupManager                          :: status
net start FBBackupManager                         :: iniciar
net stop FBBackupManager                          :: parar
fb_backup_manager.exe --service install           :: registrar serviço
fb_backup_manager.exe --service remove            :: remover serviço
fb_backup_manager.exe --admin-password "senha"    :: redefinir senha admin
```

---

## Variáveis de Ambiente

| Variável | Padrão | Descrição |
|---|---|---|
| `FB_DATA_DIR` | `<pasta do exe>\data` | Diretório do banco SQLite e logo |
| `WINEPREFIX` | `~/.wine` | Prefixo Wine usado pelo build.sh |

---

## Logs

Arquivo: `fb_backup_manager.log` — rotativo, máx. 10 MB, 3 cópias.

---

## Licença

MIT — veja [LICENSE](LICENSE).
