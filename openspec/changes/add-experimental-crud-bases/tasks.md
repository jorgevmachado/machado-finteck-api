# Tasks

## 1. Pacote e consultas com owner obrigatorio

- [x] 1.1 Criar `app/temp/__init__.py` e `repository.py` com contrato generico, sessao explicita, campos permitidos e escopo obrigatorio separado dos filtros; adicionar fixtures locais e testes em `tests/app/temp/test_repository.py` que provem busca por dois owners, ausencia de criterios e rejeicao de escopo ausente antes de executar SQL.
- [x] 1.2 Implementar listagem, filtros, ordenacao deterministica e paginacao com helpers existentes; verificar em SQLite async que itens e total usam os mesmos predicados, pagina conta entidades raiz, resultado vazio e valido, filtros nao sao mutados e campos desconhecidos geram erro explicito.
- [x] 1.3 Iniciar `app/temp/README.md` com aviso experimental, diagnostico por grupo de dominio, exemplos de consulta e limites de filtros/ordenacao; verificar que os exemplos correspondem as assinaturas exercitadas pelos testes de repository.

## 2. Persistencia e transacoes

- [x] 2.1 Implementar `transaction()` e primitivas `save`, `update` e delete fisico sem commits intermediarios; testar inicio de transacao, adocao de autobegin, commit unico, mutacao fora do contexto e rejeicao de reentrada/savepoint, inclusive entre repositorios na mesma sessao.
- [x] 2.2 Adicionar verificacao de owner nas primitivas e testes de rollback em validacao, flush e commit; verificar com duas escritas em SQLite que falha na segunda nao persiste a primeira, e com falhas injetadas que erro de rollback e registrado sem substituir a causa original.
- [x] 2.3 Documentar exclusividade de sessao, `expire_on_commit=False`, posse do commit e composicao via primitivas, nao chamadas publicas aninhadas; verificar o exemplo transacional por teste com repositorio real.

## 3. Service CRUD e observabilidade

- [x] 3.1 Criar `app/temp/service.py` com repositorio tipado, alias, `LoggingParams` e `_operation` baseado em `ReceiptService`: `@asynccontextmanager`, `try/yield/except/else`, handler existente e sucesso somente no `else`; testar operacao especializada de subclasse com contexto de requester/alvo, sucesso normal e erro sem falso sucesso.
- [x] 3.2 Implementar listagem e busca obrigatoria/opcional dentro de `_operation`, usando helpers internos para composicao sem envelopes duplicados; testar 404, `None` apenas por ausencia real, falha de banco propagada e metadados de log ausentes dos filtros SQL.
- [x] 3.3 Implementar create/update/delete herdaveis com `_operation` envolvendo a transacao, construcao explicita de entidade, validacao/transformacao e atualizacao parcial; testar owner confiavel, rejeicao de campos gerenciados, entidade criada com owner incorreto, campos omitidos versus null, ausencia sem upsert e respostas `Message` em update/delete.
- [x] 3.4 Cobrir em `tests/app/temp/test_service.py` falhas de consulta, validacao, persistencia e commit; verificar que o handler existente recebe contexto correto uma unica vez por chamada publica, nao ha sucesso falso nem resultado vazio de fallback e sucesso de mutacao ocorre somente apos commit.
- [x] 3.5 Documentar API, composicao de `_operation` com transacoes e um exemplo de recurso simples que herda os cinco fluxos sem reimplementar orquestracao; verificar um ciclo CRUD com essa subclasse e repository real nos testes.

## 4. Cache reutilizado do BaseService

- [x] 4.1 Compor `CacheService` com configuracao opt-in de schema, prefixo, TTL e pais, reaproveitando construcao de chaves e get/set existentes; testar que CRUD sem configuracao nao inicializa/acessa cache e chamada cached sem configuracao falha explicitamente.
- [x] 4.2 Adaptar `list_all_cached` e `find_one_cached` do BaseService existente ao contexto `_operation` unico, com schema consistente em hit/miss e helpers internos sem dupla traducao; testar cache hit sem SQL, miss com preenchimento, lista vazia como hit, pagina customizada, lookup ausente e falha de banco sem escrita em cache.
- [x] 4.3 Implementar identidade canonica por owner/criterios e `clean_cache` sem mutar inputs; testar isolamento entre owners, filtros, paginacao, ordenacao e valores sensiveis a caixa, refresh de lista no escopo do owner e refresh individual por chave exata.
- [x] 4.4 Adaptar `_invalidate_cache` com `delete_with_parent_cache` para limpar recurso e pais do owner apos commit em create/update/delete, sem exigir override no consumidor; testar aliases antigos/listas invalidados, preservacao do cache de outro owner, nenhuma invalidacao em rollback e warning contextual sem perder resultado confirmado.
- [x] 4.5 Adicionar testes com `CacheService` real e Redis falso local para ida/volta de ORM/schema, TTL e envelopes, alem de falhas injetadas de leitura/escrita; verificar que erros que escapam da infraestrutura recebem tratamento unico em `_operation`.
- [x] 4.6 Documentar configuracao e uso dos metodos cached, invalidacao herdada, pais e diferenca de retorno ORM/schema; verificar que exemplos usam os mecanismos existentes sem criar backend ou serializador paralelo.

## 5. Extensoes demonstradas e limitadas

- [x] 5.1 Adicionar subclasse de teste com normalizacao via helper existente e validacao de unicidade por owner em create/update; testar conflito 409, renomeacao, self-update e nomes iguais de owners diferentes sem override dos fluxos CRUD publicos.
- [x] 5.2 Demonstrar exclusao logica por extensao de persistencia e visibilidade, mantendo delete fisico como padrao; testar registro preservado, exclusao de listagem/busca e 404 na repeticao, sem alterar dominios ativos.
- [x] 5.3 Completar README com exemplos normalizado, exclusao logica e acao especializada usando `_operation`; verificar correspondencia com subclasses executaveis e explicitar que agregados, leitura compartilhada e migracao nao estao implementados.

## 6. Integracao e verificacao final

- [x] 6.1 Executar `poetry run pytest -q tests/app/temp` e `poetry run ruff check app/temp tests/app/temp` mais `poetry run ruff format --check app/temp tests/app/temp`; corrigir falhas introduzidas e registrar resultados.
- [x] 6.2 Inspecionar o diff e imports para confirmar que somente pacote experimental, seus testes e documentacao foram adicionados, sem imports de `app.temp` em `app/core`, `app/domain` ou `app/main.py`; verificar que modelos, migrations, rotas e dependencias permaneceram inalterados.
- [x] 6.3 Executar `make test` como verificacao integrada exigida pelo projeto e registrar o resultado; distinguir eventuais falhas preexistentes sem corrigi-las fora de escopo.

## Verification results

- `poetry run pytest -q tests/app/temp`: 77 passed.
- `poetry run ruff check app/temp tests/app/temp`: passed.
- `poetry run ruff format --check app/temp tests/app/temp`: 8 files already formatted.
- `make test`: lint passed; 1190 tests passed, 309 warnings; HTML coverage report generated.
- Scope inspection: only `app/temp/`, `tests/app/temp/` and this OpenSpec change were added; no active application imports of `app.temp`.
