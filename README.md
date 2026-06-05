# Poliedro API & MCP

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

API REST e servidor MCP **não oficial** para consultar informações do portal Poliedro/P+.
Este projeto não é afiliado, endossado ou mantido pelo Poliedro Sistema de Ensino.

Funcionalidades:

- Boletim / notas
- Mensagens / notificações
- Calendário escolar: próximos eventos, semana, mês e ano
- **API REST** para ChatGPT Actions (deploy no Render)
- **MCP stdio** para Claude Desktop (vide docs/)

## Arquitetura

```
ChatGPT Actions ──HTTPS──► FastAPI (Render) ──► API Poliedro/P+
Claude Desktop    ──stdio──► MCP server (local) ──► API Poliedro/P+
```

A lógica de negócio fica em `services.py` e é compartilhada entre API e MCP.

## Requisitos

- Python 3.11 ou superior
- macOS (o setup salva a senha no Keychain; em Linux use `POLIEDRO_TOKEN`)
- Conta ativa no [P+](https://pmais.p4ed.com/) (responsável ou aluno)

## Primeira instalação

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

Autenticação suportada:

1. **Keychain** (recomendado no Mac) — configure com `python -m poliedro_mcp.setup_login`
2. **Token manual** — variável de ambiente `POLIEDRO_TOKEN` (útil em CI/Linux)

Para produção remota, substitua o Keychain por Secret Manager, KMS ou cofre equivalente.

## Problemas comuns

### `HTTP 401` / `Invalid user credentials`

A API rejeitou usuário ou senha. Confira:

- Usuário igual ao do P+ (ex.: `nome.sobrenome`, sem `@p4ed.com`)
- Senha digitada corretamente (o terminal **não mostra** caracteres ao digitar)
- Conta funcionando no site https://pmais.p4ed.com/

Rode o setup de novo após corrigir:

```bash
cd /caminho/para/poliedro-mcp
source .venv/bin/activate
python -m poliedro_mcp.setup_login
```

### `ModuleNotFoundError: poliedro_mcp`

Ative o venv e instale o pacote na raiz do repo:

```bash
source .venv/bin/activate
pip install -e .
```

### `Arquivo de configuração não encontrado`

```bash
cp config/config.example.json config/config.json
```

### Config em outro caminho

```bash
export POLIEDRO_CONFIG=/caminho/absoluto/config.json
```

## Rodar a API REST (local)

```bash
source .venv/bin/activate
pip install -e .

export API_KEY=dev-local-key
# Use POLIEDRO_TOKEN ou config/config.json como no setup local

uvicorn poliedro_mcp.api:app --reload --port 8000
```

Documentação interativa: http://localhost:8000/docs

Teste rápido:

```bash
curl -s -H "X-API-Key: dev-local-key" http://localhost:8000/api/v1/health
```

## Deploy no Render

1. Faça push do repositório para o GitHub
2. No [Render](https://render.com), crie um **Web Service** a partir do repo
3. Use o blueprint `render.yaml` ou configure manualmente:
   - **Build:** `pip install -r requirements.txt && pip install -e .`
   - **Start:** `uvicorn poliedro_mcp.api:app --host 0.0.0.0 --port $PORT`
   - **Health check:** `/health`
4. Defina as variáveis de ambiente:

| Variável | Obrigatória | Descrição |
|----------|-------------|-----------|
| `API_KEY` | Sim | Chave que o ChatGPT envia no header `X-API-Key` |
| `POLIEDRO_TOKEN` | Sim* | Token JWT do Poliedro (sem prefixo `Bearer`) |
| `POLIEDRO_CONFIG_JSON` | Sim* | Config completo em JSON (uma linha) |

\* No Render não há Keychain. Use token + config via env.

Para gerar `POLIEDRO_CONFIG_JSON` a partir do config local:

```bash
python scripts/export_config_json.py
# Cole a saída na variável POLIEDRO_CONFIG_JSON no Render
```

O token expira periodicamente. Quando isso acontecer, atualize `POLIEDRO_TOKEN` no Render.

## ChatGPT Actions

Guia completo: [docs/chatgpt-setup.md](docs/chatgpt-setup.md)

Resumo:

1. Crie um Custom GPT
2. Em **Actions → Authentication**: API Key, header `X-API-Key`
3. Importe o schema: `https://SEU-APP.onrender.com/openapi.json`

## Rodar como MCP stdio

```bash
python -m poliedro_mcp.server
```

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

## Endpoints REST (`/api/v1`)

| Método | Caminho | Equivalente MCP |
|--------|---------|-----------------|
| GET | `/api/v1/health` | `poliedro_health_check` |
| GET | `/api/v1/grades` | `get_grades` |
| GET | `/api/v1/messages` | `get_messages` |
| GET | `/api/v1/messages/unread` | `get_unread_messages` |
| GET | `/api/v1/calendar/next` | `get_next_events` |
| GET | `/api/v1/calendar/week` | `get_week_events` |
| GET | `/api/v1/calendar/month` | `get_month_events` |
| GET | `/api/v1/calendar/year` | `get_year_events` |

Todos os endpoints acima exigem o header `X-API-Key`.

## Ferramentas MCP expostas

- `poliedro_health_check`
- `get_grades`
- `get_unread_messages`
- `get_messages`
- `get_next_events`
- `get_week_events`
- `get_month_events`
- `get_year_events`

## Segurança em produção

- HTTPS obrigatório (Render fornece automaticamente)
- `API_KEY` forte e exclusiva para o ChatGPT
- `POLIEDRO_TOKEN` apenas como secret no Render (nunca no repositório)
- Renovar token quando expirar
- Para múltiplos usuários, seria necessário banco + cofre de credenciais (fora do escopo atual)

## Licença

Este projeto está licenciado sob a [MIT License](LICENSE).

O código deste repositório é open source; o uso da API e do portal P+ continua sujeito aos termos de uso do Poliedro. Cada usuário é responsável por suas próprias credenciais e pelo cumprimento desses termos.
