# Tasks

## 1. Contratos e coordenacao dos subagentes

Responsavel: agente principal. Esta lista sera executada apenas em apply; a proposta nao inicia implementacao.

- [x] 1.1 Entregar os quatro artefatos aprovados aos dois subagentes em contextos limpos, definir a propriedade dos arquivos conforme design.md secao 8 e registrar o marco de contratos; verificar que nao ha arquivo de implementacao atribuido a ambos.
- [x] 1.2 Estabilizar com o subagente Negocio as assinaturas tipadas de transaction/find_by/find_by_name/list_all/save/delete e o plano puro de reconciliacao conforme design.md secao 5, sem adicionar uma infraestrutura paralela de interfaces; verificar o fluxo aprovado CategoryService -> CategoryRepository, sem SubcategoryService/SubcategoryRepository, e a compatibilidade entre servico e repositorio antes de iniciar 3 e 4.
- [x] 1.3 Orientar ambos os subagentes a seguir obrigatoriamente os testes unitarios de tests/app/domain/payer/ e tests/app/domain/account/, conforme design.md secao 9; verificar nas entregas a organizacao por camada, fixtures em conftest.py, marcadores async, mocks, asserts de chamadas e tratamento de erros no mesmo estilo, sem substituir os unitarios por testes de integracao.

## 2. Schemas e regras puras

Responsavel: subagente Negocio. Depende de 1.2. Propriedade: app/domain/category/__init__.py, schema.py, business.py e testes unitarios correspondentes.

- [x] 2.1 Criar schemas de criacao, atualizacao, reconciliacao e saida com campos extras proibidos e nomes normalizados por text_strip; verificar com testes os defaults, null versus omissao, campos gerenciados proibidos e UUIDs.
- [x] 2.2 Reutilizar validacao de nomes/cores entre raiz e filhos e validar order inteiro estrito positivo; verificar nomes vazios, #RRGGBB, null permitido, bool/float/string/zero/negativos rejeitados e ordens com lacunas aceitas.
- [x] 2.3 Implementar o plano puro de reconciliacao em business.py sem dependencias de infraestrutura; verificar duplicidade de ID/order, IDs desconhecidos/excluidos/de outra categoria, filhos inativos, lista vazia e troca de posicoes.
- [x] 2.4 Executar poetry run pytest tests/app/domain/category/test_category_schema.py tests/app/domain/category/test_category_business.py e Ruff nos arquivos dessa entrega; verificar que os contratos estao utilizaveis antes da persistencia e registrar o marco para 3.

## 3. Pacote de modelos e migration

Responsavel: subagente Persistencia/API, iniciado depois de 1.2 e 2.4. Propriedade: app/models/category/, app/models/__init__.py, descoberta Alembic, nova migration e testes locais de metadata/migration.

- [x] 3.1 Criar a pasta app/models/category/ com exatamente os arquivos de modelos category.py (Category -> categories), subcategory.py (Subcategory -> subcategories) e __init__.py exportando Category e Subcategory em __all__; verificar imports publicos e que ambas as tabelas pertencem a table_registry.metadata.
- [x] 3.2 Mapear os atributos, UUIDs gerados no servidor, timestamps, FKs e relacionamentos usando mapped_as_dataclass; verificar construcao dos modelos, filhos associados a raiz e ausencia de cascade fisica no fluxo de exclusao logica.
- [x] 3.3 Adicionar indice unico parcial de nome por proprietario, checks, indices e live_order gerado com constraint unica adiavel conforme design; verificar no PostgreSQL descartavel que nomes concorrentes e ordens repetidas sao bloqueados, mas historico excluido e trocas de ordem sao permitidos.
- [x] 3.4 Reexportar entidades em app/models/__init__.py e garantir sua descoberta pelo Alembic; gerar nova revisao com make create-migration message="add category aggregate" no ambiente apropriado e revisar upgrade/downgrade; verificar que nenhuma migration historica foi alterada.
- [x] 3.5 Adicionar testes de upgrade/downgrade/novo upgrade em PostgreSQL descartavel usando testcontainers existente; verificar criacao de categories/subcategories com FKs/constraints e remocao na ordem correta.
- [x] 3.6 Criar a secao de modelos/migration em app/domain/category/README.md, incluindo a arvore category.py/subcategory.py/__init__.py e a distincao entre definicao SQLAlchemy e criacao efetiva por Alembic; conferir os caminhos e comandos contra os arquivos entregues.

## 4. Repositorio e provas transacionais

Responsavel: subagente Persistencia/API. Depende de 3.2 e 3.3; os testes de migration permanecem responsabilidade do mesmo subagente. Propriedade: repository.py e testes de repositorio/integracao, incluindo conftest local.

- [x] 4.1 Criar CategoryRepository(BaseRepository[Category]) com buscas obrigatoriamente owner-scoped, exclusao logica filtrada, carregamento antecipado dos filhos vivos e ordenacao; verificar consultas para dois proprietarios, inativos visiveis e excluidos ocultos.
- [x] 4.2 Implementar list_all reutilizando FilterPage/paginacao sem multiplicar linhas pelo join dos filhos; verificar filtro name, total/paginas de categorias, lista sem page/offset e carregamento sem N+1/lazy loading na serializacao.
- [x] 4.3 Implementar transaction como unico responsavel por commit/rollback, adotando autobegin da sessao; save/delete apenas aplicam o agregado e fazem flush, sem chamar commits herdados; verificar sessao ja iniciada por autenticacao e falhas de flush e commit.
- [x] 4.4 Implementar bloqueio de raiz antes de recarregar filhos e aplicar o plano de reconciliacao, sem mutar ownership; verificar atualizacao, exclusao logica de ausentes, exclusao propagada e preservacao de timestamps antigos.
- [x] 4.5 Testar no PostgreSQL real trocas 1 <-> 2, reuso de ordem removida e restricoes concorrentes com sessoes independentes; verificar ausencia de conflitos transitorios e revalidacao depois de esperar pelo lock.
- [x] 4.6 Induzir falhas depois de writes parciais em criacao/alteracao/exclusao e no commit, consultar em nova sessao e verificar que nenhum fragmento foi persistido; nao aceitar apenas asserts de chamadas a rollback como evidencia.
- [x] 4.7 Documentar no README a fronteira transaction/save, locks, coluna gerada, constraints adiaveis e tratamento de erros identificados por constraint; verificar correspondencia com os testes reais e comunicar a entrega dos modelos/repositorio ao subagente Negocio.

## 5. Servico do agregado

Responsavel: subagente Negocio. Depende de 2.4, 3.2 e 4.3/4.4 para integracao executavel. Propriedade: service.py e test_category_service.py; nao editar modelos/repositorio nem o README sob responsabilidade do outro agente.

- [x] 5.1 Implementar CategoryService especializado com injecao/from_session e create/list_all/find_by/update/delete, delegando regras puras e persistencia; verificar ownership, defaults, lista completa, ausencia de upsert e consulta individual com filhos ordenados e 404 para desconhecido/alheio/excluido.
- [x] 5.2 Verificar nome normalizado na criacao/alteracao sem conflitar com o proprio ID, incluir inativos e ignorar excluidos; testar 409 para duplicidade, nomes iguais entre proprietarios e comparacao case-sensitive preservando acentos.
- [x] 5.3 Orquestrar uma unica transaction por mutacao e mapear erros de negocio/constraints para 422/409, inclusive falhas de commit; testar 404 para desconhecido/alheio/excluido, ausencia de sucesso falso e rollback preservado.
- [x] 5.4 Aplicar log_service_success somente depois do sucesso e handle_service_exception em todos os except do servico, sem introduzir cache; verificar testes unitarios de sucesso e propagacao explicita de falhas.
- [x] 5.5 Executar testes de schemas/business/service juntos e Ruff nos arquivos do subagente; verificar imports reais sem stubs pendentes e comunicar contrato final para 6.

## 6. API e documentacao de consumo

Responsavel: subagente Persistencia/API. Depende de 4.7 e 5.5. Propriedade: route.py, registro em app/main.py, testes HTTP, requests.http e README.

- [x] 6.1 Criar exatamente cinco endpoints: create POST /categories, update PUT /categories/{category_id}, list GET /categories, get GET /categories/{category_id} e delete DELETE /categories/{category_id}, com Depends(get_current_user), servico injetado e response_models explicitos; verificar no router/OpenAPI essas cinco combinacoes e nenhuma operacao adicional de categoria/subcategoria.
- [x] 6.2 Adicionar testes HTTP dos cinco endpoints com autenticacao, payloads validos/invalidos, isolamento, 201/200/401/404/409/422 e rejeicao de ownership/IDs gerenciados; verificar respostas CategorySchema/lista/paginacao/Message e GET individual com filhos ordenados, inativos visiveis, excluidos ocultos, 404 para alheio/desconhecido/excluido e 422 para UUID invalido.
- [x] 6.3 Adicionar testes HTTP de reconciliacao mista, lista vazia/omitida, null versus omissao na raiz e substituicao dos opcionais de cada filho; verificar filhos ordenados no GET e exclusao logica no banco.
- [x] 6.4 Criar app/domain/category/requests.http com variaveis de token/IDs e exemplos POST, GET de lista, GET por ID, PUT com inclusao/alteracao/remocao, PUT vazio e DELETE; conferir payloads com os schemas e nao incluir credenciais reais.
- [x] 6.5 Completar README com contratos, politica de nomes, erros, ownership, reconciliacao, exclusao logica, status inativo, testes e exemplos; verificar que a documentacao nao promete exclusao fisica, restauracao ou endpoints adicionais.

## 7. Seed de desenvolvimento

Responsavel: subagente Persistencia/API. Depende de 4.7; pode ocorrer antes de 6 em arquivos independentes.

- [x] 7.1 Criar scripts/data/categories.json com pelo menos cinco exemplos e dois filhos por categoria com ordens 1/2, e scripts/seed_categories.py usando SQLAlchemy async; verificar dados atraves dos schemas e ausencia de novas dependencias.
- [x] 7.2 Resolver o usuario existente usuario@formacao.dev e inserir somente exemplos ausentes numa transacao, sem sobrescrita/restauracao; testar duas execucoes, dados preexistentes, usuario ausente e rollback em falha.
- [x] 7.3 Exigir --confirm-development, documentar poetry run python -m scripts.seed_categories --confirm-development e mensagens de criado/ignorado/falha; verificar que sem confirmacao ou usuario nao ocorre escrita nem criacao de credenciais.

## 8. Integracao final e aplicacao controlada

Responsavel: agente principal. Depende de 3 a 7 concluidos. Este grupo somente integra/verifica entregas; testes e documentacao de cada grupo ja devem existir.

- [x] 8.1 Integrar as entregas dos dois subagentes, verificar os tres arquivos em app/models/category/, exports, imports, metadata e contratos compartilhados; confirmar exatamente cinco endpoints, persistencia via CategoryService -> CategoryRepository em transacao unica, ausencia de SubcategoryService/SubcategoryRepository, stubs e mudancas fora do escopo.
- [x] 8.2 Executar poetry run pytest tests/app/domain/category e make lint, incluindo PostgreSQL real para constraints/rollback/concorrencia; registrar explicitamente qualquer bloqueio de infraestrutura sem declarar essas provas concluidas.
- [x] 8.3 Com banco de desenvolvimento/teste confirmado, executar make migrate e o seed documentado; verificar revisao aplicada e cinco categorias com ao menos dois filhos cada, sem duplicacao na segunda execucao. Se banco/usuario estiver indisponivel, manter a tarefa pendente e informar o bloqueio.
- [x] 8.4 Executar make test e revisar o diff final; verificar comportamento existente preservado, separar falhas preexistentes das introduzidas e nao corrigir assuntos alheios.

## 9. Atualizacao da raiz sem reenviar filhos

- [x] 9.1 Tornar subcategories opcional por omissao no PUT e rejeitar null, sem reconciliar filhos ausentes; verificar schemas, servico e testes HTTP para renomeacao, [] e lista preenchida.
- [x] 9.2 Atualizar README e requests.http e comprovar em PostgreSQL que renomear preserva IDs, dados e timestamps dos filhos; executar testes de categoria, lint e validacao estrita OpenSpec.

## 10. Seed autenticado das categorias padrao

Os itens anteriores que exigiam exatamente cinco rotas registram a entrega
original; esta extensao adiciona explicitamente a sexta rota solicitada.

- [x] 10.1 Incluir o catalogo das 14 categorias e 59 filhos com icones reutilizados ou react-<componente>; implementar POST /categories/seed e CategoryService.seed_defaults em uma unica transacao, com ownership, contadores e preservacao de dados existentes.
- [x] 10.2 Cobrir autenticacao, idempotencia, isolamento, dados completos e rollback integral com testes unitarios e PostgreSQL; atualizar README/requests.http com o comando e a lista de icones ausentes e executar make test e validacao OpenSpec.

## Workflow follow-up

- Revisar a implementacao antes de solicitar archive; sincronizar specs conforme o fluxo OpenSpec.
- Arquivar somente depois da conclusao ou resolucao explicita das pendencias, nunca automaticamente ao terminar esta proposta.
