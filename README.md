# Poliedro P+ para Claude ou ChatGPT

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Servidor MCP **não oficial** para consultar notas, mensagens e calendário do portal [Poliedro P+](https://pmais.p4ed.com/) no Claude ou no ChatGPT.

> Este projeto **não é afiliado** ao Poliedro Sistema de Ensino. Código aberto — use por sua conta e risco, respeitando os termos do portal P+.

## O que faz

- Boletim / notas
- Simulados / provas trimestrais (resumo, listagem e detalhe por matéria)
- Mensagens e notificações
- Calendário escolar (próximos eventos, semana, mês, ano)
- **ChatGPT** via plugin MCP
- **Claude** via MCP remoto (Custom Connector) ou MCP local no Desktop

## Integrações

| Cliente | Como conectar | OAuth |
|---------|---------------|-------|
| **ChatGPT** | Plugin → `https://poliedro-api.iden.is/mcp` | Automático (DCR) — só login P+ |
| **Claude** (web/app) | Custom Connector → a mesma URL | Automático (DCR) — só login P+ |
| **Claude Desktop** | MCP local (`python -m poliedro_mcp.server`) | Keychain no Mac |

ChatGPT e Claude remoto usam o mesmo endpoint. Não há Client ID nem Client Secret para colar no cliente.

## Como funciona

O usuário autentica com **usuário e senha do P+** (os mesmos do [pmais.p4ed.com](https://pmais.p4ed.com/)). O servidor valida **diretamente no Poliedro**, obtém um token JWT temporário e consulta boletim, mensagens e calendário **em nome de quem logou**. Cada pessoa vê **apenas os próprios dados**.

```
Plugin ou conector → /mcp → OAuth automático → /mcp/login → ferramentas (get_grades, …)
```

Guias: [ChatGPT](docs/chatgpt-setup.md) · [Claude MCP remoto](docs/claude-remote-setup.md)

## Privacidade — nada é armazenado no servidor

**Em produção (ChatGPT plugin ou Claude MCP):**

| Dado | Armazenado? |
|------|-------------|
| Senha do P+ | **Não** — usada só no momento do login e descartada |
| Usuário / e-mail | **Não** — não há banco de dados |
| Credenciais em disco ou logs | **Não** |
| Token JWT do Poliedro | **Só em memória**, pelo tempo da sessão OAuth (minutos) |

O login autentica **diretamente nos servidores do Poliedro**. Este projeto atua como ponte: recebe a senha, repassa ao P+ para validar e **não persiste** em hipótese alguma.

**Uso local (Claude Desktop):** a senha pode ficar no **Keychain do Mac** (`setup_login`). Isso fica só na sua máquina.

## ChatGPT — plugin

O ChatGPT aposentou Custom GPTs com Actions. O plugin **não leva** o schema OpenAPI nem o OAuth manual. A consulta ao P+ entra pelo MCP.

1. Deploy no [Render](https://render.com) (blueprint `render.yaml`)
2. Defina `OAUTH_CLIENT_SECRET` e `API_BASE_URL` no Render
3. No ChatGPT → **Settings → Security and login** → ligue **Developer mode**
4. **Plugins → +** e cole a URL:

```
https://poliedro-api.iden.is/mcp
```

5. Conecte e faça login com usuário e senha do P+ (usuário **sem** `@p4ed.com`)
6. Se tiver várias escolas ou dependentes, escolha na tela de login

**Migrar um GPT existente:** o botão *Migrate to plugin* copia instruções e arquivos. As Actions aparecem como *Unsupported actions* e param de funcionar. O plugin fica **privado** (não dá para publicar na loja) e o GPT original deixa de ser editável. Conecte a URL `/mcp` no plugin depois da migração.

**Ferramentas:** `get_grades`, simulados (`get_simulation_grades`, `list_simulation_assessments`, `get_simulation_performance`), `get_messages`, `get_unread_messages`, `get_message_detail`, `get_next_events`, calendário (semana/mês/ano), `poliedro_health_check`.

## Claude — MCP remoto

Mesma URL e o mesmo login. Sem instalar nada no Mac.

1. Mesmo deploy do Render (`OAUTH_CLIENT_SECRET` e `API_BASE_URL`)
2. Claude → **Settings → Connectors → Add custom connector**
3. **Connector URL:** `https://poliedro-api.iden.is/mcp`
4. Conecte e faça login no P+

Guia e troubleshooting: [docs/claude-remote-setup.md](docs/claude-remote-setup.md)

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
| `POST /mcp` | MCP Streamable HTTP (ChatGPT plugin e Claude) |
| `POST /mcp/register` | Dynamic Client Registration |
| `GET /mcp/authorize` | Início do OAuth MCP |
| `POST /mcp/login` | Login P+ no fluxo MCP |
| `POST /mcp/token` | Token OAuth MCP |
| `GET /.well-known/oauth-authorization-server/mcp` | Metadados OAuth MCP |

A API REST (`/api/v1/grades`, `/openapi.json`, `/oauth/authorize`) continua no ar para o GPT antigo com Actions. O plugin não usa esses caminhos.

Política de privacidade: `https://poliedro-api.iden.is/privacy`

## Variáveis de ambiente (Render)

| Variável | Obrigatória | Descrição |
|----------|-------------|-----------|
| `OAUTH_CLIENT_SECRET` | Sim | Assina os tokens OAuth do MCP. Não é colada no ChatGPT nem no Claude |
| `API_BASE_URL` | Sim (produção) | URL pública do app — usada nos metadados OAuth/MCP |
| `OAUTH_CLIENT_ID` | Não | Só o GPT antigo com Actions. Padrão: `poliedro-gpt` |

Não é necessário `POLIEDRO_TOKEN` nem `POLIEDRO_CONFIG_JSON` no modo MCP remoto.

## Problemas comuns

| Sintoma | O que fazer |
|---------|-------------|
| Login retorna erro | Use as mesmas credenciais do `pmais.p4ed.com` (usuário sem `@p4ed.com`) |
| Várias escolas/dependentes | Preencha School ID e Dependent ID na tela `/mcp/login` |
| "Authorization failed" após login | Remova o plugin/conector, faça redeploy e crie de novo |
| Cliente não registra OAuth | Confirme `curl …/.well-known/oauth-authorization-server/mcp` |
| Plugin sem notas/mensagens | A migração não traz Actions. Conecte `…/mcp` no plugin |

## Desenvolvimento local

```bash
source .venv/bin/activate && pip install -e .
export OAUTH_CLIENT_SECRET=dev-secret
export API_BASE_URL=http://localhost:8000
uvicorn poliedro_mcp.api:app --reload --port 8000
```

Validar: `python -m poliedro_mcp.check` · `python -m poliedro_mcp.cli health`

## Licença

[MIT License](LICENSE) — código open source. O uso do portal P+ continua sujeito aos termos do Poliedro.
