# Poliedro API & MCP

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

API REST e servidor MCP **não oficial** para consultar notas, mensagens e calendário do portal [Poliedro P+](https://pmais.p4ed.com/).

> Este projeto **não é afiliado** ao Poliedro Sistema de Ensino. Código aberto — use por sua conta e risco, respeitando os termos do portal P+.

## O que faz

- Boletim / notas
- Mensagens e notificações
- Calendário escolar (próximos eventos, semana, mês, ano)
- Integração com **ChatGPT** (OAuth — cada usuário com sua conta)
- Integração com **Claude Desktop** (MCP local)

## Como funciona

```
Usuário no ChatGPT
    → clica "Sign in"
    → tela de login P+ (sua API)
    → autentica nos servidores do Poliedro
    → recebe token JWT temporário
    → consulta notas, mensagens e calendário
```

1. O usuário entra com **usuário e senha do P+** (mesmos do `pmais.p4ed.com`).
2. A API valida as credenciais **diretamente no Poliedro** e obtém um token JWT.
3. Com esse token, a API consulta boletim, mensagens e calendário **em nome do usuário logado**.
4. Cada pessoa vê **apenas os próprios dados** — não há conta compartilhada no servidor.

Guia completo do ChatGPT: [docs/chatgpt-setup.md](docs/chatgpt-setup.md)

## Privacidade — nada é armazenado no servidor

**Em produção (API no Render + OAuth do ChatGPT):**

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
| `GET /oauth/authorize` | Tela de login P+ |
| `POST /oauth/token` | Token OAuth (ChatGPT) |
| `GET /api/v1/grades` | Boletim |
| `GET /api/v1/messages` | Mensagens |
| `GET /api/v1/calendar/*` | Calendário |

Documentação interativa: `/docs` · OpenAPI: `/openapi.json`

## Variáveis de ambiente (Render)

| Variável | Obrigatória | Descrição |
|----------|-------------|-----------|
| `OAUTH_CLIENT_SECRET` | Sim | Secret do OAuth |
| `OAUTH_CLIENT_ID` | Não | Padrão: `poliedro-gpt` |
| `API_BASE_URL` | Recomendado | URL pública do app |

Não é necessário `POLIEDRO_TOKEN` nem `POLIEDRO_CONFIG_JSON` no modo OAuth.

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
