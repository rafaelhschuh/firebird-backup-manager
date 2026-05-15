---
title: Restore
tags:
  - fb-backup-manager
  - restore
  - recuperação
---

# Restore

![[index|← Voltar ao índice]]

A seção **Restore** da interface permite restaurar bancos Firebird a partir de arquivos `.fbk` gerados pelo sistema.

---

## Tipos de Restore

### 1. Banco da Conexão

Restaura um `.fbk` **sobre o banco de uma conexão existente**, substituindo o arquivo `.fdb` atual.

**Quando usar:** recuperação após falha, reversão para estado anterior.

**Fluxo:**
1. Selecione a conexão
2. Escolha o backup disponível na lista (apenas backups com status `SUCCESS`)
3. Opcionalmente ative "Criar cópia de segurança (.fdb.bkp) antes"
4. Clique em **Restaurar Banco**
5. Acompanhe o progresso em tempo real no terminal

> O sistema executa internamente:
> ```
> gbak.exe -rep -v -user SYSDBA -password *** backup.fbk host/3050:banco.fdb
> ```

### 2. Restore Simples

Restaura um `.fbk` para **qualquer caminho** no servidor Firebird, sem alterar o banco da conexão selecionada.

**Quando usar:** criar uma cópia do banco em novo local, testar um backup antes de sobrescrever o banco de produção.

**Campos:**
- **Conexão (servidor):** apenas para autenticação — `host`, `porta`, `usuário` e `senha` são reutilizados
- **Caminho do .fbk de origem:** caminho local na máquina onde o manager roda
- **Caminho de destino .fdb (no servidor):** caminho no sistema de arquivos do servidor Firebird

> O sistema executa internamente:
> ```
> gbak.exe -cre -v -user SYSDBA -password *** source.fbk host/3050:destino.fdb
> ```

---

## Cópia de Segurança (.fdb.bkp)

Antes de um restore do tipo **Banco da Conexão**, o sistema pode criar automaticamente uma cópia do arquivo `.fdb` atual:

```
banco.fdb  →  banco.fdb.bkp
```

- **Habilitado por padrão** — recomendado para produção
- Pode ser desabilitado desmarcando o toggle na interface
- Assume que o caminho `db_path` da conexão é acessível como arquivo local na máquina onde o manager roda (mesmo host que o Firebird, ou unidade de rede mapeada)

Para reverter manualmente:
```cmd
copy banco.fdb.bkp banco.fdb
```

---

## Histórico de Restores

Todas as operações de restore são registradas na tabela `RestoreLog` e exibidas na parte inferior da seção Restore, com:

- Data/hora de início
- Conexão utilizada
- Tipo (Banco da Conexão / Simples)
- Status (RUNNING / SUCCESS / FAILED)
- Duração
- Mensagem de erro (se houver)

---

## API

| Endpoint | Método | Descrição |
|---|---|---|
| `/api/restore/{connection_id}/files` | GET | Lista backups disponíveis para uma conexão |
| `/api/restore/{connection_id}/run` | GET (SSE) | Restore sobre o banco da conexão |
| `/api/restore/simple/run` | GET (SSE) | Restore simples para caminho customizado |
| `/api/restore/logs` | GET | Histórico de restores |

Parâmetros do endpoint de restore por conexão:
- `fbk_path` — caminho do arquivo `.fbk`
- `skip_safety_backup` — `true` para pular cópia de segurança (padrão: `false`)
- `token` — token de autenticação (necessário para EventSource)

Parâmetros do restore simples:
- `server_connection_id` — ID da conexão cujo servidor será usado
- `fbk_path` — caminho do arquivo `.fbk`
- `target_db_path` — caminho destino no servidor Firebird
- `token` — token de autenticação
