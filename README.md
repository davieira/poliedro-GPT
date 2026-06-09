# Poliedro API & MCP

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

API REST e servidor MCP **não oficial** para consultar informações do portal Poliedro/P+.
Este projeto não é afiliado, endossado ou mantido pelo Poliedro Sistema de Ensino.

Funcionalidades:

- Boletim / notas
- Mensagens / notificações
- Calendário escolar: próximos eventos, semana, mês e ano
- **Multi-usuário** — cada pessoa acessa com sua conta do P+
- **OAuth** para ChatGPT Actions (botão Sign in + tela de login)
- **API REST** para deploy no Render
- **MCP stdio** para Claude Desktop

## Arquitetura

```
ChatGPT ──OAuth──► /oauth/authorize ──► login P+ ──► token JWT
   │                                                    │
   └──────── Bearer token ──► FastAPI (Render) ──────────┴──► API Poliedro/P+

Claude Desktop ──stdio──► MCP server (local) ──► API Poliedro/P+
```

A lógica de negócio fica em `services.py` e é compartilhada entre API e MCP.

## Modos de autenticação

| Modo | Uso | Como autentica |
|------|-----|----------------|
| **OAuth** (recomendado) | ChatGPT Actions, vários usuários | Sign in → `/oauth/authorize` → Bearer token |
| **Bearer token** | Integrações via API, scripts | `POST /api/v1/auth/login` ou OAuth |
| **Single-user** (legado) | Um GPT/usuário fixo no servidor | `X-API-Key` + `POLIEDRO_TOKEN` no Render |
| **Local / MCP** | Claude Desktop, desenvolvimento | Keychain (`setup_login`) ou `poliedro_token` nas tools |

Os endpoints `/api/v1/*` aceitam **`Authorization: Bearer`** (token do usuário) **ou** **`X-API-Key`** (modo legado com conta fixa no servidor). Os endpoints `/oauth/*` são públicos (protegidos por `OAUTH_CLIENT_SECRET` na troca de token).

## Requisitos

- Python 3.11 ou superior
- macOS (o setup salva a senha no Keychain; em Linux use `POLIEDRO_TOKEN`)
- Conta ativa no [P+](https://pmais.p4ed.com/) (responsável ou aluno)

## Primeira instalação (local / MCP)

Execute os comandos **na raiz do repositório** (`poliedro-mcp/`), não dentro de `config/`:

```bash
cd poliedro-mcp

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
pip install -e .

cp config/config.example.json config/config.json
```

O `config.json` inicial pode manter só a `base_url` correta; os demais campos (`auth`, `student`, `calendar`) são preenchidos no passo de login abaixo.

### Login e configuração automática

```bash
python -m poliedro_mcp.setup_login
```

O script:

1. Pede o **usuário** (se `auth.username` estiver vazio ou for placeholder no config)
2. Pede a **senha** (mesma do login em https://pmais.p4ed.com/)
3. Valida o acesso na API do Poliedro
4. Salva a senha no Keychain do macOS (serviço `poliedro-pmais`)
5. Atualiza `config/config.json` com `username`, dados do aluno e calendário

Confira no final a saída com `school_id`, `email_p4ed`, `enrollment_id`, etc.

### Validar instalação

```bash
python -m poliedro_mcp.cli health
python -m poliedro_mcp.cli grades
python -m poliedro_mcp.cli messages
python -m poliedro_mcp.cli calendar next
```

## Segurança

Não coloque senha nem token no `config.json`.

Autenticação local:

1. **Keychain** (recomendado no Mac) — `python -m poliedro_mcp.setup_login`
2. **Token manual** — variável `POLIEDRO_TOKEN` (útil em CI/Linux)

Senhas do P+ **não são armazenadas** no servidor em produção — o usuário autentica via OAuth ou envia credenciais apenas no momento do login.

## Deploy no Render

1. Faça push do repositório para o GitHub
2. No [Render](https://render.com), crie um **Web Service** a partir do repo
3. Use o blueprint `render.yaml` ou configure manualmente:
   - **Build:** `pip install -r requirements.txt && pip install -e .`
   - **Start:** `uvicorn poliedro_mcp.api:app --host 0.0.0.0 --port $PORT`
   - **Health check:** `/health`

### Variáveis de ambiente

**Modo OAuth (recomendado — ChatGPT multi-usuário):**

| Variável | Obrigatória | Descrição |
|----------|-------------|-----------|
| `OAUTH_CLIENT_SECRET` | Sim | Secret do OAuth (`openssl rand -hex 32`) |
| `OAUTH_CLIENT_ID` | Não | Padrão: `poliedro-gpt` |
| `API_BASE_URL` | Recomendado | URL pública, ex.: `https://SEU-APP.onrender.com` |

Não precisa de `POLIEDRO_TOKEN` nem `POLIEDRO_CONFIG_JSON` neste modo.

**Modo single-user (legado — um usuário fixo):**

| Variável | Obrigatória | Descrição |
|----------|-------------|-----------|
| `API_KEY` | Sim | Chave no header `X-API-Key` |
| `POLIEDRO_TOKEN` | Sim | Token JWT fixo do Poliedro |
| `POLIEDRO_CONFIG_JSON` | Sim | Config completo em JSON (uma linha) |

Para gerar `POLIEDRO_CONFIG_JSON` a partir do config local:

```bash
python scripts/export_config_json.py
```

O token expira periodicamente — renove `POLIEDRO_TOKEN` no Render quando necessário.

## ChatGPT Actions (OAuth)

Guia completo: [docs/chatgpt-setup.md](docs/chatgpt-setup.md)

1. Defina `OAUTH_CLIENT_SECRET` no Render
2. Crie um Custom GPT → **Actions → Authentication → OAuth**
3. Preencha:

| Campo | Valor |
|-------|--------|
| Client ID | `poliedro-gpt` |
| Client Secret | mesmo do Render |
| Authorization URL | `https://SEU-APP.onrender.com/oauth/authorize` |
| Token URL | `https://SEU-APP.onrender.com/oauth/token` |
| Scope | `openid profile email` |

4. Importe o schema: `https://SEU-APP.onrender.com/openapi.json`
5. Salve o GPT

O usuário verá **Sign in** → tela de login do P+ → volta autenticado. Cada pessoa acessa seus próprios dados.

### Contas com múltiplas escolas ou dependentes

Se a conta tiver mais de uma escola ou dependente, a API responde `409` com a lista de opções. Informe `school_id` ou `dependent_id` no formulário de login ou como query param na requisição.

## API programática (sem ChatGPT)

Para scripts ou integrações que não usam OAuth do ChatGPT:

```bash
# 1. Login
curl -s -X POST https://SUA-API.onrender.com/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"aluno.usuario","password":"senha"}'

# 2. Consultar notas
curl -s https://SUA-API.onrender.com/api/v1/grades \
  -H "Authorization: Bearer TOKEN_RETORNADO"
```

O servidor descobre automaticamente escola, matrícula e calendário a partir do JWT.

## Rodar a API REST (local)

```bash
source .venv/bin/activate
pip install -e .

export OAUTH_CLIENT_SECRET=dev-oauth-secret
export API_BASE_URL=http://localhost:8000
# Opcional (modo legado): export API_KEY=dev-local-key

uvicorn poliedro_mcp.api:app --reload --port 8000
```

Documentação interativa: http://localhost:8000/docs

Teste OAuth local — abra no navegador:

```
http://localhost:8000/oauth/authorize?client_id=poliedro-gpt&response_type=code&redirect_uri=https%3A%2F%2Fchatgpt.com%2Faip%2Fg-test%2Foauth%2Fcallback&state=test&scope=openid%20profile%20email
```

## Endpoints

### OAuth (ChatGPT)

| Método | Caminho | Descrição |
|--------|---------|-----------|
| GET | `/oauth/authorize` | Tela de login P+ |
| POST | `/oauth/token` | Troca `code` por `access_token` |
| GET | `/.well-known/oauth-authorization-server` | Metadados OAuth |

### API (`/api/v1`)

| Método | Caminho | Auth | Equivalente MCP |
|--------|---------|------|-----------------|
| POST | `/api/v1/auth/login` | — | — |
| GET | `/api/v1/health` | Bearer ou API Key | `poliedro_health_check` |
| GET | `/api/v1/grades` | Bearer ou API Key | `get_grades` |
| GET | `/api/v1/messages` | Bearer ou API Key | `get_messages` |
| GET | `/api/v1/messages/unread` | Bearer ou API Key | `get_unread_messages` |
| GET | `/api/v1/calendar/next` | Bearer ou API Key | `get_next_events` |
| GET | `/api/v1/calendar/week` | Bearer ou API Key | `get_week_events` |
| GET | `/api/v1/calendar/month` | Bearer ou API Key | `get_month_events` |
| GET | `/api/v1/calendar/year` | Bearer ou API Key | `get_year_events` |

## Rodar como MCP stdio

```bash
python -m poliedro_mcp.server
```

As tools aceitam `poliedro_token` opcional para consultar outro usuário sem alterar o `config.json` local.

## Configuração no Claude Desktop

Substitua `/CAMINHO/ABSOLUTO/poliedro-mcp` pelo caminho real do projeto:

```json
{
  "mcpServers": {
    "poliedro": {
      "command": "/CAMINHO/ABSOLUTO/poliedro-mcp/.venv/bin/python",
      "args": ["-m", "poliedro_mcp.server"],
      "cwd": "/CAMINHO/ABSOLUTO/poliedro-mcp"
    }
  }
}
```

## Ferramentas MCP expostas

- `poliedro_health_check`
- `get_grades`
- `get_unread_messages`
- `get_messages`
- `get_next_events`
- `get_week_events`
- `get_month_events`
- `get_year_events`

Parâmetros opcionais em todas: `poliedro_token`, `school_id`, `dependent_id`.

## Problemas comuns

### `HTTP 401` / credenciais inválidas

- Usuário igual ao do P+ (ex.: `nome.sobrenome`, sem `@p4ed.com`)
- Senha correta e conta ativa em https://pmais.p4ed.com/
- No ChatGPT: faça login novamente (token expirado)
- No modo legado: verifique `POLIEDRO_TOKEN`

### Falha no OAuth do ChatGPT

- `OAUTH_CLIENT_SECRET` igual no Render e no GPT
- URLs de authorize/token apontam para `API_BASE_URL` correto
- Callback do ChatGPT é aceito por padrão (`chatgpt.com/aip/...`)

### `ModuleNotFoundError: poliedro_mcp`

```bash
source .venv/bin/activate
pip install -e .
```

### `Arquivo de configuração não encontrado` (local/MCP)

```bash
cp config/config.example.json config/config.json
python -m poliedro_mcp.setup_login
```

## Segurança em produção

- HTTPS obrigatório (Render fornece automaticamente)
- `OAUTH_CLIENT_SECRET` forte e exclusivo — nunca no repositório
- Tokens JWT do Poliedro são de curta duração; o proxy renova via `refresh_token` quando disponível
- Senhas não ficam persistidas no servidor após o login OAuth
- Modo legado: `API_KEY` e `POLIEDRO_TOKEN` apenas como secrets no Render

## Licença

Este projeto está licenciado sob a [MIT License](LICENSE).

O código deste repositório é open source; o uso da API e do portal P+ continua sujeito aos termos de uso do Poliedro. Cada usuário é responsável por suas próprias credenciais e pelo cumprimento desses termos.
