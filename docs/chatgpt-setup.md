# Configurar ChatGPT Actions

Este guia conecta um **Custom GPT** à API hospedada no Render.

## Pré-requisitos

1. API publicada no Render (veja README, seção Deploy no Render)
2. `API_KEY` definida no Render (anote o valor)
3. `POLIEDRO_TOKEN` e `POLIEDRO_CONFIG_JSON` configurados no Render

## Passo a passo no ChatGPT

1. Abra [ChatGPT → Explore GPTs → Create](https://chatgpt.com/gpts/editor)
2. Em **Configure**, role até **Actions**
3. Clique em **Create new action**
4. Em **Authentication**, escolha:
   - **API Key**
   - Auth Type: **Custom**
   - Custom header name: `X-API-Key`
   - API Key: cole o valor de `API_KEY` do Render
5. Em **Schema**, escolha **Import from URL** e informe:

```
https://SEU-APP.onrender.com/openapi.json
```

Substitua `SEU-APP` pelo nome do serviço no Render.

6. Salve o GPT

## Endpoints disponíveis

| Método | Caminho | Descrição |
|--------|---------|-----------|
| GET | `/api/v1/health` | Status da configuração Poliedro |
| GET | `/api/v1/grades` | Boletim / notas |
| GET | `/api/v1/messages` | Mensagens (filtro `status`, `limit`, `page`) |
| GET | `/api/v1/messages/unread` | Mensagens não lidas |
| GET | `/api/v1/calendar/next` | Próximos eventos |
| GET | `/api/v1/calendar/week` | Eventos da semana (`date` opcional) |
| GET | `/api/v1/calendar/month` | Eventos do mês (`date` opcional) |
| GET | `/api/v1/calendar/year` | Eventos do ano (`date` opcional) |

## Instruções sugeridas para o GPT

Cole no campo **Instructions** do Custom GPT:

```
Você ajuda pais e alunos a consultar o portal Poliedro/P+.
Use as Actions para buscar notas, mensagens e calendário escolar.
Sempre resuma os dados de forma clara em português.
Se a API retornar erro 401, informe que a chave de API está incorreta.
Se retornar 502/503, informe que o serviço Poliedro precisa ser reconfigurado.
```

## Testar manualmente

```bash
curl -s -H "X-API-Key: SUA_API_KEY" \
  https://SEU-APP.onrender.com/api/v1/health | jq
```
