# Assistente Órbita: agente RAG com API de câmbio

Agente conversacional para colaboradores da **Órbita Tecnologia** (empresa fictícia). Ele responde dúvidas sobre as políticas internas e calcula reembolsos de despesas feitas no exterior usando a cotação real da moeda.

Projeto da disciplina de LangChain (pós-graduação Infnet), construído com **LangChain 1.x**, **LangGraph**, **OpenAI**, **Astra DB**, **LangSmith** e **Streamlit**.

## O que o agente faz

- **Responde sobre políticas e documentos internos** (reembolso, manual do colaborador, FAQ do Nimbus, relatório financeiro), sempre buscando nos documentos e citando a fonte.
- **Converte despesas em moeda estrangeira** consultando uma API de câmbio real (AwesomeAPI).
- **Decide sozinho** quando buscar nos documentos, quando consultar o câmbio e quando responder direto (padrão ReAct com tool calling).
- **Lembra da conversa:** perguntas de acompanhamento ("e se fossem 30 euros?") usam o contexto dos turnos anteriores.
- **Resume conversas longas:** passado um limite de mensagens, as mais antigas viram um resumo, o que economiza tokens.
- **Lembra do colaborador entre conversas:** guarda fatos sobre ele (nome, cidade, cargo) e os corrige ou apaga quando mudam, se repetem ou quando ele pede para esquecer.
- **Guarda o histórico:** as conversas ficam salvas, podem ser reabertas pela barra lateral e apagadas pelo ícone de lixeira.
- **Ignora políticas desatualizadas:** documentos marcados como `substituida` ficam fora da busca.
- **Não obedece a documentos:** todo conteúdo externo (documentos, API, memórias) é tratado como dado não confiável. Instruções embutidas nele são ignoradas (veja [Segurança](#segurança-prompt-injection)).

## Arquitetura

```
Usuário (navegador)
      │
      ▼
   app.py (Streamlit) ──► get_agent()  [create_agent]
      │                      │
      │                      │  middleware: resumo da conversa + memórias no system prompt
      │                      │  o LLM (gpt-6-luna) decide a cada passo
      │                      ├── search_policies ──► get_retriever() ──► Astra DB
      │                      ├── convert_currency / get_exchange_rate ──► AwesomeAPI (BRL)
      │                      └── save / update / delete_memory ──► SQLite (fatos do colaborador)
      │                      │
      │                      ▼
      │                  resposta (com a conta e a fonte)
      │
      └──► histórico de conversas ──► SQLite

Todas as execuções (agente, embeddings e ingestão) são registradas no LangSmith.
```

**Indexação:** `data/raw/` → loaders (PDF, Markdown, TXT, com metadados do front matter YAML) → chunks (`RecursiveCharacterTextSplitter`) → embeddings (`text-embedding-3-small`) → Astra DB.

**Consulta:** pergunta → agente → tools → resposta.

### Memória

| Camada | O que guarda | Onde |
|---|---|---|
| Curto prazo | Contexto do agente na conversa: mensagens, chamadas de tool e resumo das antigas | `storage/checkpoints.sqlite` (`SqliteSaver`), por `thread_id` |
| Longo prazo | Fatos sobre o colaborador | `storage/memory.sqlite` (`SqliteStore`), por `user_id` |
| Histórico | Todas as conversas e mensagens, para exibir e reabrir | `storage/conversations.sqlite`, por `user_id` |

## Estrutura

```
src/agentic_rag/
├── config.py              # Settings (pydantic-settings) e setup do LangSmith
├── llm.py                 # chat model e embeddings (com trace no LangSmith)
├── ingestion/             # loaders, splitter, pipeline de indexação e resumos para o trace
├── retrieval/
│   ├── vectorstore.py     # conexão com o Astra DB
│   └── retriever.py       # retriever com filtro de status
├── tools/
│   ├── rag_tool.py        # search_policies
│   ├── api_tool.py        # get_exchange_rate, convert_currency
│   └── memory_tool.py     # save_memory, update_memory, delete_memory
├── guardrails/            # proteção contra prompt injection
│   ├── untrusted.py       # envelope de dados externos (tag com sufixo aleatório)
│   ├── detection.py       # heurística de instruções embutidas
│   ├── memory.py          # validação dos fatos antes de gravar
│   └── middleware.py      # envelopa todo resultado de tool
├── agent/
│   ├── prompts.py         # system prompt e prompt de resumo
│   └── agent.py           # get_agent()
├── memory/
│   ├── store.py           # memória de longo prazo (fatos do colaborador)
│   └── conversations.py   # histórico de conversas
└── app.py                 # interface web (Streamlit)
data/raw/                  # documentos de entrada
.streamlit/config.toml     # tema escuro da interface
```

## Requisitos

- [uv](https://docs.astral.sh/uv/) (instala o Python 3.12 e as dependências)
- Conta na OpenAI (chave de API)
- Banco no Astra DB (plano gratuito serve)
- Opcional: conta no LangSmith (chave de API) para ver os traces

## Instalação

```powershell
uv sync
```

Cria a `.venv` com o Python fixado em `.python-version` (3.12) e instala as versões travadas no `uv.lock`, incluindo as ferramentas de desenvolvimento. Para adicionar um pacote: `uv add nome`.

## Configuração

Copie o modelo e preencha as chaves:

```powershell
Copy-Item .env.example .env
```

| Variável | Obrigatória | Descrição |
|---|---|---|
| `OPENAI_API_KEY` | sim | Chave da OpenAI (LLM e embeddings) |
| `ASTRA_DB_API_ENDPOINT` | sim | Endpoint do banco no Astra DB |
| `ASTRA_DB_APPLICATION_TOKEN` | sim | Token do Astra DB |
| `USER_ID` | não | Usuário das memórias e do histórico (padrão: `colaborador`) |
| `LANGSMITH_API_KEY` | não | Liga o tracing no LangSmith |
| `LANGSMITH_PROJECT` | não | Nome do projeto no LangSmith (padrão: `orbita-agent`) |

Um valor por linha, sem aspas extras nem quebras de linha. Os demais parâmetros têm valor padrão em `config.py` e podem ser sobrescritos pelo `.env` com o nome em maiúsculas. Os mais úteis:

| Variável | Padrão | Descrição |
|---|---|---|
| `SUMMARY_TRIGGER_TOKENS` | `12000` | Tokens nas mensagens da conversa que disparam o resumo (resultados de tool também contam) |
| `SUMMARY_KEEP_TOKENS` | `4000` | Tokens das mensagens mais recentes mantidas inteiras após o resumo (precisa ser menor que o anterior) |
| `MEMORY_MAX_ITEMS` | `50` | Máximo de fatos por colaborador (passou disso, o agente precisa atualizar ou apagar antes de salvar) |
| `MEMORY_MAX_CHARS` | `200` | Tamanho máximo de cada fato |
| `CONVERSATIONS_MAX_ITEMS` | `30` | Conversas listadas na barra lateral |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `1000` / `150` | Tamanho e sobreposição dos chunks |
| `RETRIEVER_K` | `5` | Trechos devolvidos por busca |

## Uso

**1. Indexar os documentos** (uma vez, ou quando os documentos mudarem). Pela interface, clique na **engrenagem** no canto superior direito e em **Gerar embeddings**. Ou pelo terminal:

```powershell
uv run python -m agentic_rag.ingestion.pipeline
```

A ingestão sincroniza a collection com `data/raw`: o ID de cada chunk é o hash do texto e dos metadados, então chunks iguais não geram embedding de novo, e chunks de documentos editados ou removidos (ou de outro `chunk_size`/modelo de embedding) são apagados. Rodar de novo sem mudanças não altera nada. Use uma collection exclusiva para o projeto, porque tudo o que não vier de `data/raw` é removido.

**2. Conversar com o agente:**

```powershell
uv run streamlit run src/agentic_rag/app.py
```

Exemplo de conversa:

```
Você: Qual o limite de reembolso para refeição em viagem?
  [search_policies] {'query': 'limite de reembolso refeição em viagem'}
Assistente: O limite é de R$ 110,00 por refeição (orbita_politica_reembolso_2026.md).

Você: Gastei 30 dólares numa refeição em Nova York, quanto recebo?
  [convert_currency] {'amount': 30, 'currency': 'USD'}
Assistente: US$ 30 × R$ 5,5085 = R$ 165,26. Como o limite é R$ 110,00, o reembolso é de R$ 110,00.

Você: E se fossem 30 euros?
  [convert_currency] {'amount': 30, 'currency': 'EUR'}
Assistente: €30 × R$ 6,1795 = R$ 185,39. Também passa do limite: reembolso de R$ 110,00.
```

Na interface:
- a resposta aparece em streaming, token a token, enquanto o modelo escreve;
- acima de cada resposta aparece um bloco compacto com o total de ferramentas usadas ("3 ferramentas usadas"). Ao clicar, ele abre a lista no próprio chat, e cada ferramenta abre os argumentos que recebeu;
- a barra lateral lista as conversas salvas: clique para reabrir, ou passe o mouse e use a **lixeira** para apagar (com confirmação);
- **Nova conversa** começa do zero, mas o agente continua lembrando dos fatos sobre o colaborador.

## Segurança (prompt injection)

Quem consegue colocar um arquivo em `data/raw` não deve conseguir dar ordens ao agente. Por isso, todo conteúdo que não vem do colaborador é tratado como **dado não confiável**, em camadas:

1. **Envelope** (`guardrails/untrusted.py` + `middleware.py`): todo resultado de tool e a memória de longo prazo chegam ao LLM entre `<dados_externos_XXXXXXXX>` e `</dados_externos_XXXXXXXX>`, com um sufixo aleatório a cada chamada. Assim, o documento não consegue fechar a tag para se passar por instrução. O middleware fica no agente, então tools novas são cobertas automaticamente.
2. **Regra no system prompt:** o conteúdo das tags é só dado. Se ele pedir para ignorar regras, mudar de papel, chamar tools ou mexer na memória, o agente não obedece e avisa o colaborador.
3. **Detecção** (`guardrails/detection.py`): padrões de injeção em português e inglês. Nos documentos, só alerta: registra no log (na ingestão e na consulta) e marca o envelope com `alerta`. Na memória, bloqueia.
4. **Memória validada** (`guardrails/memory.py`): fatos com mais de `MEMORY_MAX_CHARS` caracteres, com marcação (`< > [ ]`) ou com cara de instrução são recusados, porque uma memória vai para o prompt de todas as conversas futuras.

Nenhuma dessas camadas elimina prompt injection por completo: a heurística é contornável, e o envelope reduz o risco sem zerá-lo. O que limita o estrago é o agente ter poucos poderes. O pior que um documento malicioso consegue é distorcer uma resposta.

## Observabilidade (LangSmith)

Com `LANGSMITH_API_KEY` no `.env`, a barra lateral mostra `LangSmith: ligado` e tudo vira trace no projeto `orbita-agent`:

- **Cada pergunta** vira um trace `orbita_agent`, com as chamadas ao LLM, as tools, o embedding da pergunta (`embed_query`), o resumo da conversa (quando acontece), os tokens, o custo e a latência. Os turnos de uma mesma conversa ficam agrupados na aba **Threads** (pelo `thread_id`).
- **Cada ingestão** vira um trace `ingestion`, com `load_documents`, `split_documents` e `sync_chunks` (quantos chunks foram adicionados e removidos), e dentro dele os `embed_documents`.

Os traces de embedding e de ingestão registram só resumos (quantidade de documentos, fontes, dimensão dos vetores), sem o texto completo nem os vetores.

## Limitações conhecidas

- **Hibernação do Astra DB (plano gratuito):** depois de um tempo sem uso, o banco hiberna e a primeira requisição falha com `400`. Acorde o banco pelo painel do Astra antes de usar.
- **Conversas anteriores ao checkpointer em SQLite:** essas conversas não têm checkpoint. Ao reabrir uma delas, o histórico salvo é reenviado ao agente (só o texto, sem as chamadas de tool).
- **Turnos com falha:** se o agente falhar no meio de uma resposta, o turno é desfeito. A pergunta e o aviso de erro aparecem só na tela, não entram no histórico nem no contexto, e o erro técnico vai para o log.
- **Reiniciar após mudar o agente:** o agente é criado uma vez por processo (`st.cache_resource`). Mudanças em tools, prompts ou no agente só valem depois de reiniciar o Streamlit.
- **Caminhos relativos:** `storage/` e `data/raw` são resolvidos a partir da pasta onde o comando roda. Rode sempre da raiz do projeto.

## Desenvolvimento

```powershell
uv run ruff format .   # formatação
uv run ruff check .    # lint
uv run mypy src        # checagem de tipos
```

## Uso de IA

Este projeto foi desenvolvido com auxílio do **Claude (Anthropic)**, via Claude Code, para planejamento e revisão de código. Todo o código foi escrito, revisado e executado pelo autor.
