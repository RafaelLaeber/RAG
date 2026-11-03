# Projeto: RAG Agêntico com Memória

Projeto de estudo. O objetivo principal é **aprender**, não só ter o código pronto.

## Modo de trabalho (regras para o Claude)

O Rafael escreve o código. O Claude guia.

1. **Não criar nem editar arquivos de código por conta própria.** Entregar o código no chat para o Rafael digitar. Só escrever arquivos diretamente se ele pedir explicitamente.
2. **Passos pequenos.** Um conceito por vez, um arquivo (ou um trecho) por vez. Nada de entregar 200 linhas de uma vez.
3. **Explicar sempre**, nesta ordem:
   - **O que vamos fazer e por quê** (o conceito antes do código).
   - **O código**, em blocos curtos.
   - **Explicação linha a linha** (ou bloco a bloco quando for trivial): o que cada linha faz, o que cada parâmetro significa e o que acontece por baixo.
   - **Como testar** aquele passo (um comando ou um `print` para ver o resultado).
4. **Verificar entendimento.** Ao fim de cada etapa, fazer 1 ou 2 perguntas rápidas ou sugerir um pequeno exercício (ex.: "mude o `chunk_size` para 200 e veja o que acontece").
5. **Ao revisar o código do Rafael**, ler o arquivo, apontar erros e explicar a causa. Não reescrever tudo; indicar a correção e o motivo.
6. **Não pular etapas do roteiro** sem combinar. Se ele quiser avançar, avisar o que está sendo pulado.
7. **Comentários no código em português**, nomes de variáveis/funções em inglês.
8. Linguagem direta, sem floreios.
9. **Seguir sempre os padrões de mercado** (seção abaixo). Quando um padrão aparecer pela primeira vez, explicar por que o mercado faz assim e qual problema ele evita.

## Padrões de mercado (obrigatórios)

### Projeto e dependências
- **`pyproject.toml`** (PEP 621) como fonte única de metadados e dependências. Nada de `requirements.txt` solto.
- Dependências de desenvolvimento separadas em `[project.optional-dependencies] dev`.
- Instalação em modo editável: `pip install -e ".[dev]"`.
- **src layout** (`src/agentic_rag/`): evita importar o código "sem querer" da pasta atual e obriga o pacote a estar instalado, como em produção.

### Configuração e segredos
- Configuração via **`pydantic-settings`** (classe `Settings` tipada e validada), lida do ambiente/`.env`.
- `.env` fora do git; **`.env.example`** versionado com as chaves sem valores.
- Nada de valores fixos espalhados no código (nomes de modelo, caminhos, `k`, `chunk_size` ficam no `Settings`).

### Escrita de código
- **PEP 8**, formatado e verificado com **Ruff** (`ruff format` e `ruff check`).
- **Type hints** em todas as funções públicas; verificação com **mypy**.
- **Docstrings** no estilo Google em módulos, classes e funções públicas.
- **`logging`** no código da aplicação; `print` só no CLI e em scripts de experimento.
- Funções pequenas, uma responsabilidade cada. Criação de objetos caros (LLM, embeddings, vector store) em funções *factory* (ex.: `get_chat_model()`), não em variáveis globais soltas.
- Prompts separados da lógica (`prompts.py`).
- Tratamento de erros explícito: exceções específicas, nunca `except:` vazio.
- Caminhos com `pathlib.Path`, não strings.

### Testes
- **pytest**, em `tests/` espelhando a estrutura de `src/`.
- `tests/unit/`: sem chamadas de rede (LLM e embeddings mockados/fakes, ex.: `FakeEmbeddings`, `FakeListChatModel`).
- `tests/integration/`: chamam a API de verdade; marcados com `@pytest.mark.integration` para rodar só quando quiser.

### Git
- Repositório git desde a Etapa 0.
- Commits pequenos no padrão **Conventional Commits** (`feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`).
- Um commit ao fim de cada etapa do roteiro, no mínimo.

### Documentação
- `README.md` com objetivo, arquitetura, como instalar, configurar e rodar.

## Conceitos do projeto

### RAG (Retrieval-Augmented Generation)
O LLM não conhece seus documentos. O RAG resolve isso em duas fases:
- **Indexação (offline):** carregar documentos → dividir em pedaços (*chunks*) → gerar embeddings → salvar no vector store.
- **Consulta (online):** pergunta do usuário → gerar embedding da pergunta → buscar os chunks mais parecidos → colocar esses chunks no prompt → LLM responde com base neles.

### Embedding
Função que transforma texto em um vetor de números (ex.: 384 ou 1536 dimensões). Textos com significado parecido geram vetores próximos. A "proximidade" é medida por similaridade de cosseno ou distância euclidiana. É isso que permite busca semântica (por significado, não por palavra exata).

### Chunking (text splitting)
Documentos grandes são divididos em pedaços menores antes do embedding.
- `chunk_size`: tamanho de cada pedaço.
- `chunk_overlap`: sobreposição entre pedaços, para não cortar uma ideia no meio.
Chunks muito grandes trazem ruído; muito pequenos perdem contexto.

### Vector Store
Banco de dados que guarda vetores + o texto original + metadados, e faz busca por similaridade. Neste projeto: **Astra DB** (DataStax/IBM, gerenciado na nuvem, sobre Cassandra). Alternativas: Chroma (local), FAISS, pgvector, Qdrant, Pinecone. Todos implementam a interface `VectorStore` do LangChain, então a troca fica isolada em `retrieval/vectorstore.py`.

### Retriever
Interface que recebe uma pergunta e devolve documentos relevantes. Criado a partir do vector store (`vectorstore.as_retriever()`). Parâmetros importantes: `k` (quantos documentos) e `search_type` (`similarity`, `mmr`).

### LCEL (LangChain Expression Language)
Forma de compor componentes com o operador `|` (pipe), como no shell:
```python
chain = prompt | llm | StrOutputParser()
```
Todo componente é um **Runnable** e tem os mesmos métodos: `invoke`, `batch`, `stream` (e versões `a*` assíncronas). Peças importantes:
- `RunnablePassthrough`: repassa a entrada sem alterar.
- `RunnableParallel` (ou um `dict`): roda vários ramos com a mesma entrada e junta os resultados.
- `RunnableLambda`: transforma uma função Python comum em Runnable.
- `.assign(...)`: adiciona chaves ao dicionário que está passando pela chain.

### RAG Agêntico
No RAG simples, a busca sempre acontece, uma vez, do mesmo jeito. No RAG agêntico, um **agente** (LLM + ferramentas + loop de decisão) decide:
- **se** precisa buscar (perguntas como "oi" não precisam);
- **onde** buscar (base de documentos, memória, web, etc.);
- **como** reformular a pergunta;
- **se** o resultado foi bom o suficiente ou se precisa buscar de novo.
O retriever vira uma **tool** que o agente pode chamar. A orquestração é feita com **LangGraph** (grafo de estados com nós e arestas condicionais).

### Memória de curto prazo
Histórico da conversa atual (as últimas mensagens). Permite perguntas de acompanhamento ("e o segundo item?"). No LangGraph, é feita com um **checkpointer** (`InMemorySaver` ou `SqliteSaver`) e um `thread_id` por conversa. Precisa de estratégia para não estourar o contexto: cortar mensagens antigas (`trim_messages`) ou resumir.

### Memória de longo prazo
Informações que persistem **entre conversas** (preferências do usuário, fatos aprendidos). Ficam num **store** separado (`InMemoryStore` / store com busca semântica no LangGraph, ou uma coleção própria no vector store), organizadas por *namespace* (ex.: `("usuario", "rafael")`). O agente tem ferramentas para salvar e consultar essas memórias.

## Stack

- **Python** (venv em `.venv`). Atenção: o Python instalado é 3.14; algumas libs (ex.: `chromadb`, `torch`) podem ainda não ter suporte. Se der erro de instalação, criar o venv com 3.12.
- **langchain / langchain-core**: componentes e LCEL.
- **langgraph**: agente, checkpointer (memória curta) e store (memória longa).
- **langchain-astradb**: vector store no Astra DB (variáveis `ASTRA_DB_API_ENDPOINT` e `ASTRA_DB_APPLICATION_TOKEN` no `.env`). Plano B: Chroma local.
- **langchain-openai**: LLM e embeddings, ambos pela API da OpenAI (chave `OPENAI_API_KEY` no `.env`).
  - Embeddings: `text-embedding-3-small` (1536 dimensões, ~US$ 0,02 por 1M tokens).
  - LLM:`gpt-6-luna` 
- **pydantic-settings**: configuração tipada lida do `.env` (nunca commitar o `.env`).
- **Dev**: `pytest`, `ruff`, `mypy`.

## Estrutura planejada

```
RAG/
├── .env                      # segredos (fora do git)
├── .env.example              # modelo do .env, sem valores (versionado)
├── .gitignore
├── pyproject.toml            # metadados, dependências e config de ruff/mypy/pytest
├── README.md
├── CLAUDE.md
├── data/
│   └── raw/                  # documentos de entrada (pdf, txt, md)
├── storage/                  # arquivos locais gerados, ex.: banco SQLite da memória (fora do git)
├── notebooks/                # experimentos das etapas 1–3 (exploração, não é código de produção)
├── src/
│   └── agentic_rag/          # pacote da aplicação
│       ├── __init__.py
│       ├── config.py         # classe Settings (pydantic-settings)
│       ├── llm.py            # factories: get_chat_model(), get_embeddings()
│       ├── ingestion/
│       │   ├── loaders.py    # carregar documentos
│       │   ├── splitter.py   # chunking
│       │   └── pipeline.py   # carregar → dividir → embeddings → salvar
│       ├── retrieval/
│       │   ├── vectorstore.py  # criar/carregar o vector store
│       │   └── retriever.py    # configurar o retriever
│       ├── chains/
│       │   ├── prompts.py    # templates de prompt
│       │   └── rag_chain.py  # chain LCEL do RAG simples
│       ├── memory/
│       │   ├── short_term.py # checkpointer + trim de mensagens
│       │   └── long_term.py  # store com namespaces
│       ├── agent/
│       │   ├── state.py      # estado do grafo (TypedDict)
│       │   ├── tools.py      # tools do agente
│       │   ├── nodes.py      # funções dos nós do grafo
│       │   └── graph.py      # montagem do grafo LangGraph
│       └── cli.py            # interface de chat no terminal (entry point)
└── tests/
    ├── conftest.py           # fixtures compartilhadas
    ├── unit/
    └── integration/
```

## Roteiro de aprendizado

Marcar com `[x]` ao concluir cada etapa.

- [x] **Etapa 0 – Ambiente e esqueleto:** git, `pyproject.toml`, estrutura de pastas, `.gitignore`, `.env.example`, `config.py` com pydantic-settings, ruff/pytest funcionando, primeiro commit.
- [x] **Etapa 1 – Primeira chamada ao LLM:** `invoke` simples, mensagens (`SystemMessage`, `HumanMessage`).
- [x] **Etapa 2 – LCEL básico:** `ChatPromptTemplate | llm | StrOutputParser`, `stream`, `batch`.
- [x] **Etapa 3 – Embeddings na prática:** gerar vetores, comparar similaridade de frases manualmente.
- [x] **Etapa 4 – Ingestão:** loaders, `RecursiveCharacterTextSplitter`, salvar no Astra DB.
- [ ] **Etapa 5 – Retriever:** busca por similaridade, `k`, MMR, filtros por metadados.
- [ ] **Etapa 6 – RAG com LCEL:** `{"context": retriever | format_docs, "question": RunnablePassthrough()} | prompt | llm | parser`.
- [ ] **Etapa 7 – Memória de curto prazo:** histórico da conversa, reformular a pergunta com base no histórico.
- [ ] **Etapa 8 – Tools e agente:** transformar o retriever em tool, agente ReAct com LangGraph.
- [ ] **Etapa 9 – RAG agêntico de verdade:** grafo com nós de decisão (buscar ou não, avaliar relevância, reescrever pergunta).
- [ ] **Etapa 10 – Memória de longo prazo:** store com namespaces, tools para salvar/buscar fatos do usuário.
- [ ] **Etapa 11 – Interface de chat:** loop no terminal com `thread_id`, streaming.
- [ ] **Etapa 12 (opcional) – Avaliação e melhorias:** testar qualidade das respostas, reranking, busca híbrida.

## Estado atual

Etapas 0 a 4 concluídas (`config.py`, `llm.py`, notebooks 01–03, `ingestion/loaders.py`, `splitter.py`, `pipeline.py` idempotente com IDs sha256 de `source|page|conteúdo`, `retrieval/vectorstore.py`). 106 chunks indexados na collection `documents` do Astra (cosine, 1536 dims). Rodar a ingestão: `python -m agentic_rag.ingestion.pipeline`.

**Etapa 5 em andamento** (notebook `notebooks/04_retriever.ipynb`):
- Parte 1 (feita): `similarity_search_with_score`, score do Astra = (1+cos)/2 (maior = melhor), `k` é máximo e não garantia, busca vetorial sempre devolve algo (score ~0,6 para pergunta irrelevante).
- Parte 2 (feita): `filter={"source": ...}` e `{"file_type": {"$in": ["md", "txt"]}}` (`file_type` é salvo **sem ponto**). Filtro com valor errado devolve vazio, sem erro.
- Parte 3 (código feito, falta ajustar): front matter YAML nos `.md`/`.txt` de `data/raw` (`doc_type`, `version` entre aspas, `status: vigente|substituida`); `_split_front_matter` em `loaders.py` com `yaml.safe_load`, valores convertidos para `str`, `source` sempre vence. Pendências: declarar `pyyaml>=6.0` em dependencies e `types-PyYAML>=6.0` em dev no `pyproject.toml`; ordenar imports (`ruff check --fix`); `ruff format`.
- Parte 4 (entregue, não feita): 2 testes em `test_loaders.py` (lê front matter; lista no YAML levanta `ValueError`), reindexar (deve continuar 106, mesmos IDs), células 6 e 7 do notebook filtrando por `status`. Pergunta em aberto: o PDF não tem `status`, então o filtro `{"status": "vigente"}` o exclui; soluções: dar status ao PDF (dado) ou usar `{"status": {"$ne": "substituida"}}` (filtro).
- Depois: MMR (`search_type="mmr"`, `fetch_k`, `lambda_mult`), `retrieval/retriever.py` com `get_retriever()` e `k`/`search_type` no `Settings`, testes, commit e marcar a Etapa 5.

Limitações conhecidas (para a Etapa 12): editar um documento ou mudar `chunk_size`/modelo deixa chunks órfãos no Astra (IDs novos não sobrescrevem os antigos) → apagar por `source` ou recriar a collection antes de reindexar.

Perguntas já respondidas: factory devolve `VectorStore` (programar para a interface; permite `InMemoryVectorStore` nos testes); mudar `chunk_size` gera órfãos.

**Para continuar em outro PC:** `CLAUDE.md` e `data/` estão no `.gitignore` → copiar manualmente. Recriar `.env` a partir do `.env.example` (um valor por linha). `python -m venv .venv` + `pip install -e ".[dev]"`. Kernel dos notebooks = `.venv`.

Pontos de aprendizado já trabalhados: parênteses em chamadas (classe vs. instância), chaves do dict = variáveis do template, cache de módulos no kernel, mock "onde é usado", seguir o fluxo do dado na chain (bug de passar a resposta como pergunta), a entrada do `.invoke()` é o que a primeira peça da chain espera.

Pontos a reforçar (respostas parciais nos exercícios): embedding capta assunto, não palavras iguais nem negação; vetores de modelos diferentes vivem em espaços incompatíveis (não é questão de capacidade) → trocar modelo exige reindexar.

Observações técnicas:
- pydantic-settings **não** coloca o `.env` em `os.environ`; por isso a chave é passada explicitamente para `ChatOpenAI`/`OpenAIEmbeddings` via `openai_api_key=` (o alias `api_key=` falha no mypy em `OpenAIEmbeddings`).
- ID `gpt-6-luna` confirmado via `models.list()` (também existe `gpt-5.6-luna`).
- Notebooks: usar `%autoreload 2` na primeira célula; kernel antigo mantém módulos em cache.
- `langchain-community` está sendo descontinuado (DeprecationWarning). Não usar; loaders próprios com `pypdf` e `Path.read_text`.
- `.env` não é Python: um valor por linha, sem parênteses nem quebra de linha (endpoint em `( ... )` quebrou o Astra).
- O `AstraDBVectorStore` chama a API de embeddings já no `__init__` (detecta a dimensão).
- `data/` inteira está no `.gitignore` (decisão do Rafael). Testes não podem depender de `data/raw`; usar `tmp_path`.

Atualizar esta seção ao fim de cada sessão (etapa atual, dúvidas pendentes, próximos passos).
