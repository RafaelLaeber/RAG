Sempre que uma grande atualização foi feita atualize o @README.md e o adicione mais explicações ao arquivo @explicacao.md caso ele exista.

Qualquer alteração do projeto deve seguir o mesmo padrão ja existente para aquele serviço ou tarefa.


Caso seja uma alteração de grande impacto, ao final de realizar a tarefa descreva sempre as principais mudanças, impactos, desvantagens e vantagens no final da resposta.

## Versionamento

O Vega segue o versionamento semântico (`MAJOR.MINOR.PATCH`), a partir da versão 1.0.0. Toda alteração que for para a `main` deve dizer se muda a versão e qual número sobe:

- **MAJOR** (`1.0.0` → `2.0.0`): mudança que quebra compatibilidade. Exemplos: rota da API removida ou com contrato diferente (`docs/api.md`), evento SSE alterado, schema dos bancos em `storage/` que exige apagar ou migrar dados, variável obrigatória nova ou renomeada no `.env`, troca da collection ou do formato dos chunks que exige reindexar do zero, cookie de sessão renomeado (todo mundo precisa entrar de novo).
- **MINOR** (`1.0.0` → `1.1.0`): funcionalidade nova que não quebra nada. Exemplos: tool nova no agente, rota nova, tela ou componente novo, guardrail novo, variável opcional nova com valor padrão, suporte a outro tipo de arquivo no upload.
- **PATCH** (`1.0.0` → `1.0.1`): correção de bug, ajuste de texto, prompt ou estilo, melhoria de desempenho, atualização de dependência sem mudança de comportamento e mudanças só de documentação.

Ao subir o MAJOR, o MINOR e o PATCH voltam a zero; ao subir o MINOR, o PATCH volta a zero.

Ao mudar a versão:

1. Atualize o número, igual, nos três lugares: `pyproject.toml` (`version`, depois `uv lock`), `frontend/package.json` (com `npm version X.Y.Z --no-git-tag-version` dentro de `frontend/`, que também atualiza o `package-lock.json`) e `src/agentic_rag/api/main.py` (`version=` do FastAPI, que aparece no Swagger). A versão mostrada na tela de login vem do `frontend/package.json` no build (`__APP_VERSION__` em `vite.config.ts`), então acompanha sozinha: só é preciso gerar o build de novo.
2. Registre a versão no `README.md` (seção **Versões**) e, se existir, no `explicacao.md`, com as principais mudanças.
3. Faça o commit com a versão na mensagem (ex.: `release: v1.1.0 ...`) e crie a tag anotada `vX.Y.Z` nesse commit (`git tag -a v1.1.0 -m "Vega 1.1.0"`).

Se não estiver claro qual número subir, escolha o maior entre os candidatos e explique o motivo na resposta.
