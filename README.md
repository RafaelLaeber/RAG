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
      │                      ├── get_exchange_rate ──► AwesomeAPI (cotação em BRL)
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
| Curto prazo | Mensagens da conversa atual (com resumo das antigas) | RAM (`InMemorySaver`), por `thread_id` |
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
│   ├── api_tool.py        # get_exchange_rate
│   └── memory_tool.py     # save_memory, update_memory, delete_memory
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
| `SUMMARY_TRIGGER_MESSAGES` | `10` | Mensagens no contexto que disparam o resumo (chamadas e respostas de tool também contam) |
| `SUMMARY_KEEP_MESSAGES` | `4` | Mensagens recentes mantidas inteiras após o resumo (precisa ser menor que o anterior) |
| `MEMORY_MAX_ITEMS` | `50` | Máximo de fatos do colaborador injetados no prompt |
| `CONVERSATIONS_MAX_ITEMS` | `30` | Conversas listadas na barra lateral |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `1000` / `150` | Tamanho e sobreposição dos chunks |
| `RETRIEVER_K` | `4` | Trechos devolvidos por busca |

## Uso

**1. Indexar os documentos** (uma vez, ou quando os documentos mudarem). Pela interface, clique na **engrenagem** no canto superior direito e em **Gerar embeddings**. Ou pelo terminal:

```powershell
uv run python -m agentic_rag.ingestion.pipeline
```

Rodar de novo não duplica os chunks: o ID de cada um é o hash do conteúdo.

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
  [get_exchange_rate] {'currency': 'USD'}
Assistente: US$ 30 × R$ 5,5085 = R$ 165,26. Como o limite é R$ 110,00, o reembolso é de R$ 110,00.

Você: E se fossem 30 euros?
  [get_exchange_rate] {'currency': 'EUR'}
Assistente: €30 × R$ 6,1795 = R$ 185,39. Também passa do limite: reembolso de R$ 110,00.
```

Na interface:
- as ferramentas usadas em cada resposta aparecem num bloco recolhível acima dela;
- a barra lateral lista as conversas salvas: clique para reabrir, ou passe o mouse e use a **lixeira** para apagar (com confirmação);
- **Nova conversa** começa do zero, mas o agente continua lembrando dos fatos sobre o colaborador.

## Observabilidade (LangSmith)

Com `LANGSMITH_API_KEY` no `.env`, a barra lateral mostra `LangSmith: ligado` e tudo vira trace no projeto `orbita-agent`:

- **Cada pergunta** vira um trace `orbita_agent`, com as chamadas ao LLM, as tools, o embedding da pergunta (`embed_query`), o resumo da conversa (quando acontece), os tokens, o custo e a latência. Os turnos de uma mesma conversa ficam agrupados na aba **Threads** (pelo `thread_id`).
- **Cada ingestão** vira um trace `ingestion`, com `load_documents`, `split_documents` e `index_chunks`, e dentro dele os `embed_documents`.

Os traces de embedding e de ingestão registram só resumos (quantidade de documentos, fontes, dimensão dos vetores), sem o texto completo nem os vetores.

## Limitações conhecidas

- **Hibernação do Astra DB (plano gratuito):** depois de um tempo sem uso, o banco hiberna e a primeira requisição falha com `400`. Acorde o banco pelo painel do Astra antes de usar.
- **Contexto do agente só na sessão:** o contexto fica na memória do processo (`InMemorySaver`) e se perde ao reiniciar o app. Ao reabrir uma conversa antiga, o histórico salvo é reenviado ao agente (só o texto, sem as chamadas de tool).
- **Reiniciar após mudar o agente:** o agente é criado uma vez por processo (`st.cache_resource`). Mudanças em tools, prompts ou no agente só valem depois de reiniciar o Streamlit.
- **Chunks órfãos:** editar um documento ou mudar `chunk_size`/modelo gera IDs novos, e os chunks antigos continuam no banco. Apague a collection antes de reindexar.
- **Caminhos relativos:** `storage/` e `data/raw` são resolvidos a partir da pasta onde o comando roda. Rode sempre da raiz do projeto.

## Desenvolvimento

```powershell
uv run ruff format .   # formatação
uv run ruff check .    # lint
uv run mypy src        # checagem de tipos
```

## Uso de IA

Este projeto foi desenvolvido com auxílio do **Claude (Anthropic)**, via Claude Code, para planejamento e revisão de código. Todo o código foi escrito, revisado e executado pelo autor.
