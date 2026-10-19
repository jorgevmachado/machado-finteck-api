# Proposal

## Why

A API ainda nao oferece categorias com subcategorias pertencentes ao usuario para organizar seus dados financeiros. Um agregado unico permite gerenciar essa hierarquia sem registros parcialmente salvos, acesso entre proprietarios ou ordens de exibicao inconsistentes.

## What Changes

- Adicionar Category como raiz e Subcategory como entidade filha, com UUIDs gerados no servidor, metadados visuais, status e timestamps.
- Expor os cinco endpoints CRUD de categoria, autenticados e limitados ao proprietario: create (POST /categories), update (PUT /categories/{category_id}), list (GET /categories), get (GET /categories/{category_id}) e delete (DELETE /categories/{category_id}).
- Acrescentar POST /categories/seed como sexta operacao autenticada para inserir as 14 categorias padrao e 59 subcategorias solicitadas. Reutilizar icones do pacote @machado-repo/icons quando equivalentes; nos demais casos usar referencias react-<componente> de react-icons/fa6, sem modificar o frontend.
- Validar nomes, cores hexadecimais, inteiros positivos e consistencia da lista completa de subcategorias.
- Permitir atualizacao apenas da raiz: no PUT, omitir subcategories preserva os filhos; [] exclui todos logicamente; uma lista preenchida reconcilia o conjunto completo; null retorna 422.
- Reconciliar filhos na atualizacao e excluir logicamente os ausentes, conforme decisao confirmada pelo usuario; excluir logicamente a raiz e seus filhos na mesma transacao.
- Garantir atomicidade, unicidade concorrente de nomes por usuario e de ordens por categoria, inclusive durante trocas de posicao.
- Adicionar migration Alembic, seed idempotente de desenvolvimento, testes automatizados, exemplos REST Client e documentacao do dominio.
- Os testes unitarios deverao seguir obrigatoriamente os exemplos existentes em tests/app/domain/payer/ e tests/app/domain/account/: mesma organizacao por camada, fixtures pytest, mocks das dependencias e convencoes de testes async e de erros. Testes com banco real complementam, nao substituem, esses testes unitarios.
- Planejar a aplicacao com dois subagentes de contexto limpo, compartilhando contratos aprovados e sem edicoes concorrentes dos mesmos arquivos.

Nao criar endpoints de subcategorias, restauracao, integracao com lancamentos financeiros, hierarquia de VOs, CQRS ou infraestrutura TypeScript/Prisma. Nao alterar o comportamento de account, payer ou credit_card. Esta etapa modifica somente artefatos OpenSpec.

## Capabilities

### New Capabilities

- `category-management`: ciclo de vida de categorias e subcategorias como agregado autenticado, com validacao, reconciliacao, isolamento, ordenacao, persistencia atomica e carga de exemplos.

### Modified Capabilities

Nenhuma. O inventario atual de specs esta vazio.

## Impact

- Novo dominio em app/domain/category/ e novo pacote app/models/category/ contendo category.py (modelo Category/tabela categories), subcategory.py (modelo Subcategory/tabela subcategories) e __init__.py exportando as duas entidades.
- Esses arquivos sao os mapeamentos SQLAlchemy usados na metadata para gerar as migrations que constroem as tabelas na base de dados; nao sao schemas Pydantic nem criam tabelas automaticamente por simples import.
- Registro do router em app/main.py, exports de modelos e descoberta de metadata pelo Alembic.
- Nova revisao em migrations/versions/ para categories, subcategories, FKs, constraints e indices.
- Na implementacao, sera obrigatorio gerar a migration com `make create-migration message="add category aggregate"` e, depois de revisar o arquivo gerado, aplicar as migrations com `make migrate` no banco de desenvolvimento/teste confirmado.
- O primeiro comando executa `alembic revision --autogenerate` a partir da metadata dos modelos SQLAlchemy; o segundo executa `alembic upgrade head`, criando efetivamente as tabelas e suas constraints no banco. Nao substituir esse fluxo por `metadata.create_all()` na aplicacao.
- Verificar a revisao aplicada e a existencia das tabelas categories/subcategories apos `make migrate`. Se o banco estiver indisponivel, registrar o bloqueio e manter a execucao pendente, sem declarar as tabelas criadas.
- Fluxo aprovado: rotas -> CategoryService -> CategoryRepository. CategoryService orquestra regras, logs e persistencia do agregado completo; CategoryRepository especializa BaseRepository e sua fronteira transacional confirma ou desfaz raiz e filhos juntos, sem commits intermediarios.
- Nao criar SubcategoryService, SubcategoryRepository ou gravacoes independentes de filhos. CategoryService pode chamar save/delete do CategoryRepository dentro da transacao unica; nunca executa SQL, commit ou persistencia isolada de subcategorias.
- Novos testes em tests/app/domain/category/, com PostgreSQL isolado para comprovar transacoes e constraints; exemplos .http e scripts/dados de seed.
- Nenhuma nova biblioteca de runtime prevista. Dependencias e infraestrutura de teste existentes devem ser reutilizadas.
- Aplicacao de migration e seed depende de banco de desenvolvimento/teste disponivel e explicitamente identificado; nao executar nesta proposta.
