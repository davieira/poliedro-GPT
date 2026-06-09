# Claude — MCP remoto (Custom Connector)

Use o Poliedro MCP na nuvem, sem instalar nada no Mac. Funciona em **Claude** (web/app) via **Custom Connectors**.

## Pré-requisitos

1. API publicada (ex.: Render com `render.yaml`)
2. `OAUTH_CLIENT_SECRET` definido no Render (necessário para a API, mas **não** para o conector Claude)

## URL do conector

```
https://SEU-APP.onrender.com/mcp
```

Para conferir após o deploy:

```bash
python print_oauth_config.py https://SEU-APP.onrender.com
```

A seção **MCP remoto (Claude Connectors)** mostra a URL exata.

## Configurar no Claude

1. Abra **Settings** → **Connectors** (ou **Integrations**)
2. **Add custom connector**
3. Cole a **Connector URL**: `https://SEU-APP.onrender.com/mcp`
4. Salve e conecte — o Claude abre o fluxo OAuth automaticamente
5. Faça login com **usuário e senha do P+** (`pmais.p4ed.com`)
6. Se tiver várias escolas/dependentes, escolha na tela de login

Não é preciso informar Client ID, Client Secret nem URLs de token — o MCP usa **Dynamic Client Registration (DCR)**.

## Ferramentas disponíveis

| Tool | Descrição |
|------|-----------|
| `get_grades` | Boletim / notas |
| `get_messages` / `get_unread_messages` | Mensagens |
| `get_next_events` | Próximos eventos |
| `get_week_events` / `get_month_events` / `get_year_events` | Calendário |
| `poliedro_health_check` | Status da conexão |

## Privacidade

Igual ao ChatGPT OAuth:

- Senha **não** é armazenada — só usada no login e descartada
- Token JWT do Poliedro fica **em memória** na sessão
- Cada usuário vê apenas os próprios dados

## Diferença: MCP local vs remoto

| | MCP local (Desktop) | MCP remoto (Connector) |
|--|---------------------|------------------------|
| Onde roda | Seu Mac (`python -m poliedro_mcp.server`) | API no Render |
| Login | Keychain (`setup_login`) | OAuth na web |
| Claude | Desktop only | Web + app (Connectors) |
| ChatGPT | — | REST + OAuth Actions |

## Troubleshooting

**Conector não conecta**

- Confirme que a API responde: `curl https://SEU-APP.onrender.com/health`
- Metadados MCP: `curl https://SEU-APP.onrender.com/.well-known/oauth-protected-resource/mcp`

**Login expirou**

- Reconecte o conector no Claude e faça login de novo

**Várias escolas/dependentes**

- Na tela de login, selecione escola e/ou dependente antes de continuar
