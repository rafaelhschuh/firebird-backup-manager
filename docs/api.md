---
title: API Reference
tags:
  - fb-backup-manager
  - api
  - endpoints
---

# API Reference

![[index|← Voltar ao índice]]

Base URL: `http://localhost:8099/api`

Todos os endpoints retornam JSON. Erros retornam `{"detail": "mensagem"}`.

---

## Conexões

### `GET /api/connections`

Lista todas as conexões cadastradas.

**Response** `200 OK`
```json
[
  {
    "id": 1,
    "name": "Servidor Principal",
    "host": "192.168.1.10",
    "port": 3050,
    "db_path": "C:\\dados\\banco.fdb",
    "username": "SYSDBA",
    "backup_path": "C:\\Backups\\Firebird",
    "retention_count": 7,
    "gbak_path": "C:\\Program Files\\Firebird\\Firebird_3_0\\gbak.exe",
    "enabled": true
  }
]
```

> [!note] Senha nunca exposta
> O campo `password` **não** é incluído na resposta. A senha fica criptografada no banco e nunca trafega pela API.

---

### `POST /api/connections`

Cria uma nova conexão. A senha é criptografada com Fernet antes de persistir.

**Request body**
```json
{
  "name": "Servidor Principal",
  "host": "192.168.1.10",
  "port": 3050,
  "db_path": "C:\\dados\\banco.fdb",
  "username": "SYSDBA",
  "password": "masterkey",
  "backup_path": "C:\\Backups\\Firebird",
  "retention_count": 7,
  "gbak_path": "C:\\Program Files\\Firebird\\Firebird_3_0\\gbak.exe",
  "enabled": true
}
```

| Campo | Obrigatório | Padrão |
|---|---|---|
| `name` | sim | — |
| `host` | sim | — |
| `port` | não | `3050` |
| `db_path` | sim | — |
| `username` | sim | — |
| `password` | sim | — |
| `backup_path` | sim | — |
| `retention_count` | não | `7` |
| `gbak_path` | não | `null` |
| `enabled` | não | `true` |

**Response** `201 Created` — objeto `ConnectionOut`

---

### `PUT /api/connections/{id}`

Atualiza campos de uma conexão existente. Todos os campos são opcionais (PATCH semântico).

Para **não alterar a senha**, omita o campo `password` no body.

**Response** `200 OK` — objeto `ConnectionOut` atualizado

**Erros**
- `404` — conexão não encontrada

---

### `DELETE /api/connections/{id}`

Remove a conexão e todos os vínculos em `ScheduleConnection`.

**Response** `204 No Content`

**Erros**
- `404` — conexão não encontrada

---

## Agendamentos

### `GET /api/schedules`

Lista todos os agendamentos com suas conexões vinculadas e próxima execução.

**Response** `200 OK`
```json
[
  {
    "id": 1,
    "name": "Backup da noite",
    "cron_hour": 2,
    "cron_minute": 0,
    "days_of_week": "0,1,2,3,4",
    "enabled": true,
    "next_run": "2026-05-15T02:00:00+00:00",
    "connection_ids": [1, 2, 3]
  }
]
```

`next_run` é `null` se o agendamento estiver desativado ou não tiver job registrado.

---

### `POST /api/schedules`

Cria um agendamento e registra o job no APScheduler.

**Request body**
```json
{
  "name": "Backup da noite",
  "cron_hour": 2,
  "cron_minute": 0,
  "days_of_week": "0,1,2,3,4",
  "enabled": true,
  "schedule_type": "BACKUP",
  "connection_ids": [1, 2]
}
```

| Campo | Obrigatório | Padrão |
|---|---|---|
| `name` | sim | — |
| `cron_hour` | sim | — |
| `cron_minute` | sim | — |
| `days_of_week` | não | `"0,1,2,3,4,5,6"` |
| `enabled` | não | `true` |
| `schedule_type` | não | `"BACKUP"` |
| `connection_ids` | não | `[]` |

`schedule_type`: `"BACKUP"` executa backup; `"REINDEX"` executa ciclo backup→restore para reindexação.

> [!example] Formato days_of_week
> String de dígitos separados por vírgula: `0`=Seg, `1`=Ter, …, `6`=Dom.
> Dias úteis: `"0,1,2,3,4"` | Fim de semana: `"5,6"` | Todos: `"0,1,2,3,4,5,6"`

**Response** `201 Created` — objeto `ScheduleOut`

---

### `PUT /api/schedules/{id}`

Atualiza agendamento e re-registra o job. Se `enabled=false`, o job é removido do APScheduler.

**Request body** — mesmos campos do `POST`, todos opcionais.

Se `connection_ids` for enviado (mesmo vazio `[]`), **substitui** todos os vínculos existentes.
Se omitido, os vínculos atuais são mantidos.

**Response** `200 OK` — objeto `ScheduleOut` atualizado

**Erros**
- `404` — agendamento não encontrado

---

### `DELETE /api/schedules/{id}`

Remove o agendamento, seus vínculos e o job do APScheduler.

**Response** `204 No Content`

**Erros**
- `404` — agendamento não encontrado

---

## Backups

### `GET /api/logs`

Retorna o histórico de backups, ordenado do mais recente para o mais antigo.

**Query params**

| Parâmetro | Tipo | Padrão | Descrição |
|---|---|---|---|
| `connection_id` | int | — | Filtra por conexão específica |
| `limit` | int | `50` | Máximo de registros retornados |

**Response** `200 OK`
```json
[
  {
    "id": 42,
    "connection_id": 1,
    "started_at": "2026-05-14T02:00:01.123456",
    "finished_at": "2026-05-14T02:00:43.789012",
    "status": "SUCCESS",
    "fbk_path": "C:\\Backups\\Firebird\\servidor_principal_20260514_0200.fbk",
    "fbk_size_bytes": 134742016,
    "duration_seconds": 42.7,
    "error_message": null,
    "gbak_output": "gbak:readied database...\n..."
  }
]
```

Valores de `status`: `SUCCESS` | `FAILED` | `RUNNING`

---

### `GET /api/backups/{connection_id}/run`

Executa o backup da conexão e transmite a saída do `gbak` em tempo real via **SSE (Server-Sent Events)**.

**Response** `200 OK` com `Content-Type: text/event-stream`

Cada evento é uma linha JSON no formato:
```
data: {"type": "output", "line": "gbak:readied database..."}

data: {"type": "output", "line": "gbak:creating file C:\\..."}

data: {"type": "done", "status": "SUCCESS", "size_bytes": 134742016, "duration": 42.7}
```

Em caso de erro:
```
data: {"type": "error", "message": "gbak retornou código 1. ..."}
```

> [!tip] Consumindo o SSE no frontend
> ```js
> const src = new EventSource(`/api/backups/${id}/run`);
> src.onmessage = ({ data }) => {
>   const ev = JSON.parse(data);
>   if (ev.type === 'output') appendLine(ev.line);
>   if (ev.type === 'done' || ev.type === 'error') src.close();
> };
> ```

> [!warning] Sem retry automático
> Ao receber `type: done` ou `type: error`, feche a conexão SSE explicitamente (`src.close()`). O `EventSource` tentará reconectar automaticamente se a conexão for encerrada sem esse tratamento, disparando múltiplos backups.

**Erros**
- `404` — conexão não encontrada

---

## Configuração

### `GET /api/config`

Retorna a configuração atual da aplicação.

**Response** `200 OK`
```json
{
  "app_port": 8099
}
```

---

### `PUT /api/config`

Atualiza a configuração. Atualmente suporta apenas `app_port`.

**Request body**
```json
{
  "app_port": 9000
}
```

**Response** `200 OK` — objeto `ConfigOut` atualizado

> [!warning] Mudança de porta
> A nova porta só entra em vigor após reiniciar o serviço. O endpoint `/api/status` expõe um botão de reinício na UI.

---

### `GET /api/status`

Retorna informações do serviço em execução.

**Response** `200 OK`
```json
{
  "version": "1.0.0",
  "uptime_seconds": 3661.4,
  "service_status": "running"
}
```

| Campo | Descrição |
|---|---|
| `version` | Versão hardcoded da aplicação |
| `uptime_seconds` | Segundos desde o início do processo |
| `service_status` | `"running"` \| `"stopped"` \| `"unknown"` \| `"N/A"` (Linux/dev) |

---

---

## Restore

### `GET /api/restore/{connection_id}/files`

Lista os backups disponíveis (status `SUCCESS`, arquivo existente em disco) para uma conexão.

**Response** `200 OK`
```json
[
  {
    "log_id": 42,
    "fbk_path": "C:\\Backups\\banco_20260514_0200.fbk",
    "started_at": "2026-05-14T02:00:01",
    "fbk_size_bytes": 134742016
  }
]
```

---

### `GET /api/restore/{connection_id}/run`

Executa restore de um `.fbk` sobre o banco da conexão. Responde via **SSE**.

**Query params**

| Parâmetro | Obrigatório | Padrão | Descrição |
|---|---|---|---|
| `fbk_path` | sim | — | Caminho do arquivo `.fbk` |
| `skip_safety_backup` | não | `false` | Pula cópia `.fdb.bkp` |
| `token` | sim | — | Token de autenticação |

---

### `GET /api/restore/simple/run`

Restore de um `.fbk` para qualquer caminho no servidor. Responde via **SSE**.

**Query params**

| Parâmetro | Obrigatório | Descrição |
|---|---|---|
| `server_connection_id` | sim | ID da conexão (credenciais do servidor) |
| `fbk_path` | sim | Caminho local do `.fbk` |
| `target_db_path` | sim | Caminho destino no servidor Firebird |
| `token` | sim | Token de autenticação |

---

### `GET /api/restore/logs`

Histórico de operações de restore.

**Query params:** `connection_id` (filtro), `limit` (padrão: 50)

---

## Manutenção

### `GET /api/maintenance/{connection_id}/reindex`

Executa reindexação completa (backup → restore) via **SSE**.

**Query params**

| Parâmetro | Obrigatório | Padrão | Descrição |
|---|---|---|---|
| `skip_safety_backup` | não | `false` | Pula cópia `.fdb.bkp` |
| `token` | sim | — | Token de autenticação |

---

### `GET /api/maintenance/logs`

Histórico de reindexações (registros de `BackupLog` com `operation_type = "REINDEX"`).

**Query params:** `connection_id` (filtro), `limit` (padrão: 50)

---

## Próximos passos

→ [[modelos|Modelos de Dados]]
→ [[restore|Restore]]
→ [[manutencao|Manutenção]]
→ [[build|Build e Distribuição]]
