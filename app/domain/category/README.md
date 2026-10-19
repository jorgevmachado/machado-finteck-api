# Categorias

Categorias e subcategorias formam um unico agregado pertencente a um usuario.
Leituras e alteracoes sao limitadas ao proprietario; registros inativos continuam
visiveis, enquanto registros excluidos logicamente sao omitidos das consultas
normais.

## Persistencia e migration

Os modelos SQLAlchemy estao em:

```text
app/models/category/
├── category.py
├── subcategory.py
└── __init__.py
```

`Category` mapeia `categories` e `Subcategory` mapeia `subcategories`. Importar
esses modelos registra as tabelas em `table_registry.metadata`, mas nao cria
tabelas. A criacao efetiva e controlada por uma revisao Alembic:

```bash
make create-migration message="add category aggregate"
make migrate
```

Revise a nova revisao antes de aplica-la. Ela cria a FK da categoria para
`users`, a FK do filho para a categoria, checks de nome/cor/ordem e os indices
necessarios. A migration de downgrade remove primeiro `subcategories` e depois
`categories`. Migrations historicas nao devem ser alteradas.

`uq_categories_owner_name_live` e um indice unico parcial sobre proprietario e
nome para categorias nao excluidas. A comparacao e case-sensitive e preserva
acentos; a normalizacao da camada de entrada remove espacos externos e colapsa
whitespace interno.

`subcategories.live_order` e uma coluna gerada: recebe `order` quando o filho
esta vivo e `NULL` quando foi excluido. A constraint
`uq_subcategories_category_live_order` e `UNIQUE DEFERRABLE INITIALLY DEFERRED`,
permitindo trocar ordens ou reutilizar uma ordem removida na mesma transacao.
As ordens vivas devem ser positivas e unicas dentro da categoria; lacunas sao
permitidas.

## Transacoes do agregado

`CategoryRepository.transaction()` e a unica fronteira de commit e rollback.
Ela adota a transacao que a sessao async possa ter iniciado por autobegin, ou
abre uma quando ainda nao existe; contextos aninhados nao sao suportados.
`save()` e `delete()` exigem essa fronteira, aplicam a raiz e os filhos como
uma unidade e fazem `flush`, sem commits intermediarios ou exclusoes fisicas.
Uma falha de flush ou commit provoca rollback antes de a sessao ser reutilizada.

Mutacoes devem buscar a raiz com `find_by(..., for_update=True)`. O repositorio
bloqueia primeiro a raiz, recarrega depois os filhos vivos e ordenados e mantem
o lock ate o commit. A lista reconciliada e aplicada como estado final, assim
trocas de posicao nao precisam de ordens temporarias. Filhos ausentes recebem
exclusao logica; timestamps anteriores de filhos ja excluidos sao preservados.

Conflitos do indice `uq_categories_owner_name_live` devem ser convertidos pela
camada de servico em HTTP 409, inclusive quando aparecem no commit. Conflitos
de `uq_subcategories_category_live_order` indicam uma ordem final duplicada e
devem ser convertidos em HTTP 422. Outras falhas de integridade e infraestrutura
nao devem ser ocultadas como sucesso ou resultado vazio.

As consultas usam `selectinload` para filhos vivos ordenados, incluindo os
inativos. A listagem filtra e pagina categorias-raiz, nao linhas de filhos, e
carrega filhos por lote para evitar N+1.

## API

O router de categorias expoe somente:

| Metodo | Caminho | Operacao |
| --- | --- | --- |
| `POST` | `/categories` | Criar categoria e filhos |
| `POST` | `/categories/seed` | Criar categorias padrao para o usuario autenticado |
| `PUT` | `/categories/{category_id}` | Atualizar raiz e reconciliar a lista completa de filhos |
| `GET` | `/categories` | Listar categorias proprias, com filtro por nome e paginacao opcional |
| `GET` | `/categories/{category_id}` | Ler uma categoria propria |
| `DELETE` | `/categories/{category_id}` | Excluir logicamente o agregado |

Todas as operacoes exigem autenticacao; o proprietario e sempre derivado do
usuario autenticado. Um recurso desconhecido, excluido ou pertencente a outro
usuario retorna 404. Nao ha endpoints independentes de subcategorias.

`POST /categories` responde `201` com o agregado criado; `GET` responde `200`; `PUT` e
`DELETE` respondem `200` com `{"message": "..."}`. Credenciais ausentes ou
invalidas respondem `401`, dados de entrada invalidos e ordens/IDs de filhos
inconsistentes respondem `422`, e nomes duplicados para o mesmo proprietario
respondem `409`. IDs malformados no caminho tambem respondem `422`.

Na listagem, `name` filtra por nome e `page`, `offset` e `limit` ativam o
envelope de paginacao existente. Sem `page` ou `offset`, a resposta e uma lista,
mesmo que `limit` seja informado. A paginacao e contabilizada por categoria;
cada categoria inclui seus filhos vivos, ordenados, inclusive os inativos.

Nomes sao normalizados removendo espacos externos e colapsando whitespace.
Categorias do mesmo usuario nao podem repetir nome normalizado entre registros
vivos, inclusive inativos; a comparacao distingue caixa e preserva acentos.
Cores sao `null` ou `#RRGGBB`; a ordem e um inteiro estrito positivo.

No `PUT`, omitir `subcategories` preserva todos os filhos, permitindo alterar
somente o nome com `{"name": "Novo nome"}`. Enviar `null` retorna 422; enviar
`[]` exclui todos os filhos logicamente. Quando enviada, a lista `subcategories`
deve representar o conjunto completo desejado. Filhos existentes sao
identificados por `id`; filhos novos omitem `id`. Filhos retidos sao atualizados,
novos sao criados e os omitidos sao excluidos logicamente. Omitir um campo
opcional de um filho redefine-o para seu default (`icon`/`color` nulos e
`is_active` verdadeiro). Na raiz, campos opcionais omitidos permanecem iguais;
`icon` e `color` podem ser limpos com `null`.

Um payload de criacao nao aceita IDs ou timestamps gerenciados. O `PUT` recebe o
ID da categoria apenas no caminho e aceita IDs somente para identificar filhos
vivos desse mesmo agregado. Ownership, `category_id`, IDs de raiz no body e
campos internos nao fazem parte da resposta publica.

Exemplos REST Client completos para criacao, listagem, leitura, reconciliacao
mista, lista vazia e exclusao estao em `requests.http`.

## Categorias padrao via API

Execute `POST /categories/seed` com o mesmo JWT das outras rotas, sem body.
O endpoint insere as 14 categorias e 59 subcategorias do catalogo
`default_categories.json` exclusivamente para o usuario autenticado:
Moradia, Alimentação, Transporte, Saúde, Educação, Lazer, Vestuário,
Contas e Serviços, Cuidados Pessoais, Filhos e Família, Pets,
Financeiro e Investimentos, Presentes e Doações e Impostos e Taxas.
Nomes, cores e ordens seguem os dados solicitados; todos iniciam ativos.

Em um usuario sem esses dados, a resposta e `200`:

```json
{"created": 14, "skipped": 0}
```

Repetir a chamada retorna `{"created": 0, "skipped": 14}`. Uma categoria viva
com o mesmo nome normalizado, inclusive inativa, e ignorada integralmente:
nao altera atributos nem adiciona/remove seus filhos. Categorias de outros
usuarios nao interferem. Um nome excluido logicamente pode receber um novo
agregado com novos IDs, sem restaurar o historico.

O lote inteiro usa uma unica transacao do repositorio. Se qualquer insercao
ou commit falhar, nenhuma categoria nova do lote e confirmada. Um conflito
concorrente de nome retorna `409`; nesse caso, repita a chamada apos o conflito.
Nao ha execucao automatica ao iniciar a aplicacao nem alteracao de dados de
outros usuarios. O novo endpoint e a sexta operacao do router, alem das cinco CRUD.
Nao exige migration adicional.

### Icones do catalogo

Foram consultadas as chaves de `packages/icons/src/options/option.ts` e suas
implementacoes em `src/groups/` no projeto `machado-comprovante-web`.
As chaves reutilizadas sao: `home`, `bolt`, `store`, `umbrella`, `like`,
`school`, `book`, `gamepad`, `tv`, `map`, `receipt`, `phone`, `laptop`,
`brush`, `shower`, `box`, `wallet`, `landmark`, `credit-card`,
`hand-holding` e `document`. Por exemplo, `like` e um coracao,
`hand-holding` representa uma mao com dinheiro, `document` tem implementacao
nos grupos io/io5/md e `umbrella` substitui a protecao de seguros.

Para os itens sem substituto adequado, os valores abaixo sao referencias
pendentes, **nao chaves ja disponiveis no pacote**. Os componentes foram
verificados nos exports de `react-icons/fa6`:

| Valor persistido em `icon` | Uso |
| --- | --- |
| `react-FaBuilding` | Aluguel/financiamento e condominio |
| `react-FaDroplet` | Agua e esgoto |
| `react-FaFire` | Gas |
| `react-FaWifi` | Internet e TV |
| `react-FaWrench` | Manutencao e reparos |
| `react-FaUtensils` | Alimentacao e restaurantes |
| `react-FaBreadSlice` | Padaria |
| `react-FaCarrot` | Feira |
| `react-FaCar` | Transporte, veiculo e IPVA |
| `react-FaGasPump` | Combustivel |
| `react-FaBus` | Transporte publico |
| `react-FaTaxi` | Aplicativos de transporte |
| `react-FaSquareParking` | Estacionamento e pedagio |
| `react-FaShieldHeart` | Plano de saude |
| `react-FaPills` | Farmacia |
| `react-FaStethoscope` | Consultas e exames |
| `react-FaDumbbell` | Academia e bem-estar |
| `react-FaTicket` | Eventos e shows |
| `react-FaShirt` | Vestuario e roupas |
| `react-FaShoePrints` | Calcados |
| `react-FaClock` | Acessorios/relogio |
| `react-FaScissors` | Cabeleireiro e banho/tosa |
| `react-FaBaby` | Filhos/familia e creche/baba |
| `react-FaPaw` | Pets e acessorios para pets |
| `react-FaBone` | Racao e petiscos |
| `react-FaSyringe` | Veterinario e vacinas |
| `react-FaPiggyBank` | Financeiro/investimentos e poupanca |
| `react-FaChartLine` | Investimentos |
| `react-FaPercent` | Taxas bancarias |
| `react-FaGift` | Presentes/doacoes e presentes |
| `react-FaCakeCandles` | Celebracoes |

Todos esses componentes podem ser importados de `react-icons/fa6`; consulte
o [catalogo oficial](https://react-icons.github.io/react-icons/icons/fa6/).
O frontend deve registrar/resolver essas referencias no pacote central de
icones antes de renderiza-las; nao interpretar o valor como import dinamico
arbitrario nem presumir que o prefixo funcione automaticamente.
Este trabalho nao modifica o projeto web nem instala dependencias React na API.

## Seed de desenvolvimento

O seed adiciona cinco categorias de exemplo, cada uma com duas subcategorias de
ordens 1 e 2, ao usuario ja existente `usuario@formacao.dev`. Ele nunca cria
usuarios ou credenciais. Categorias com o mesmo nome vivo sao ignoradas sem
alteracao; todas as insercoes da execucao ocorrem em uma transacao.

Confirme manualmente que `DATABASE_URL` aponta para o banco de desenvolvimento
pretendido e execute:

```bash
poetry run python -m scripts.seed_categories --confirm-development
```

Sem `--confirm-development`, o script nao conecta ao banco. Se o usuario
esperado nao existir, o comando falha antes de inserir categorias.

## Testes

Os testes unitarios ficam em `tests/app/domain/category/`. Testes de constraints,
reordenacao, rollback e concorrencia usam PostgreSQL descartavel via testcontainers;
nao substituem testes unitarios e nao acessam o banco de desenvolvimento.

Para o ciclo rapido, use `make test-unit`: ele nao inicia PostgreSQL nem executa
migrations. `make test-integration` executa as provas com banco; `make test`
continua executando lint, todos os testes e cobertura. Os testes de migration
usam um banco separado no mesmo container descartavel, sem iniciar outro container.

```bash
poetry run pytest -q tests/app/domain/category -m "not integration" \
  --cov=app.domain.category.business --cov=app.domain.category.repository \
  --cov-report=term-missing --cov-fail-under=100
```

Os metadados de log do usuario sao capturados antes da transacao: rollback
expira as entidades ORM, inclusive o usuario autenticado. Ler seus atributos
depois do rollback poderia provocar carregamento async implicito e ocultar
o HTTP 409 esperado para categorias duplicadas.
