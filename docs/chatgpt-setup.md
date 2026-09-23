# Configurar o ChatGPT (plugin MCP)

O ChatGPT consulta o P+ pelo mesmo MCP do Claude. O plugin não usa Actions, `openapi.json` nem Client ID/Secret.

## Pré-requisitos

1. API publicada no Render
2. No Render: `OAUTH_CLIENT_SECRET` e `API_BASE_URL=https://poliedro-api.iden.is`

`OAUTH_CLIENT_SECRET` fica só no servidor. Não cole esse valor no ChatGPT.

## Conectar

1. ChatGPT → **Settings → Security and login** → ligue **Developer mode**
2. **Plugins → +**
3. URL:

```
https://poliedro-api.iden.is/mcp
```

4. Crie a conexão e faça login com usuário e senha do [pmais.p4ed.com](https://pmais.p4ed.com/) (usuário sem `@p4ed.com`)
5. Se a conta tiver várias escolas ou dependentes, escolha na tela de login

Confirme que a API responde:

```bash
curl -s https://poliedro-api.iden.is/health
curl -s https://poliedro-api.iden.is/.well-known/oauth-authorization-server/mcp
```

O JSON do segundo comando precisa trazer `registration_endpoint`.

## Migrar um Custom GPT

*Migrate to plugin* copia instruções e arquivos de conhecimento. Três coisas não vêm:

- **Actions** (OpenAPI + OAuth manual). O aviso *Unsupported actions* é esperado. Sem conectar `/mcp`, o plugin não consulta o P+.
- Conversas antigas
- Compartilhamento público. O plugin fica privado, e o GPT original deixa de ser editável

## Ferramentas

| Tool | Descrição |
|------|-----------|
| `get_grades` | Boletim / notas |
| `get_simulation_grades` | Simulado — resumo |
| `list_simulation_assessments` | Simulado — listagem com `assessment_id` |
| `get_simulation_performance` | Simulado — detalhe por matéria |
| `get_messages` / `get_unread_messages` | Mensagens |
| `get_message_detail` | Texto completo (`announcement_id` de `get_messages`) |
| `get_next_events` | Próximos eventos |
| `get_week_events` / `get_month_events` / `get_year_events` | Calendário |
| `poliedro_health_check` | Status da conexão |

## Actions (GPT antigo)

A API REST em `/api/v1/*` e o OAuth em `/oauth/authorize` continuam no ar enquanto um Custom GPT ainda não migrado precisar deles. O plugin novo não usa esse fluxo. Client ID padrão: `poliedro-gpt`.
