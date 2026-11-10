# Assistente Órbita: agente RAG com API de câmbio

Agente conversacional para colaboradores da **Órbita Tecnologia** (empresa fictícia). Ele responde dúvidas sobre as políticas internas e calcula reembolsos de despesas feitas no exterior usando a cotação real da moeda.

Projeto da disciplina de LangChain (pós-graduação Infnet), construído com **LangChain 1.x**, **OpenAI**, **Astra DB** e **LangSmith**.

## O que o agente faz

- **Responde sobre políticas e documentos internos** (reembolso, manual do colaborador, FAQ do Nimbus, produto da Órbita), sempre buscando nos documentos e citando a fonte.
- **Converte despesas em moeda estrangeira** consultando uma API de câmbio real (AwesomeAPI).
- **Decide sozinho** quando buscar nos documentos, quando consultar o câmbio e quando responder direto (padrão ReAct com tool calling).
- **Lembra da conversa:** perguntas de acompanhamento ("e se fossem 30 euros?") usam o contexto dos turnos anteriores.
- **Ignora políticas desatualizadas:** documentos marcados como `substituida` ficam fora da busca.

## Arquitetura

```
Usuário (terminal)
      │
      ▼
   cli.py ──► get_agent()  [create_agent + memória InMemorySaver por thread_id]
                 │
                 │  o LLM (gpt-6-luna) decide a cada passo
                 ├── search_policies ──► get_retriever() ──► Astra DB (106 chunks)
                 └── get_exchange_rate ──► AwesomeAPI (cotação em BRL)
                 │
                 ▼
             resposta (com a conta e a fonte)

Todas as execuções são registradas no LangSmith (tracing).
```

**Indexação (offline):** `data/raw/` → loaders (PDF, Markdown, TXT, com metadados do front matter YAML) → chunks (`RecursiveCharacterTextSplitter`) → embeddings (`text-embedding-3-small`) → Astra DB.

**Consulta (online):** pergunta → agente → tools → resposta.

## Estrutura

```
src/agentic_rag/
├── config.py              # Settings (pydantic-settings) e setup do LangSmith
├── llm.py                 # factories do chat model e dos embeddings
├── ingestion/             # loaders, splitter e pipeline de indexação
├── retrieval/
│   ├── vectorstore.py     # conexão com o Astra DB
│   └── retriever.py       # retriever com filtro de status
├── tools/
│   ├── rag_tool.py        # search_policies
│   └── api_tool.py        # get_exchange_rate
├── agent/
│   ├── prompts.py         # system prompt
│   └── agent.py           # get_agent()
└── cli.py                 # chat no terminal
data/raw/                  # documentos de entrada
```

## Requisitos

- Python 3.12 ou superior
- Conta na OpenAI (chave de API)
- Banco no Astra DB (plano gratuito serve)
- Opcional: conta no LangSmith (chave de API) para ver os traces

## Instalação

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

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
| `LANGSMITH_API_KEY` | não | Liga o tracing no LangSmith |
| `LANGSMITH_PROJECT` | não | Nome do projeto no LangSmith (padrão: `orbita-agent`) |

Um valor por linha, sem aspas extras nem quebras de linha. Outros parâmetros (modelo, `chunk_size`, `k` do retriever) têm valor padrão em `config.py` e podem ser sobrescritos pelo `.env`.

## Uso

**1. Indexar os documentos** (uma vez, ou quando os documentos mudarem):

```powershell
python -m agentic_rag.ingestion.pipeline
```

Rodar de novo não duplica os chunks: o ID de cada um é o hash do conteúdo.

**2. Conversar com o agente:**

```powershell
python -m agentic_rag.cli
```

Exemplo de conversa:

```
Você: Qual o limite de reembolso para refeição em viagem?
  [tool] search_policies({'query': 'limite de reembolso refeição em viagem'})
Assistente: O limite é de R$ 110,00 por refeição (orbita_politica_reembolso_2026.md).

Você: Gastei 30 dólares numa refeição em Nova York, quanto recebo?
  [tool] get_exchange_rate({'currency': 'USD'})
Assistente: US$ 30 × R$ 5,5085 = R$ 165,26. Como o limite é R$ 110,00, o reembolso é de R$ 110,00.

Você: E se fossem 30 euros?
  [tool] get_exchange_rate({'currency': 'EUR'})
Assistente: €30 × R$ 6,1795 = R$ 185,39. Também passa do limite: reembolso de R$ 110,00.
```

As linhas `[tool]` mostram as decisões do agente. Digite `sair` para encerrar.

## Observabilidade (LangSmith)

Com `LANGSMITH_API_KEY` no `.env`, o CLI mostra `LangSmith: ligado`, e cada pergunta vira um trace no projeto `orbita-agent`, com as chamadas de tool, os tokens, o custo e a latência.

## Limitações conhecidas

- **Hibernação do Astra DB (plano gratuito):** depois de um tempo sem uso, o banco hiberna e a primeira requisição falha com `400`. Acorde o banco pelo painel do Astra antes de usar.
- **Memória só na sessão:** o histórico fica na memória do processo (`InMemorySaver`) e se perde quando o CLI fecha.
- **Chunks órfãos:** editar um documento ou mudar `chunk_size`/modelo gera IDs novos, e os chunks antigos continuam no banco. Apague a collection antes de reindexar.

## Desenvolvimento

```powershell
ruff format .   # formatação
ruff check .    # lint
mypy src        # checagem de tipos
```

## Uso de IA

Este projeto foi desenvolvido com auxílio do **Claude (Anthropic)**, via Claude Code, para planejamento, escrita e revisão de código. Todo o código foi revisado e executado pelo autor.
