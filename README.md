# Poliedro P+ para CLaude ou ChatGPT

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

API REST e servidor MCP **não oficial** para consultar notas, mensagens e calendário do portal [Poliedro P+](https://pmais.p4ed.com/) através do Claude ou ChatGPT.

> Este projeto **não é afiliado** ao Poliedro Sistema de Ensino. Código aberto — use por sua conta e risco, respeitando os termos do portal P+.

## O que faz

- Boletim / notas
- Mensagens e notificações
- Calendário escolar (próximos eventos, semana, mês, ano)
- Integração com **ChatGPT** (Actions + OAuth)
- Integração com **Claude** (MCP remoto via Custom Connector — recomendado — ou MCP local no Desktop)

## Integrações

| Cliente | Como conectar | OAuth |
|---------|---------------|-------|
| **Claude** (web/app) | Custom Connector → `https://SEU-APP.onrender.com/mcp` | Automático (DCR) — só login P+ |
| **ChatGPT** | Custom GPT → Actions + `openapi.json` | Manual (Client ID/Secret) |
| **Claude Desktop** | MCP local (`python -m poliedro_mcp.server`) | Keychain no Mac |

## Como funciona

Em ambos os casos, o usuário autentica com **usuário e senha do P+** (mesmos do [pmais.p4ed.com](https://pmais.p4ed.com/)). A API valida **diretamente no Poliedro**, obtém um token JWT temporário e consulta boletim, mensagens e calendário **em nome do usuário logado**. Cada pessoa vê **apenas os próprios dados** — não há conta compartilhada no servidor.

**ChatGPT (Actions):**

```
Sign in → /oauth/authorize → login P+ → token OAuth → /api/v1/*
```

**Claude (MCP remoto):**

```
Add connector → /mcp → OAuth automático → /mcp/login → ferramentas MCP (get_grades, …)
```

Guias: [ChatGPT](docs/chatgpt-setup.md) · [Claude MCP remoto](docs/claude-remote-setup.md)

## Privacidade — nada é armazenado no servidor

**Em produção (API no Render — ChatGPT OAuth ou Claude MCP):**

| Dado | Armazenado? |
|------|-------------|
| Senha do P+ | **Não** — usada só no momento do login e descartada |
| Usuário / e-mail | **Não** — não há banco de dados |
| Credenciais em disco ou logs | **Não** |
| Token JWT do Poliedro | **Só em memória**, pelo tempo da sessão OAuth (minutos) |

O login autentica **diretamente nos servidores do Poliedro**. Este projeto atua como ponte: recebe a senha, repassa ao P+ para validar e **não persiste** em hipótese alguma.

**Uso local (Claude Desktop / MCP):** opcionalmente a senha pode ficar no **Keychain do seu Mac** (`setup_login`) — isso é **só na sua máquina**, não no servidor.

## ChatGPT — início rápido

1. Faça deploy no [Render](https://render.com) (blueprint `render.yaml`)
2. Defina `OAUTH_CLIENT_SECRET` no Render (`openssl rand -hex 32`)
3. Gere os valores OAuth:

```bash
python print_oauth_config.py https://SEU-APP.onrender.com
```

4. No Custom GPT → **Actions → Authentication → OAuth**:

| Campo | Valor |
|-------|--------|
| Client ID | `poliedro-gpt` |
| Client Secret | mesmo do Render |
| Authorization URL | `https://SEU-APP.onrender.com/oauth/authorize` |
| Token URL | `https://SEU-APP.onrender.com/oauth/token` |
| Scope | `openid profile email` |

5. Importe o schema: `https://SEU-APP.onrender.com/openapi.json`

O **Scope** não é seu e-mail — são permissões padrão OAuth (`openid`, `profile`, `email`).

**Publicar o GPT:** use `https://SEU-APP.onrender.com/privacy` como Privacy policy URL.

## Claude — MCP remoto (recomendado)

Funciona no **Claude web e app** via Custom Connectors — sem instalar nada no Mac e **sem** configurar Client ID/Secret (o servidor registra o cliente automaticamente via DCR).

1. Faça deploy no Render (mesmo app do ChatGPT; defina `OAUTH_CLIENT_SECRET` e `API_BASE_URL`)
2. Confira a URL do conector:

```bash
python print_oauth_config.py https://SEU-APP.onrender.com
```

3. No Claude → **Settings → Connectors → Add custom connector**
4. **Connector URL:** `https://SEU-APP.onrender.com/mcp`
5. Conecte → faça login com usuário e senha do P+ (usuário **sem** `@p4ed.com`)
6. Se tiver várias escolas ou dependentes, preencha na tela de login

**Ferramentas MCP:** `get_grades`, `get_messages`, `get_unread_messages`, `get_next_events`, calendário (semana/mês/ano), `poliedro_health_check`.

Guia completo e troubleshooting: [docs/claude-remote-setup.md](docs/claude-remote-setup.md)

## Claude Desktop (MCP local)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && pip install -e .
cp config/config.example.json config/config.json
python -m poliedro_mcp.setup_login   # salva senha no Keychain (local)
python -m poliedro_mcp.server
```

Configuração do Claude: [docs/claude-desktop-config.example.json](docs/claude-desktop-config.example.json)

## Endpoints principais

| Caminho | Descrição |
|---------|-----------|
| `GET /oauth/authorize` | Tela de login P+ (ChatGPT) |
| `POST /oauth/token` | Token OAuth (ChatGPT) |
| `POST /mcp` | MCP Streamable HTTP (Claude Connectors) |
| `POST /mcp/register` | Dynamic Client Registration (Claude) |
| `GET /mcp/authorize` | Início do OAuth MCP |
| `POST /mcp/login` | Login P+ no fluxo MCP |
| `POST /mcp/token` | Token OAuth MCP |
| `GET /.well-known/oauth-authorization-server/mcp` | Metadados OAuth MCP (Claude) |
| `GET /api/v1/grades` | Boletim (ChatGPT Actions) |
| `GET /api/v1/messages` | Mensagens |
| `GET /api/v1/calendar/*` | Calendário |

Documentação interativa: `/docs` · OpenAPI (ChatGPT): `/openapi.json`

## Variáveis de ambiente (Render)

| Variável | Obrigatória | Descrição |
|----------|-------------|-----------|
| `OAUTH_CLIENT_SECRET` | Sim | Secret do OAuth |
| `OAUTH_CLIENT_ID` | Não | Padrão: `poliedro-gpt` |
| `API_BASE_URL` | Sim (produção) | URL pública do app — usada nos metadados OAuth/MCP |

Não é necessário `POLIEDRO_TOKEN` nem `POLIEDRO_CONFIG_JSON` no modo OAuth/MCP remoto.

## Problemas comuns (Claude MCP)

| Sintoma | O que fazer |
|---------|-------------|
| Login retorna erro | Use as mesmas credenciais do `pmais.p4ed.com` (usuário sem `@p4ed.com`) |
| Várias escolas/dependentes | Preencha School ID e Dependent ID na tela `/mcp/login` |
| "Authorization failed" após login | Remova o conector, faça redeploy e crie de novo |
| Conector não registra OAuth | Confirme `curl …/.well-known/oauth-authorization-server/mcp` |

## Desenvolvimento local

```bash
source .venv/bin/activate && pip install -e .
export OAUTH_CLIENT_SECRET=dev-secret
export API_BASE_URL=http://localhost:8000
uvicorn poliedro_mcp.api:app --reload --port 8000
```

Validar: `python -m poliedro_mcp.cli health`

## Licença

[MIT License](LICENSE) — código open source. O uso do portal P+ continua sujeito aos termos do Poliedro.
