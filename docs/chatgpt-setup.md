# Configurar ChatGPT Actions (OAuth multi-usuário)

Este guia conecta um **Custom GPT** à API no Render com **login por usuário** — cada pessoa entra com sua conta do P+.

## Pré-requisitos

1. API publicada no Render (veja README)
2. Variáveis no Render:

| Variável | Obrigatória | Exemplo |
|----------|-------------|---------|
| `OAUTH_CLIENT_SECRET` | Sim | gere com `openssl rand -hex 32` |
| `OAUTH_CLIENT_ID` | Não | padrão: `poliedro-gpt` |
| `API_BASE_URL` | Recomendado | `https://SEU-APP.onrender.com` |

Não é necessário `POLIEDRO_TOKEN` nem `POLIEDRO_CONFIG_JSON` no modo OAuth.

## Passo 1 — Deploy

Após o deploy, confira:

```bash
curl -s https://SEU-APP.onrender.com/health
curl -s https://SEU-APP.onrender.com/.well-known/oauth-authorization-server | jq
```

## Passo 2 — Criar o Custom GPT

1. Abra [ChatGPT → Explore GPTs → Create](https://chatgpt.com/gpts/editor)
2. Em **Actions → Create new action**
3. **Schema → Import from URL:**

```
https://SEU-APP.onrender.com/openapi.json
```

4. Em **Authentication**, escolha **OAuth** e preencha:

| Campo | Valor |
|-------|--------|
| Client ID | `poliedro-gpt` (ou seu `OAUTH_CLIENT_ID`) |
| Client Secret | mesmo valor de `OAUTH_CLIENT_SECRET` no Render |
| Authorization URL | `https://SEU-APP.onrender.com/oauth/authorize` |
| Token URL | `https://SEU-APP.onrender.com/oauth/token` |
| Scope | `openid profile email` |
| Token Exchange Method | Default (POST request) |

5. **Salve o GPT** e copie o **Callback URL** que aparece em Actions (formato `https://chatgpt.com/aip/g-.../oauth/callback`).

O callback do ChatGPT já é aceito por padrão. Só altere `OAUTH_ALLOWED_REDIRECT_PREFIXES` se usar outro domínio.

## Passo 3 — Instruções do GPT

```
Você ajuda pais e alunos a consultar o portal Poliedro/P+.
Antes de buscar notas, mensagens ou calendário, o usuário deve estar logado.
Se não estiver, peça para clicar em "Sign in" / "Entrar" — nunca peça senha no chat.
Use as Actions para consultar a API e resuma os dados em português claro.
Se retornar 409 com escolha_necessaria, peça school_id ou dependent_id e tente de novo.
Se retornar 401, peça para fazer login novamente.
```

## Fluxo do usuário final

1. Abre o GPT no ChatGPT
2. Clica em **"Sign in to …"** (botão OAuth)
3. Vê a tela de login P+ hospedada na sua API
4. Digita usuário e senha do https://pmais.p4ed.com/
5. Volta ao ChatGPT autenticado
6. Pode pedir notas, mensagens e calendário

## Endpoints da API

| Método | Caminho | Descrição |
|--------|---------|-----------|
| GET | `/oauth/authorize` | Tela de login (ChatGPT redireciona aqui) |
| POST | `/oauth/token` | Troca code por token |
| GET | `/api/v1/health` | Status |
| GET | `/api/v1/grades` | Boletim / notas |
| GET | `/api/v1/messages` | Mensagens |
| GET | `/api/v1/messages/unread` | Não lidas |
| GET | `/api/v1/calendar/next` | Próximos eventos |
| GET | `/api/v1/calendar/week` | Semana |
| GET | `/api/v1/calendar/month` | Mês |
| GET | `/api/v1/calendar/year` | Ano |

## Contas com múltiplas escolas ou dependentes

Se o login falhar pedindo escolha, o formulário lista as opções. O usuário informa o ID no campo **ID da escola** ou **ID do dependente** e tenta de novo.

Nas Actions, também é possível passar `school_id` ou `dependent_id` como query param após o login.

## Modo legado (um usuário fixo)

Se preferir um único usuário sem OAuth:

1. Authentication → **API Key** → header `X-API-Key`
2. Configure `POLIEDRO_TOKEN` + `POLIEDRO_CONFIG_JSON` no Render

Veja README, seção "Modo single-user".

## Testar OAuth manualmente

```bash
# Simular abertura da tela de login (abra a URL no navegador)
open "https://SEU-APP.onrender.com/oauth/authorize?client_id=poliedro-gpt&response_type=code&redirect_uri=https%3A%2F%2Fchatgpt.com%2Faip%2Fg-test%2Foauth%2Fcallback&state=xyz&scope=openid%20profile%20email"
```

Após login, troque o `code` retornado:

```bash
curl -s -X POST https://SEU-APP.onrender.com/oauth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=authorization_code" \
  -d "client_id=poliedro-gpt" \
  -d "client_secret=SEU_OAUTH_CLIENT_SECRET" \
  -d "code=CODE_RETORNADO" \
  -d "redirect_uri=https://chatgpt.com/aip/g-test/oauth/callback"
```

Use o `access_token` nas chamadas:

```bash
curl -s https://SEU-APP.onrender.com/api/v1/grades \
  -H "Authorization: Bearer TOKEN"
```
