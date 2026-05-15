---
title: Instalação
tags:
  - fb-backup-manager
  - instalação
  - windows
---

# Instalação

![[index|← Voltar ao índice]]

## Pré-requisitos

- Windows 10 ou Windows Server 2016+
- Permissão de **Administrador** para instalar o serviço
- **Firebird** instalado na máquina servidora dos bancos
- O arquivo `gbak.exe` acessível (geralmente em `C:\Program Files\Firebird\Firebird_X_X\`)

---

## Instalação via Instalador

> [!tip] Método recomendado
> Use o instalador `.exe` gerado pelo [[build|build.sh]]. Ele configura tudo automaticamente.

1. Copie `FBBackupManager_Setup_1.0.0.exe` para a máquina Windows
2. Execute como **Administrador**
3. Siga o assistente de instalação em PT-BR
4. Ao final, o instalador:
   - Instala os arquivos em `C:\Program Files\FBBackupManager\`
   - Registra e inicia o serviço Windows `FBBackupManager`
   - Cria atalho no Menu Iniciar que abre `http://localhost:8099`

> [!warning] Atualização
> Ao atualizar de uma versão anterior, o instalador para o serviço existente e **apaga o banco de dados** (`data\fb_backup.db`) automaticamente, pois o schema pode ter mudado. Reconfigure as conexões e agendamentos após a atualização.

---

## Primeira Execução

Na primeira inicialização o app:

1. Cria o banco SQLite em `<pasta de instalação>\data\fb_backup.db`
2. Gera uma `app_secret_key` aleatória (usada para criptografar senhas)
3. Registra o serviço Windows

Acesse a interface em **http://localhost:8099** para começar a configurar.

---

## Gerenciamento do Serviço Windows

| Ação | Comando |
|---|---|
| Verificar status | `sc query FBBackupManager` |
| Iniciar | `net start FBBackupManager` |
| Parar | `net stop FBBackupManager` |
| Instalar manualmente | `fb_backup_manager.exe --service install` |
| Remover | `fb_backup_manager.exe --service remove` |

> [!note] Services.msc
> Também é possível gerenciar o serviço pelo painel `services.msc` do Windows (Serviços). O serviço aparece como **FB Backup Manager**.

---

## Estrutura de Arquivos Instalados

```
C:\Program Files\FBBackupManager\
├── fb_backup_manager.exe   ← executável principal
├── fb_backup_manager.log   ← log rotativo (10 MB, 3 cópias)
├── open_ui.url             ← atalho para http://localhost:8099
└── data\
    └── fb_backup.db        ← banco SQLite (conexões, logs, config)
```

> [!warning] Pasta data\
> **Não apague** a pasta `data\` enquanto o serviço estiver rodando. Os arquivos `.fbk` de backup ficam nas pastas configuradas em cada conexão, não aqui.

---

## Desinstalação

1. Painel de Controle → Programas → **FB Backup Manager** → Desinstalar
2. O desinstalador para e remove o serviço Windows automaticamente

> [!tip]
> Os arquivos `.fbk` de backup **não são apagados** na desinstalação — eles ficam nas pastas que você configurou em cada conexão.

---

## Próximo passo

→ [[uso|Como usar a interface web]]
