---
title: Manutenção
tags:
  - fb-backup-manager
  - manutenção
  - reindexação
  - performance
---

# Manutenção

![[index|← Voltar ao índice]]

A seção **Manutenção** oferece a operação de **reindexação** do banco Firebird, que melhora a performance de consultas ao reconstruir completamente os índices internos.

---

## Reindexação

### Por que reindexar?

Com o uso contínuo do banco Firebird, os índices podem ficar fragmentados, impactando a performance de consultas. A técnica mais eficaz para reconstruir índices em Firebird é o ciclo **backup → restore** via `gbak`, que recria o banco do zero a partir do backup.

**Quando usar:**
- Performance degradada após muitas inserções/exclusões
- Após importação massiva de dados
- Manutenção preventiva periódica (ex: agendado semanalmente)

### Como funciona

O processo executa 2 fases em sequência:

```
Fase 0 (opcional): banco.fdb → banco.fdb.bkp    (cópia de segurança)
Fase 1: gbak -b → banco_reindex_temp.fbk         (backup temporário)
Fase 2: gbak -rep → banco_reindex_temp.fbk → banco.fdb  (restore sobre si mesmo)
        → remove banco_reindex_temp.fbk
```

> O banco ficará **brevemente indisponível** durante a Fase 2 (restore). Planeje a janela de manutenção.

### Realizando a reindexação manualmente

1. Acesse **Manutenção** no menu lateral
2. Selecione a conexão do banco a ser reindexado
3. Ative/desative "Criar .fdb.bkp antes" conforme necessário
4. Clique em **Reindexar Banco**
5. Acompanhe as duas fases no terminal em tempo real

### Agendando a reindexação

Na seção **Agendamentos**, ao criar ou editar um agendamento, selecione o tipo **Reindexação** (em vez de Backup). O agendamento executará o ciclo completo backup → restore no horário configurado.

---

## Cópia de Segurança (.fdb.bkp)

Antes da reindexação, o sistema pode copiar o `.fdb` atual para `.fdb.bkp`:
- **Habilitado por padrão** — recomendado
- Requer que `db_path` seja acessível como arquivo local
- Permite reversão manual em caso de falha

---

## Histórico de Reindexações

A fase de **backup** da reindexação é registrada em `BackupLog` com `operation_type = "REINDEX"`. O histórico é exibido na parte inferior da seção Manutenção.

---

## API

| Endpoint | Método | Descrição |
|---|---|---|
| `/api/maintenance/{connection_id}/reindex` | GET (SSE) | Executa reindexação completa |
| `/api/maintenance/logs` | GET | Histórico de reindexações |

Parâmetros:
- `skip_safety_backup` — `true` para pular cópia de segurança (padrão: `false`)
- `token` — token de autenticação (necessário para EventSource)
- `connection_id` — filtro opcional no endpoint de logs
