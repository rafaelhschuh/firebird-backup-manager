---
title: Uso
tags:
  - fb-backup-manager
  - uso
  - interface
---

# Uso da Interface Web

![[index|← Voltar ao índice]]

Acesse **http://localhost:8099** após a instalação.

---

## Dashboard

A tela inicial exibe um card por conexão cadastrada com:

- **Status** do último backup (✓ Sucesso / ✗ Falha / ⏳ Executando / Sem backup)
- **Tamanho** do último arquivo `.fbk` gerado
- **Próxima execução** agendada
- Botão **▶ Executar agora** para backup imediato

---

## Conexões

Gerencia os bancos Firebird que serão copiados.

### Cadastrar uma conexão

1. Clique em **+ Nova Conexão**
2. Preencha os campos:

| Campo | Descrição | Exemplo |
|---|---|---|
| **Nome** | Identificação amigável | `Servidor Principal` |
| **Host** | IP ou hostname do servidor Firebird | `192.168.1.10` |
| **Porta** | Porta TCP do Firebird (padrão 3050) | `3050` |
| **Caminho do banco** | Path do `.fdb` no servidor | `C:\dados\banco.fdb` |
| **Usuário** | Usuário Firebird | `SYSDBA` |
| **Senha** | Senha Firebird (criptografada ao salvar) | `masterkey` |
| **Destino dos backups** | Pasta local onde os `.fbk` serão salvos | `C:\Backups\Firebird` |
| **Retenção** | Quantas cópias manter (as mais antigas são apagadas) | `7` |
| **Caminho do gbak.exe** | Path completo do gbak.exe *(obrigatório)* | `C:\Program Files\Firebird\Firebird_3_0\gbak.exe` |

> [!warning] gbak.exe obrigatório
> O campo **Caminho do gbak.exe** é obrigatório. Sem ele o backup não executa.
> Localize o `gbak.exe` na pasta de instalação do Firebird do servidor.

> [!tip] URL completa
> Alterne para **Usar URL completa** se preferir digitar a connection string diretamente no formato `host/porta:caminho`.

### Editar / Excluir

- **Editar**: botão na linha da tabela. Deixe o campo senha em branco para não alterá-la.
- **Excluir**: remove a conexão e todos os agendamentos associados.

---

## Agendamentos

Agrupa conexões em um horário de execução nomeado.

### Criar um agendamento

1. Clique em **+ Novo Agendamento**
2. Defina:
   - **Nome**: ex. `Backup da noite`, `Backup semanal`
   - **Hora** e **Minuto** da execução
   - **Dias da semana** (checkboxes Seg–Dom)
   - **Conexões**: marque todas as conexões que devem ser copiadas neste horário

> [!example] Exemplo
> Agendamento **"Backup da noite"** às **02:00**, dias úteis (Seg–Sex), com 3 conexões selecionadas → o sistema executa os 3 backups em sequência toda madrugada.

- O próximo horário de execução é exibido em cada card de agendamento.
- O toggle **Ativo/Inativo** suspende o agendamento sem apagá-lo.

---

## Executar backup manual

No **Dashboard**, clique em **▶ Executar agora** em qualquer conexão.

Um popup se abre com o **terminal de saída em tempo real** do `gbak`:

```
→ Iniciando backup de: Servidor Principal
gbak:readied database C:\dados\banco.fdb for backup
gbak:creating file C:\Backups\Firebird\servidor_principal_20260514_0200.fbk
gbak:starting backup phase 1
...
✓ Backup concluído — 128.45 MB em 42.3s
```

> [!tip] Diagnóstico de erros
> A saída completa do gbak fica registrada no [[uso#Histórico|Histórico]], facilitando a identificação de problemas.

---

## Histórico

Tabela com todos os backups executados (manuais e agendados).

| Coluna | Descrição |
|---|---|
| Data/Hora | Quando o backup iniciou |
| Conexão | Nome da conexão |
| Status | SUCCESS / FAILED / RUNNING |
| Tamanho | Tamanho do `.fbk` gerado |
| Duração | Tempo total de execução |
| Saída / Erro | Botão **▼ ver saída** para expandir o log completo do gbak |

> [!tip] Filtro por conexão
> Use o seletor no topo para filtrar os registros de uma conexão específica.

---

## Configurações

| Campo | Descrição |
|---|---|
| **Porta da Aplicação** | Porta HTTP onde a UI é servida (padrão: 8099) |
| **Reiniciar Serviço** | Aplica mudanças que requerem reinício |
| **Versão / Uptime / Status** | Informações do serviço Windows |

> [!warning] Mudança de porta
> Após alterar a porta e salvar, clique em **Reiniciar Serviço**. A UI ficará indisponível por alguns segundos — acesse pelo novo endereço em seguida.

---

## Próximos passos

→ [[arquitetura|Arquitetura do projeto]]
→ [[api|API Reference]]
