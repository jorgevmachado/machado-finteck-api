# Design

## Context

Ver proposal.md para motivacao e specs/category-management/spec.md para comportamento.

Evidencias do repositorio:
- AGENTS.md define route -> service -> repository -> models e business.py para regras puras.
- app/domain/payer/schema.py usa text_strip; payer/service.py usa consultas owner-scoped, from_session e helpers de logs/erros. Payer tambem possui name_code via to_snake_case, uma politica mais agressiva que a normalizacao de exibicao.
- account e credit_card possuem servicos especializados; seus campos color nao tem um VO compartilhado. Nao existem validadores reutilizaveis DueDay/ClosingDay no codigo-fonte atual.
- app/core/repository/base.py faz commit em save/update. Seus metodos nao podem ser usados para salvar separadamente raiz e filhos.
- get_current_user consulta o usuario pela mesma dependencia get_session; a AsyncSession pode estar em autobegin antes do servico.
- app/core/database/database.py fornece sessoes com expire_on_commit=False.
- tests/conftest.py usa FakeSession e testes de repositorio usam AsyncMock; isso nao prova rollback real. pyproject.toml ja inclui psycopg e testcontainers.
- Nao ha seed de categorias ou arquivos .http estabelecidos. Os arquivos .pyc antigos de category nao constituem modelos, testes ou migrations utilizaveis.

O design e necessario por incluir dois modelos relacionados, exclusao logica, concorrencia, constraints e uma migration.

## Goals / Non-Goals

**Goals:**
- Separar regras puras de reconciliacao, orquestracao e detalhes SQL.
- Ter uma fronteira transacional unica mesmo quando a autenticacao ja iniciou a sessao.
- Garantir consistencia no banco sem reordenacoes temporarias visiveis ou commits parciais.
- Fixar os contratos compartilhados antes do trabalho dos subagentes.

**Non-Goals:**
- Modificar o CRUD generico ou corrigir problemas preexistentes de outros dominios.
- Adicionar cache, restauracao, exclusao fisica, controle otimista por versao ou endpoints alem dos cinco CRUD e do seed solicitado posteriormente.
- Exigir igualdade com a normalizacao name_code de payer: categorias terao a politica explicita abaixo, sem alterar payer.

## Decisions

### 1. Camadas e propriedade dos arquivos

CategoryService sera especializado, como AccountService/PayerService, em vez de herdar metodos genericos que nao preservam ownership e agregado. Mantera injecao de CategoryRepository e from_session. O router apenas delega, inclusive GET; nao havera CQRS separado.

Decisao confirmada: rotas -> CategoryService -> CategoryRepository, preservando uma unica transacao de escrita para Category e Subcategory. Nao criar SubcategoryService nem SubcategoryRepository. O servico da raiz pode chamar save/delete do repositorio do agregado dentro de transaction(); nao executa SQL nem commit e nao grava filhos isoladamente.

CategoryRepository estendera BaseRepository[Category] e reutilizara listagem/paginacao quando preservarem os predicados obrigatorios. Escritas, carregamento de filhos e bloqueio serao especializados.

business.py recebera dados tipados e o estado dos filhos existentes, sem sessao, FastAPI ou SQLAlchemy, e produzira um plano de reconciliacao: atualizacoes, criacoes e IDs a excluir logicamente. Os DTOs de entrada tipados e as estruturas simples do plano nao exigem novas classes de entidade nem VOs.

Antes de construir/mutar objetos ORM, o servico valida o plano final completo. O repositorio aplica o plano; nao decide regras de negocio.

### 2. Contratos de entrada, saida e erros

Todos os schemas de entrada usam extra="forbid". Campos de identificacao UUID devem rejeitar null explicito quando sua omissao significa criacao.

| Schema | Campos e semantica |
|---|---|
| CategoryCreateSchema | name obrigatorio; icon/color opcionais null; is_active=True; subcategories=[] por default_factory |
| SubcategoryCreateSchema | name e order obrigatorios; icon/color null e is_active=True; nao aceita id |
| CategoryUpdateSchema | subcategories opcional por omissao: preserva filhos; [] remove todos; lista preenchida reconcilia; null rejeitado; name/is_active opcionais apenas por omissao e rejeitam null; icon/color omitidos preservam e null limpa |
| SubcategoryReconcileSchema | name/order obrigatorios; id omitido para novo, UUID para existente; icon/color omitidos tornam-se null e is_active omitido torna-se True |
| CategorySchema | id/name/icon/color/is_active/created_at/updated_at/deleted_at e lista ordenada de SubcategorySchema |
| SubcategorySchema | id/name/icon/color/is_active/order/created_at/updated_at/deleted_at |

Schemas de saida usam from_attributes=True sem importar classes ORM. user_id, category_id e colunas auxiliares nunca aparecem na resposta. IDs de raiz no body e timestamps de entrada sao proibidos.

O PUT tem semantica parcial nos atributos da raiz, como os dominios existentes. A lista subcategories e opcional: sua omissao preserva todos os filhos, sem construir ou aplicar plano de reconciliacao; null explicito e rejeitado. Quando informada, a lista substitui o conjunto completo e as propriedades de cada filho; [] exclui todos logicamente. Um filho existente deve reenviar name/order e seus opcionais desejados. O servico passa reconciliation=None ao repositorio quando a lista e omitida, mantendo a mesma transacao unica, validacao de nome e ownership.

O router /categories tera os cinco endpoints CRUD abaixo e o endpoint de seed definido na secao 10:

| Operacao na rota | Metodo e caminho | Resposta | Delegacao ao servico |
|---|---|---|---|
| create | POST /categories | 201 CategorySchema | create |
| update | PUT /categories/{category_id} | 200 Message | update |
| list | GET /categories | 200 list[CategorySchema] ou CustomLimitOffsetPage[CategorySchema] | list_all |
| get | GET /categories/{category_id} | 200 CategorySchema | find_by |
| delete | DELETE /categories/{category_id} | 200 Message | delete |

Path usa UUID e todas as rotas usam o usuario autenticado. O nome da funcao de rota list nao altera o nome list_all do servico, preservado por consistencia com os dominios existentes. O get delega a find_by do CategoryService e retorna a raiz viva com filhos vivos ordenados, inclusive inativos; devolve 404 para categoria inexistente, excluida ou de outro usuario e 422 para UUID invalido. Nao adicionar rotas de subcategorias.

GET expoe page, offset, limit (default 12) e name, seguindo o filtro de payer. Paginacao usa is_paginate/get_limit_offset_params existentes; sem page/offset retorna lista. O servico sobrescreve user_id com user.id; nunca expoe filtro de proprietario. Ordenacao de categorias sera created_at, id para estabilidade; filhos sempre order crescente.

Validacao escalar e do plano gera 422; categorias inexistentes/inacessiveis geram 404; duplicidade de nome gera 409; autenticacao fica em Depends(get_current_user). Erros de dominio puros sao convertidos no servico sem capturar indiscriminadamente ValueError de infraestrutura. Todo except de servico usa handle_service_exception; sucesso so e registrado apos a operacao concluida.

### 3. Nomes, cor e ordem

Reutilizar text_strip para armazenar nomes e comparar nomes de categoria por igualdade exata apos normalizacao de whitespace. Comparacao sera case-sensitive, preservando acentos e pontuacao. Nao criar name_code: to_snake_case tambem remove caracteres e faria nomes distintos colidirem, inclusive nomes Unicode sem representacao ASCII. Essa e uma decisao especifica do novo dominio, nao alteracao da politica de payer.

Reutilizar a mesma validacao Pydantic de nome/cor em raiz e filhos sem copiar implementacoes. Cor deve corresponder integralmente a #[0-9a-fA-F]{6}; null e permitido e nao ha conversao obrigatoria de caixa. Ordem usa inteiro estrito positivo, sem coercao de bool, float ou string. business.py valida unicidade da ordem e dos IDs no estado final, incluindo filhos inativos.

Nao impor unicidade de nomes de subcategorias nem contiguidade de ordens.

### 4. Modelos, constraints e exclusao logica

Criar obrigatoriamente uma pasta category dentro de app/models, com esta estrutura:

```text
app/models/
    category/
        category.py
        subcategory.py
        __init__.py
```

- app/models/category/category.py define a entidade ORM Category e o mapeamento da tabela categories.
- app/models/category/subcategory.py define a entidade ORM Subcategory e o mapeamento da tabela subcategories.
- app/models/category/__init__.py importa e exporta Category e Subcategory, incluindo ambas em __all__.
- app/models/__init__.py reexporta as duas entidades, seguindo o acesso publico dos outros modelos.

Esses modelos sao a definicao estrutural das tabelas na base de dados: colunas, tipos, chaves, relacionamentos e constraints compoem table_registry.metadata. O Alembic usa essa metadata para gerar a migration; executar a migration cria efetivamente as tabelas. Nao criar as tabelas por efeito colateral de import nem confundir estes arquivos com os contratos Pydantic de app/domain/category/schema.py. Garantir que a descoberta de modelos em migrations/env.py carregue ambas as entidades, sem dependencias circulares de import.

Usar table_registry.mapped_as_dataclass, Mapped, mapped_column e utcnow; UUIDs e campos gerenciados pelo servidor ficam init=False. Tabelas: categories e subcategories. Category possui FK users.id e Subcategory possui FK categories.id, nao anulaveis.

Relacionamentos devem permitir salvar filhos com a raiz, sem delete-orphan ou cascade de exclusao fisica no fluxo de negocio. Leituras normais incluem apenas deleted_at IS NULL, mas nao filtram is_active.

No PostgreSQL:
- Indice unico parcial nomeado uq_categories_owner_name_live em (user_id, name), WHERE deleted_at IS NULL, com comparacao deterministica case-sensitive.
- Check de nome nao vazio na raiz e no filho, CHECK ("order" > 0), campos obrigatorios NOT NULL e checks de cor opcionais compativeis com o contrato.
- Indice de busca owner/deleted_at e indice de FK category_id.
- Coluna interna gerada live_order em subcategories: CASE WHEN deleted_at IS NULL THEN "order" ELSE NULL END.
- Constraint uq_subcategories_category_live_order UNIQUE (category_id, live_order) DEFERRABLE INITIALLY DEFERRED. Usar o comportamento padrao de NULLs distintos; nao usar NULLS NOT DISTINCT.

A coluna gerada nunca entra nos schemas nem recebe valor do cliente. Ela torna a unicidade dos filhos vivos adiavel ate o commit, permitindo trocas 1 <-> 2 e reutilizacao de ordem sem valores temporarios ou restauracoes transitorias. Um indice unico parcial simples nao pode ser DEFERRABLE no PostgreSQL; por isso foi descartado para a ordem. UNIQUE(category_id, order) tambem foi descartado por bloquear historico logicamente excluido.

O usuario confirmou exclusao logica tambem na reconciliacao. Quando subcategories e informada, filhos ausentes dessa lista recebem deleted_at e is_active=False; seus IDs nao podem reaparecer em PUT. DELETE atribui um mesmo utcnow a raiz e aos filhos ainda vivos e preserva timestamps de filhos excluidos anteriormente. updated_at e atualizado nos registros modificados. Alterar apenas is_active nunca exclui nem restaura.

### 5. Contrato do repositorio e fronteira transacional

Contrato compartilhado a estabilizar antes dos subagentes implementarem:
- transaction(): contexto async que adota a transacao corrente da sessao ou inicia uma se necessario, faz um unico commit na saida bem-sucedida e rollback em qualquer falha, inclusive falha no commit.
- find_by(id=..., user_id=..., for_update=False): retorna raiz viva e filhos vivos carregados, ou None; for_update e usado nas mutacoes.
- find_by_name(name=..., user_id=..., exclude_id=None): consulta para antecipar conflito.
- list_all(page_filter): aplica ownership, exclusao e carregamento ordenado; preserva o contrato de paginacao.
- save(entity, reconciliation=None): persiste raiz e plano completo, faz flush mas nunca commit, devolve agregado carregado.
- delete(entity): aplica exclusao logica completa com flush, nunca commit.

save/delete somente podem ser chamados dentro de transaction(); nao ha chamada por filho nem SubcategoryRepository. O contrato explicito e "save persiste o agregado inteiro; transaction confirma tudo ou desfaz tudo". Nao chamar os save/update herdados que fazem commit.

Fluxo: o servico entra em repository.transaction(), busca/valida, prepara o plano e chama save/delete. A saida do contexto e o unico ponto de commit. O servico nao chama session.commit nem abre session.begin sobre autobegin. A sessao e request-scoped; nao pode conter escritas alheias pendentes. Nao suportar contextos transacionais aninhados silenciosamente.

Mapear IntegrityError de uq_categories_owner_name_live para 409, inclusive quando surgir no commit. Mapear conflito residual da constraint de ordem para 422. Identificar constraints pelo diagnostico do driver, nao por substring generica de mensagens. Outros erros de integridade/infraestrutura continuam sendo erros explicitos; sempre efetuar rollback antes de reaproveitar a sessao.

Na criacao, carregar os filhos ainda dentro da transacao e antes de retornar; com expire_on_commit=False a serializacao nao precisa consultar a sessao apos o commit.

### 6. Concorrencia e carregamento

PUT/DELETE bloqueiam a raiz com SELECT ... FOR UPDATE, filtrando por id, user_id e deleted_at IS NULL. Carregar/recarregar os filhos apos adquirir o bloqueio, evitando snapshot antigo no identity map (populate_existing quando necessario). Validar contra esse estado atual. Locks permanecem ate commit/rollback.

Assim, mutacoes concorrentes no mesmo agregado sao serializadas. Nao ha ETag: duas atualizacoes validas de atributos seguem a ordem dos commits; uma requisicao que referencia filho ja excluido falha com 422. Uma atualizacao que espera por DELETE encontra raiz excluida e retorna 404.

Para consultas, usar selectinload com criterio de exclusao de filhos e order_by do relacionamento. Evitar join de colecao no SELECT de paginacao para nao duplicar categorias nem distorcer total. A quantidade de consultas cresce por lote, nao por categoria. Nunca depender de lazy loading na serializacao.

### 7. Seed, exemplos e documentacao

Adicionar scripts/seed_categories.py e scripts/data/categories.json. Usar SQLAlchemy async e settings existentes, sem nova biblioteca. Comando previsto: poetry run python -m scripts.seed_categories --confirm-development.

Exigir confirmacao explicita e banco de desenvolvimento/teste identificado pelo operador; nao tentar inferir seguranca apenas pelo hostname. Resolver usuario@formacao.dev antes de inserir; se ausente, abortar sem criar usuario/credenciais.

Dados previstos: Alimentacao (Mercado, Restaurantes), Moradia (Aluguel, Manutencao), Transporte (Combustivel, Transporte publico), Saude (Consultas, Medicamentos), Lazer (Cinema, Viagens); ordens 1 e 2 em cada categoria.

Seed insere somente exemplos ainda ausentes por nome normalizado, sem atualizar categorias/filhos preexistentes ou restaurar exclusoes. Se o nome ja existir, preservar o agregado inteiro e informar que foi ignorado. Resolver concorrencia com o mesmo indice unico; conflito de outra execucao exige rollback e mensagem clara, nao sucesso falso. Uma execucao sem falhas confirma os novos exemplos em uma unica transacao.

Exemplos em app/domain/category/requests.http: variaveis base_url/token/category_id/child_id, POST, GET de listagem, GET por ID, PUT misto, PUT vazio e DELETE, sem token ou senha reais. README do dominio explica os cinco endpoints, contratos, mensagens, isolamento, exclusao logica, comando de seed e limites ambientais.

### 8. Divisao em dois subagentes durante apply

O agente principal entrega a ambos proposal/design/spec/tasks aprovados e o contrato da secao 5; nenhum subagente recebe apenas uma referencia vaga a esta conversa.

- Subagente Negocio: app/domain/category/{__init__,schema,business,service}.py e testes unitarios test_category_schema.py, test_category_business.py e test_category_service.py.
- Subagente Persistencia/API: app/models/category/, app/domain/category/{repository,route}.py, registros em main/models, migration, descoberta Alembic, seed, requests.http, README e testes de repositorio/rotas/integracao, incluindo conftest local.
- Agente principal: estabilizar contratos, coordenar dependencia, integrar e validar; nao delegar a implementacao nesta etapa de proposta.

O arquivo tests/app/domain/category/conftest.py e de propriedade exclusiva de Persistencia/API. Ate sua entrega, Negocio reutiliza fixtures globais e declara fixtures especificas nos seus proprios arquivos de teste; comunica as fixtures compartilhadas necessarias para Persistencia/API consolida-las no conftest local. Nao editar esse arquivo simultaneamente.

Primeiro concluir os contratos tipados e seus testes com o subagente Negocio; depois iniciar Persistencia/API para modelos e repositorio. A conclusao executavel do servico depende desses modelos; apos sua entrega, o subagente Negocio termina a integracao e o outro termina rotas/integracao. Evitar imports de classes inexistentes como entrega final, arquivos stub persistentes e edicoes de um mesmo arquivo pelos dois agentes. Ambos podem trabalhar so em arquivos independentes depois do marco de contratos.

### 9. Padrao obrigatorio dos testes unitarios

Usar tests/app/domain/payer/ e tests/app/domain/account/ como referencia concreta de organizacao, fixtures e estilo, sem criar um padrao de testes paralelo:

- Organizar em tests/app/domain/category/ os arquivos conftest.py, test_category_schema.py, test_category_business.py, test_category_service.py, test_category_repository.py e test_category_route.py.
- Seguir tests/app/domain/payer/conftest.py e tests/app/domain/account/conftest.py para fixtures locais de entidades e payloads Pydantic; reutilizar a fixture user e a infraestrutura compartilhada de tests/conftest.py quando adequadas.
- Seguir test_payer_schema.py para pytest.mark.parametrize, pytest.raises(ValidationError), normalizacao e diferenca entre omissao e null.
- Seguir test_account_service.py e test_payer_service.py para agrupamento por operacao, pytest.mark.asyncio, AsyncMock/Mock/patch, injecao de repositorio e asserts assert_awaited_once_with, verificando argumentos, ownership, retornos e falhas.
- Simular corretamente o contexto async transaction do novo repositorio, sem substituir metodos sincronos por AsyncMock indiscriminadamente.
- Seguir test_payer_route.py e test_account_route.py para TestClient, dependency_overrides de autenticacao/servico e verificacao de delegacao e contratos HTTP; limpar os overrides apos cada teste.
- Seguir os testes de repositorio de payer/account para verificacoes unitarias de interacao com a sessao, adaptando as expectativas ao contrato novo de flush sem commits intermediarios. Nao copiar exclusao fisica nem outras regras incompativeis.

Reproduzir o estilo e os mecanismos de teste, nao assertions triviais ou regras de negocio alheias. Os testes de business.py devem exercitar diretamente as regras puras, sem banco. Manter os testes reais de PostgreSQL separados dos unitarios: eles complementam esse padrao para provar atomicidade, locks e constraints que mocks nao demonstram.

### 10. Catalogo padrao por usuario (extensao posterior)

POST /categories/seed nao recebe payload e usa exclusivamente o usuario do JWT.
Retorna 200 CategorySeedSchema com created e skipped. O catalogo versionado em
app/domain/category/default_categories.json contem exatamente as 14 categorias
e 59 filhos fornecidos, preservando nomes, cores e ordens. defaults.py carrega
e valida esses dados com CategoryCreateSchema.

CategoryService.seed_defaults consulta cada nome normalizado por proprietario;
categorias vivas ja existentes, inclusive inativas, sao ignoradas integralmente,
sem sobrescrever nem completar filhos. Insere todas as ausentes numa unica
repository.transaction(), reutilizando a construcao do agregado de create.
Nao chama create em loop porque isso confirmaria transacoes intermediarias.
Repetir a chamada nao duplica os padroes. Nomes excluidos podem ser reutilizados
sem restaurar registros historicos. Conflitos concorrentes mantem a protecao do
indice unico, retornam 409 e desfazem todo o lote; outras falhas tambem desfazem
todas as categorias inseridas. Nao executar o seed automaticamente no deploy.

Usar as chaves publicas de @machado-repo/icons quando houver substituto
apropriado; para icones ausentes, persistir react-<NomeDoComponente> e listar
os exports reais de react-icons/fa6 no README. Essas referencias ainda precisam
de registro no frontend; esta mudanca nao altera o outro repositorio.
O script de exemplos de desenvolvimento permanece separado e inalterado.

## Risks / Trade-offs

- [Nome distingue caixa e acentos] -> Politica explicita nos contratos e testes; nao presumir a equivalencia mais ampla de payer.
- [Coluna gerada e unicidade adiavel dependem de PostgreSQL] -> Verificar no banco real, nao tratar SQLite como prova equivalente.
- [Autobegin e commit compartilhado com autenticacao] -> Uma unica fronteira request-scoped, sem escritas alheias e com rollback em falha de commit.
- [Historico cresce com exclusao logica] -> Filtrar exclusoes consistentemente e indexar consultas; retencao/purge fica fora deste escopo.
- [Validacoes e locks nao substituem constraints concorrentes] -> Testar corrida de nomes e mutacoes sobre o mesmo agregado com sessoes independentes.
- [Ambiente externo indisponivel] -> Documentar bloqueio de migration/seed/teste real; nunca afirmar aplicacao ou atomicidade comprovada apenas por mocks.

## Migration Plan

1. Registrar os modelos na metadata e gerar nova revisao com make create-migration message="add category aggregate"; revisar a revisao contra a head atual, sem reutilizar .pyc ou alterar historico.
2. Revisar upgrade/downgrade, colunas geradas, constraints adiaveis, collation deterministica, defaults e FKs. Usar migration manual complementar dentro da nova revisao se o autogenerate nao representar todos os detalhes.
3. Testar upgrade, downgrade e novo upgrade em PostgreSQL descartavel via testcontainers, ja disponivel no projeto. Downgrade deve remover filhos antes da raiz e implica perda dos novos dados.
4. Aplicar com make migrate somente no banco de desenvolvimento/teste confirmado; nao criar ou apagar banco compartilhado para testes.
5. Executar seed com confirmacao e usuario existente; relatar quantidades criadas/ignoradas.
6. Executar testes direcionados, make lint e make test. Testes reais devem consultar nova sessao apos falha induzida de flush/commit para comprovar ausencia de escrita parcial.
7. Em rollback de deploy, desabilitar/reverter a nova API antes de remover tabelas. Preferir manter tabelas quando houver dados a preservar; downgrade destrutivo somente com backup e aprovacao explicita.

## Open Questions

Nenhuma decisao funcional bloqueante. O nome/URL do banco de desenvolvimento e a disponibilidade de Docker/PostgreSQL serao confirmados na aplicacao, sem alterar contratos ou executar infraestrutura agora.
