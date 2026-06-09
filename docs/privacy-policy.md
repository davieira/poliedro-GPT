# Política de Privacidade — Poliedro P+ para ChatGPT / Claude

**Última atualização:** 9 de junho de 2026

Esta política descreve como o serviço **Poliedro P+ para ChatGPT / Claude** (API REST e servidor MCP não oficial, código aberto em [github.com/davieira/poliedro-GPT](https://github.com/davieira/poliedro-GPT)) trata informações quando você o utiliza por meio do **ChatGPT** (Custom GPT com Actions), do **Claude** (Custom Connector MCP) ou de instalação **local** (Claude Desktop).

> **Importante:** este projeto **não é afiliado** ao Poliedro Sistema de Ensino. O portal oficial P+ permanece em [pmais.p4ed.com](https://pmais.p4ed.com/) e possui seus próprios termos e políticas.

---

## 1. Quem somos

O software é mantido de forma independente por contribuidores do repositório open source **poliedro-GPT**. Quem faz o deploy da API (por exemplo, no [Render](https://render.com)) atua como **operador técnico** da instância que você utiliza ao conectar um Custom GPT ou conector Claude.

Para dúvidas sobre esta política, abra uma issue em:  
[https://github.com/davieira/poliedro-GPT/issues](https://github.com/davieira/poliedro-GPT/issues)

---

## 2. O que o serviço faz

O serviço permite consultar, **em seu nome**, dados já disponíveis no portal Poliedro P+, como:

- Boletim / notas escolares  
- Mensagens e notificações  
- Calendário escolar (eventos, semana, mês, ano)

Para isso, você faz login com **usuário e senha do P+**. A API valida suas credenciais **diretamente nos servidores do Poliedro** e usa um token de acesso temporário para buscar os dados solicitados.

---

## 3. Dados que passam pelo serviço

| Dado | Quando | Armazenado pelo serviço? |
|------|--------|--------------------------|
| Usuário e senha do P+ | Apenas no momento do login | **Não** — usados só para autenticar no Poliedro e descartados em seguida |
| Token JWT do Poliedro | Após login bem-sucedido | **Somente em memória**, pelo tempo da sessão OAuth (minutos) |
| Perfil escolar (escola, matrícula, IDs internos) | Para montar consultas à API do Poliedro | **Cache em memória** por até 30 minutos; não é gravado em disco |
| Notas, mensagens e calendário | Quando você (ou o assistente) solicita uma consulta | **Não persistidos** — repassados na resposta da requisição |
| Códigos e tokens OAuth (ChatGPT / Claude) | Durante o fluxo de autorização | **Somente em memória**, com expiração curta (minutos a horas) |

**Não há banco de dados.** Credenciais do P+ **não são gravadas** em disco, logs estruturados ou arquivos no servidor de produção.

---

## 4. Uso local (Claude Desktop / MCP local)

Se você instala o servidor MCP na **sua máquina**, a senha pode ser salva opcionalmente no **Keychain do macOS** (`setup_login`). Esse armazenamento ocorre **apenas no seu dispositivo**, não no servidor remoto.

---

## 5. Como os dados são usados

Os dados são usados **exclusivamente** para:

1. Autenticar você no portal Poliedro P+  
2. Atender às consultas que você faz via ChatGPT, Claude ou cliente local  
3. Manter sua sessão OAuth ativa enquanto você usa o assistente

Não vendemos, alugamos nem utilizamos seus dados escolares para publicidade, perfilamento comercial ou treinamento de modelos de IA.

---

## 6. Terceiros envolvidos

Ao usar este serviço, seus dados também podem ser processados por:

| Terceiro | Papel |
|----------|--------|
| **Poliedro / P+** ([pmais.p4ed.com](https://pmais.p4ed.com/)) | Autenticação e fonte dos dados escolares |
| **OpenAI** ([ChatGPT](https://openai.com/policies/privacy-policy)) | Interface do Custom GPT; processa suas mensagens e as respostas da Action conforme a política da OpenAI |
| **Anthropic** ([Claude](https://www.anthropic.com/privacy)) | Interface do conector MCP, se você usar Claude |
| **Render** (ou outro provedor de hospedagem) | Hospeda a API; pode registrar metadados de rede padrão de infraestrutura |

Cada terceiro possui sua própria política de privacidade. Recomendamos lê-las.

---

## 7. Retenção

- **Senha do P+:** não retida após o login.  
- **Tokens e cache em memória:** expiram automaticamente (sessão OAuth ou TTL de cache); são perdidos ao reiniciar o servidor.  
- **Logs do servidor:** em produção, credenciais não são registradas intencionalmente. Logs de infraestrutura do provedor de hospedagem podem existir conforme política do Render.

---

## 8. Segurança

Adotamos medidas proporcionais ao escopo do projeto:

- Comunicação via **HTTPS** em produção  
- Tokens OAuth assinados e com tempo de vida limitado  
- Senhas **nunca persistidas** no servidor  
- Cada usuário acessa **apenas os próprios dados** do P+ após autenticação

Nenhum sistema é 100% seguro. Use por sua conta e risco e mantenha suas credenciais do P+ em sigilo.

---

## 9. Crianças e adolescentes

O serviço exibe dados escolares que podem pertencer a **menores de idade** (notas, mensagens da escola, calendário). O acesso deve ser feito por **pais, responsáveis legais ou o próprio aluno** com credenciais válidas do P+. Não coletamos dados adicionais de crianças além do que o portal Poliedro já disponibiliza à conta autenticada.

---

## 10. Seus direitos (LGPD)

Se você está no Brasil, nos termos da **Lei Geral de Proteção de Dados (LGPD)**, você pode:

- Confirmar se tratamos dados em seu nome (limitado ao descrito nesta política)  
- Solicitar esclarecimentos sobre o tratamento  
- Revogar o consentimento **desconectando** o Custom GPT ou conector Claude e **encerrando** o uso do serviço  

Como **não armazenamos** credenciais nem histórico escolar em banco de dados, a forma mais efetiva de cessar o tratamento é **desconectar o GPT/conector** e, se desejar, solicitar exclusão de dados diretamente ao **Poliedro** e à **OpenAI/Anthropic**, conforme as políticas deles.

Para contato: [GitHub Issues](https://github.com/davieira/poliedro-GPT/issues).

---

## 11. Alterações desta política

Podemos atualizar esta política periodicamente. A data da **última atualização** aparece no topo. Alterações relevantes serão refletidas nesta página (`/privacy`) e no repositório.

---

## 12. Resumo

| Pergunta | Resposta |
|----------|----------|
| Vocês guardam minha senha do P+? | **Não** |
| Vocês têm banco de dados com meus dados? | **Não** |
| Quem vê minhas notas no chat? | Você, o assistente (ChatGPT/Claude) e os servidores necessários para a consulta |
| Como parar de usar? | Desconecte o GPT/conector nas configurações do ChatGPT ou Claude |

---

*Projeto open source sob [licença MIT](https://github.com/davieira/poliedro-GPT/blob/main/LICENSE). Uso do portal P+ sujeito aos termos do Poliedro Sistema de Ensino.*
