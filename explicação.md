# Explicação do projeto, arquivo por arquivo

Assistente interno da empresa fictícia **Órbita**. Ele responde perguntas sobre as políticas da empresa usando RAG (busca em documentos indexados no Astra DB) e converte despesas feitas no exterior com a cotação real da moeda (AwesomeAPI). Tem memória híbrida: o histórico da conversa (curto prazo, em RAM) e fatos sobre cada colaborador que duram entre sessões (longo prazo, em SQLite). Funciona pelo terminal.

## Visão geral do fluxo

```
Ingestão (roda uma vez):
  data/raw/*  →  loaders.py  →  splitter.py  →  embeddings (OpenAI)  →  Astra DB

Conversa (cli.py):
  pergunta  →  agente (create_agent + LLM)
                 ├─ search_policies    →  retriever  →  Astra DB  →  trechos com [Fonte: ...]
                 ├─ get_exchange_rate  →  AwesomeAPI  →  "1 USD = x BRL"
                 └─ save_memory        →  SQLite (storage/memory.sqlite)
              →  resposta

Memória:
  curto prazo  →  InMemorySaver, por thread_id (uma conversa; some ao fechar o CLI)
  longo prazo  →  SqliteStore, por user_id (fatos do colaborador; persistem entre sessões)
                  e são injetados no system prompt antes de cada chamada ao LLM
```

---

## Arquivos da raiz

| Arquivo | O que faz |
|---|---|
| `pyproject.toml` | Define o pacote `agentic-rag`: dependências (LangChain, OpenAI, Astra, LangGraph, `langgraph-checkpoint-sqlite`, LangSmith, httpx, pydantic-settings, pypdf, pyyaml), dependências de desenvolvimento (`ruff`, `mypy`) e a configuração dessas duas ferramentas. Instalação: `pip install -e ".[dev]"`. |
| `.env.example` | Modelo do `.env` com as chaves necessárias: `OPENAI_API_KEY`, `ASTRA_DB_API_ENDPOINT`, `ASTRA_DB_APPLICATION_TOKEN` e, opcionalmente, `USER_ID` (usuário da memória de longo prazo), `LANGSMITH_API_KEY` e `LANGSMITH_PROJECT`. |
| `.env` | (Não versionado.) Contém as chaves reais. É lido pelo `Settings`. |
| `.gitignore` | Impede que `.env`, `.venv/`, caches (`__pycache__`, `.ruff_cache`, `.mypy_cache`) e `storage/` (onde fica o banco SQLite das memórias) entrem no git. |
| `.vscode/settings.json` | Configuração do VS Code (pasta raiz para notebooks Jupyter). Não afeta o código. |
| `README.md` | Documentação de uso: instalação, configuração e como rodar. |
| `CLAUDE.md` | Instruções e estado do projeto para o assistente de código (roteiro do MVP e observações técnicas). |

## `data/raw/`: documentos da base de conhecimento

Os arquivos `.md` e `.txt` começam com um **front matter** YAML (bloco entre `---`), que vira metadado de cada trecho no Astra:

| Arquivo | Conteúdo | Metadados |
|---|---|---|
| `orbita_manual_colaborador.md` | Manual do colaborador v3.2 | `doc_type: manual_colaborador`, `status: vigente` |
| `orbita_politica_reembolso_2025.md` | Política de reembolso v1.4 (antiga) | `status: substituida` → **excluída das buscas** |
| `orbita_politica_reembolso_2026.md` | Política de reembolso v2.0 (atual) | `status: vigente` |
| `nimbus_faq.txt` | FAQ do produto Nimbus | `doc_type: faq`, `status: vigente` |
| `lewis2020_rag_paper.pdf` | Artigo original sobre RAG (Lewis et al., 2020) | Sem front matter; um documento por página |

---

## `src/agentic_rag/`: código

Os arquivos `__init__.py` estão vazios. Eles só marcam cada pasta como pacote Python.

### `config.py`: configuração central

- **`Settings`** (pydantic-settings): lê o `.env` e valida os tipos. Reúne todos os valores configuráveis:
  - segredos obrigatórios (`openai_api_key`, `astra_db_*`), guardados como `SecretStr` para não aparecerem em logs;
  - modelos (`llm_model`, `embedding_model`);
  - ingestão (`data_dir`, `chunk_size=1000`, `chunk_overlap=150`);
  - retriever (`retriever_k=4`, ou seja, quantos trechos voltam por busca);
  - câmbio (URL da AwesomeAPI e timeout);
  - memória de longo prazo (`memory_db_path=storage/memory.sqlite`, `memory_max_items=50` e `user_id`, cujo padrão é `colaborador`);
  - LangSmith (chave opcional e nome do projeto).
- **`get_settings()`**: devolve sempre o mesmo objeto (`@lru_cache`), então o `.env` é lido uma vez só. Se o `.env` mudar, é preciso reiniciar o processo.
- **`setup_langsmith()`**: o LangSmith procura a configuração em `os.environ`, mas o pydantic-settings não coloca o `.env` lá. Por isso a função copia `LANGSMITH_*` manualmente. Sem chave (ou com chave vazia), o tracing fica desligado e a função retorna `False`.

### `llm.py`: modelos da OpenAI

- **`get_chat_model()`**: cria o `ChatOpenAI` (modelo do `Settings`, timeout de 30 s, 2 tentativas).
- **`get_embeddings()`**: cria o `OpenAIEmbeddings` (`text-embedding-3-small`), que transforma texto em vetores.

### `ingestion/`: preparar e indexar os documentos

**`loaders.py`**: lê os arquivos de `data/raw/`.
- `_split_front_matter(text)`: separa o bloco YAML do topo do corpo do texto e devolve `(metadados, corpo)`.
- `_load_text(path)`: `.md`/`.txt` → um `Document` com o corpo e os metadados (front matter + `source` = nome do arquivo).
- `_load_pdf(path)`: `.pdf` → um `Document` por página com texto (metadados `source` e `page`).
- `load_documents(directory)`: percorre a pasta, chama o loader certo pela extensão, ignora (com aviso) as extensões não suportadas e adiciona `file_type`.

**`splitter.py`**: quebra os documentos em pedaços (chunks).
- `split_documents(...)`: usa `RecursiveCharacterTextSplitter`, que tenta cortar primeiro em parágrafos, depois em linhas e depois em palavras. Cada chunk tem até 1000 caracteres e repete 150 do chunk anterior, para não perder contexto na fronteira. Os metadados do documento de origem são mantidos e `start_index` registra a posição do trecho.

**`pipeline.py`**: junta tudo. Rodar com `python -m agentic_rag.ingestion.pipeline`.
- `_chunk_id(chunk)`: gera um ID SHA-256 a partir de arquivo + página + texto. O mesmo trecho sempre gera o mesmo ID.
- `run_ingestion()`: carregar → dividir → marcar o `embedding_model` → `add_documents` no Astra com esses IDs. Como os IDs são estáveis, rodar de novo **sobrescreve em vez de duplicar** (idempotente). Resultado atual: 106 chunks.

### `retrieval/`: busca vetorial

**`vectorstore.py`**
- `get_vector_store()`: conecta ao Astra DB (`AstraDBVectorStore`) na collection `documents`, com os embeddings da OpenAI e similaridade por cosseno. Cria a collection se ela não existir.

**`retriever.py`**
- `EXCLUDE_REPLACED = {"status": {"$ne": "substituida"}}`: filtro que exclui documentos marcados como substituídos. Documentos sem `status` (como o PDF) continuam aparecendo.
- `get_retriever()`: transforma o vector store em retriever por similaridade, que devolve os `k` trechos mais parecidos com a pergunta, já com o filtro.
- Por que existe o filtro: sem ele, a pergunta "limite de refeição em viagem" trazia a política 2025 (R$ 80) acima da 2026 (R$ 110).

### `tools/`: ferramentas que o agente pode chamar

O decorator `@tool` transforma uma função em ferramenta. O **nome**, a **docstring** e os **type hints** viram a descrição que o LLM lê para decidir quando chamá-la e com quais argumentos.

**`rag_tool.py`**: `search_policies(query)`
- `_retriever()`: cria o retriever uma vez só (`@lru_cache`), na primeira busca.
- `_format_docs(docs)`: junta os trechos separados por `---`, cada um precedido de `[Fonte: arquivo]`, para que o agente possa citar a fonte.
- `search_policies(query)`: busca a pergunta no Astra e devolve o texto formatado. Se nada for encontrado, devolve "Nenhum trecho relevante encontrado."

**`api_tool.py`**: `get_exchange_rate(currency)`
- Monta a URL `https://economia.awesomeapi.com.br/json/last/USD-BRL` (por exemplo), faz o GET com `httpx` e lê o campo `bid` (taxa de compra).
- Retorna, por exemplo, `"1 USD = 5.4321 BRL (cotação de 2026-11-11 10:00:00)"`.
- Os erros viram mensagens em texto em vez de exceções, para o agente conseguir explicar o problema ao usuário:
  - moeda inexistente (erro HTTP) → "Moeda 'XYZ' não encontrada…";
  - rede ou formato inesperado → "Não foi possível consultar a cotação agora…".

**`memory_tool.py`**: `save_memory(content)`
- Usada pelo agente quando o colaborador conta algo duradouro sobre si: nome, cargo, área, cidade, viagens planejadas ou preferências. A docstring diz para **não** guardar perguntas, valores pontuais nem trechos das políticas.
- Recebe um parâmetro `runtime: ToolRuntime[UserContext]`, que o LangChain injeta sozinho e que o LLM não vê. Dele saem o `store` (o SQLite) e o `user_id` da conversa atual.
- Retorna `"Memória salva: ..."`.

### `memory/`: memória de longo prazo (SQLite)

**`store.py`**
- `UserContext(user_id)`: dataclass com o contexto de execução do agente. É passada em cada chamada (`context=UserContext(...)`) e diz de quem são as memórias.
- `get_memory_store()`: abre (ou cria) o arquivo `storage/memory.sqlite` como um `SqliteStore` do LangGraph e chama `setup()` para criar as tabelas na primeira vez. Usa `@lru_cache`, então abre uma conexão por processo.
- `save_user_memory(store, user_id, content)`: grava um fato com ID aleatório no namespace `("memories", user_id)`.
- `load_user_memories(store, user_id)`: lista os fatos desse usuário, dos mais antigos para os mais novos, até `memory_max_items`.
- Cada usuário tem o próprio namespace, então as memórias de um não aparecem para outro, mesmo estando no mesmo arquivo.

**Curto prazo × longo prazo**

| | Curto prazo | Longo prazo |
|---|---|---|
| O que guarda | Todas as mensagens da conversa | Fatos curtos sobre o colaborador |
| Onde | RAM (`InMemorySaver`) | Arquivo SQLite (`SqliteStore`) |
| Chave | `thread_id` (um por execução do CLI) | `user_id` (do `.env`) |
| Quando some | Ao fechar o CLI | Só apagando `storage/memory.sqlite` |
| Quem grava | O próprio agente, automaticamente | O LLM, ao chamar `save_memory` |

### `agent/`: o agente

**`prompts.py`**: `SYSTEM_PROMPT`
- `SYSTEM_PROMPT`: instruções fixas do agente: ele é o assistente da Órbita, **sempre** usa `search_policies` para regras (nunca o próprio conhecimento), reaproveita trechos e cotações já buscados na conversa, converte moeda estrangeira para reais antes de comparar com os limites, mostra a conta, cita a fonte, diz quando não encontrou a resposta (sem inventar) e responde em português, de forma curta. Também diz para guardar com `save_memory` o que o colaborador contar de duradouro sobre si e para usar a memória para personalizar a resposta.
- `format_memories(memories)`: transforma a lista de memórias em um bloco de texto ("Memória de longo prazo: ...") que é somado ao `SYSTEM_PROMPT`.

**`agent.py`**: `get_agent()`
Monta o agente com `create_agent` (LangChain 1.x):
- `model`: o LLM de `get_chat_model()`;
- `tools`: `search_policies`, `get_exchange_rate` e `save_memory`;
- `middleware=[_prompt_with_memories]`: middleware `@dynamic_prompt` que roda **antes de cada chamada ao LLM**. Ele lê as memórias do `user_id` no SQLite e monta o system prompt (`SYSTEM_PROMPT` + `format_memories`). Assim o agente já começa sabendo quem é o colaborador, sem precisar chamar uma tool para ler;
- `context_schema=UserContext`: define o tipo do contexto recebido em cada chamada (o `user_id`);
- `checkpointer=InMemorySaver()`: a **memória de curto prazo**. Guarda as mensagens de cada `thread_id` em memória RAM, então o histórico some quando o programa fecha;
- `store=get_memory_store()`: a **memória de longo prazo** (SQLite), acessível pela tool e pelo middleware;
- `name="orbita_agent"`: nome que aparece no trace do LangSmith.

O agente segue o ciclo ReAct: o LLM decide se chama uma tool, recebe o resultado, decide de novo e, quando tem informação suficiente, responde.

### `cli.py`: chat no terminal

Rodar com `python -m agentic_rag.cli`.
1. Liga o LangSmith (se houver chave) e cria o agente.
2. Gera um `thread_id` aleatório (`uuid4`): cada execução do CLI é uma conversa, e todas as perguntas dela compartilham a memória de curto prazo. Cria também o `UserContext` com o `user_id` do `Settings` e mostra na tela qual usuário está ativo. O `config` também leva, para o LangSmith, a `metadata` (`thread_id`, `user_id`, `llm_model`) e as `tags` (`cli`, `memoria-sqlite`): o `thread_id` agrupa os turnos da conversa na aba **Threads**, e os demais campos servem de filtro no painel.
3. Loop: lê a pergunta e encerra com `sair`/`exit`/`quit`, Ctrl+C ou Ctrl+D.
4. `agent.stream(..., context=context, stream_mode="updates")` recebe cada passo do agente conforme ele acontece:
   - `AIMessage` com `tool_calls` → imprime `[tool] nome({args})`, o que mostra quais ferramentas foram usadas;
   - `ToolMessage` (resultado bruto da tool) → não é impresso;
   - `AIMessage` sem tool calls → é a resposta final, impressa como `Assistente: ...`.

---

## Como rodar (resumo)

```bash
pip install -e ".[dev]"                     # instalar
cp .env.example .env                        # preencher as chaves
python -m agentic_rag.ingestion.pipeline    # indexar (só uma vez; já feito)
python -m agentic_rag.cli                   # conversar
```

## Como trocar de usuário (testar a memória de longo prazo)

O usuário vem de `USER_ID`. Cada usuário tem as próprias memórias no mesmo arquivo SQLite.

No PowerShell, a variável vale até fechar o terminal e tem prioridade sobre o `.env`:

```powershell
$env:USER_ID = "marina"; python -m agentic_rag.cli
$env:USER_ID = "joao";   python -m agentic_rag.cli
Remove-Item Env:USER_ID   # volta para o USER_ID do .env (ou "colaborador")
```

Ou, para deixar fixo, coloque `USER_ID=marina` no `.env`. A primeira linha do CLI mostra o usuário ativo (`... | usuário: marina`).

Roteiro de teste:
1. Como `marina`: "sou a Marina, de vendas, vou a Lisboa em dezembro" → aparece `[tool] save_memory(...)`. Digite `sair`.
2. Como `marina` de novo, ou seja, numa conversa nova: "o que você lembra de mim?" → ele lembra, sem chamar tool.
3. Como `joao`: a mesma pergunta → ele não sabe nada (as memórias são separadas por usuário).

Para apagar todas as memórias, apague `storage/memory.sqlite`.

Atenção: o Astra no plano gratuito hiberna. Se aparecer erro `400`, acorde o banco no painel do Astra antes de usar.
