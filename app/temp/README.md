# CRUD experimental

Este pacote nao substitui `app.core`. O dominio `payer` e o primeiro piloto
integrado; os demais dominios continuam com suas implementacoes atuais.
Imports devem usar `app.temp` explicitamente.

## Diagnostico

| Grupo atual | Reaproveitamento | O que permanece especifico |
|---|---|---|
| account / credit_card | Listar, buscar, update parcial, delete, logs | Construcao e schemas |
| payer / beneficiary / institution | Mesmo fluxo CRUD e cache | Normalizacao, unicidade e resolve |
| Sete repositorios com delete fisico | Uma primitiva de exclusao | Politica de exclusao do recurso |
| category | BaseRepository + BaseService; hook `_translate_exception` | Locks, reconciliacao, exclusao logica, seed e leitura de subcategorias |
| receipt rules | Referencia de transacao unica | Leitura de perfis do sistema e regras |
| receipt / payment | Contexto `_operation` | Upload, interpretacao, confirmacao, consultas e dashboards |
| auth / extraction | Nao precisam herdar CRUD | Autenticacao e extracao |

Reutilizamos paginacao e infraestrutura existente; nao copiamos commits por
primitiva, sucesso em `finally` ou retorno vazio em caso de erro de banco.

## Repository

O modelo precisa de `id` e `user_id` UUID mapeados. Declare apenas os campos
consultaveis; nao ha descoberta implicita de campos ou caminhos relacionais.

```python
from app.temp import BaseRepository

class ItemRepository(BaseRepository[Item]):
    model = Item
    filter_fields = ("id", "name")
    order_fields = ("id", "name")
    default_order_by = "name"

repository = ItemRepository(session)
items = await repository.list_all(user_id=user.id, page_filter=FilterPage())
item = await repository.find_by(user_id=user.id, filters={"id": item_id})
```

Sem paginacao retorna lista; com offset/page e limit retorna
`CustomLimitOffsetPage`. O total e os itens usam os mesmos predicados. `id`
desempata a ordenacao. Campos desconhecidos e owner ausente geram erro explicito.
`user_id` e separado dos filtros e nunca pode ser substituido por eles.
`user_id` nunca e inferido dos criterios recebidos.

### Pipeline de consulta

Assim como no repository de receipt/payment, cada etapa tem uma responsabilidade:

| Metodo | Responsabilidade |
|---|---|
| `prepare_list` / `prepare_lookup` | Validar criterios antes de SQL ou cache; permitir normalizacao no dominio |
| `_build_query` | Criar SELECT com owner e `_visibility()` |
| `_build_filter` | Aplicar igualdade, filtros relacionais e intervalos |
| `_load_relations` | Aplicar os loaders declarados em `relations` |
| `_order_by` | Ordenar por coluna permitida, direcao e desempate por `id` |
| `_execute_list` | Executar SELECT e materializar entidades unicas |
| `_list_paginate` | Contar e limitar a mesma consulta filtrada |

`list_all` apenas compoe essas etapas. `find_by` reutiliza construcao, filtros e
loaders sem aplicar paginacao. Overrides devem chamar `super()` para preservar
owner, visibilidade e filtros padrao. Agregacoes e dashboards continuam no dominio.

### Relacoes, intervalos e direcao

Os aliases sao declarados explicitamente pelo repository, nao pelo cliente:

```python
from datetime import date

from app.shared.schemas import FilterPage
from app.temp import BaseRepository, RangeFilter, RelationFilter

class PaymentRepository(BaseRepository[Payment]):
    model = Payment
    filter_fields = ("id", "amount")
    order_fields = ("id", "payment_date", "amount")
    default_order_by = "payment_date"
    relation_filters = {
        "payer": RelationFilter("payer", "name_code"),
        "source_institution": RelationFilter("source_institution", "name_code"),
        "destination_institution": RelationFilter("destination_institution", "name_code"),
    }
    range_filters = {
        "start_date": RangeFilter("payment_date", "gte"),
        "end_date": RangeFilter("payment_date", "lte"),
    }

page_filter = FilterPage.build(
    payer="example_payer",
    start_date=date(2026, 1, 1),
    end_date=date(2026, 1, 31),
    order_by="amount",
    order="desc",
    limit=10,
    offset=0,
)
items = await PaymentRepository(session).list_all(
    user_id=user.id, page_filter=page_filter,
)
```

Este exemplo nao migra o PaymentRepository existente. `RelationFilter` usa `has`
em relacao escalar e `any` em colecao: nao multiplica linhas raiz nem totais.
Relacoes diferentes para o mesmo modelo sao independentes. Cada alias representa
uma condicao existencial independente; nao e uma linguagem de joins arbitrarios.
`RangeFilter` aceita somente `gte` e `lte`, com limites inclusivos; pode servir
para datas ou numeros. Limites invertidos naturalmente retornam zero registros.
Strings destinadas a colunas SQLAlchemy `Uuid(as_uuid=True)` sao convertidas
automaticamente para UUID, inclusive em filtros relacionais e intervalos.
UUID invalido gera erro antes de SQL ou cache. Colunas de texto nao sofrem
conversao. Demais tipos e normalizacao de nomes continuam no schema/dominio;
a base nao converte todo texto em `name_code`. Nao e necessario sobrescrever
`validate_filters` para implementar um CRUD comum.

`order` aceita apenas `asc` ou `desc` e usa `asc` quando omitido. A direcao tambem
vale para o desempate por `id`, mantendo paginas deterministicas. Utilize
`FilterPage.build(order="desc", ...)` ou um schema derivado que declare `order`;
nenhum contrato HTTP compartilhado foi alterado. Criterios, limites e direcao
participam das chaves de cache existentes.

## Transacoes

Use uma `AsyncSession(expire_on_commit=False)` exclusiva da requisicao. A fronteira
adota autobegin iniciado por leitura e passa a ser dona do commit de **toda** a
sessao. Nao compartilhe essa sessao entre tarefas concorrentes ou com outro
coordenador de transacoes. Reentrada e savepoints externos sao rejeitados.

```python
async with repository.transaction():
    first = await repository.save(Item(user_id=user.id, name="First"), user_id=user.id)
    second = await repository.save(Item(user_id=user.id, name="Second"), user_id=user.id)
```

Primitivas exigem a fronteira ativa e verificam owner, fazem flush/refresh, mas
nunca commit. Update nao e upsert. Falhas de validacao, escrita, commit ou
cancelamento tentam rollback; erro de rollback e registrado sem esconder a
causa original. Componha primitivas dentro da fronteira, nao mutacoes publicas
aninhadas. Exclusao padrao e fisica, mesmo se existir `deleted_at`.

## Service e `_operation`

O service recebe repository, alias e `LoggingParams`. A identidade vem de `User`
confiavel, nao do payload. A subclasse so precisa construir a entidade:

```python
from app.temp import BaseService

class ItemService(BaseService[Item, ItemCreate, ItemUpdate]):
    def _build_entity(self, user_id, data):
        return Item(user_id=user_id, **data)

service = ItemService(repository, alias="Item", logger_params=logging_params)
entity = await service.create(user, ItemCreate(name="Example"))
items = await service.list_all(FilterPage(), user)
entity = await service.find_by(user=user, filters={"id": entity.id})
await service.update(entity.id, ItemUpdate(description=None), user)
await service.delete(user, entity.id)
```

Para criar a partir de uma sessao, declare `repository_class = ItemRepository`
na subclasse e use a fabrica herdada:

```python
service = ItemService.from_session(
    session, alias="Item", logger_params=logging_params,
)
```

Os argumentos adicionais sao encaminhados ao construtor do service. Se a
subclasse configura alias, logging e cache no proprio `__init__`, basta
`PayerService.from_session(session)`, como no piloto. Sem `repository_class`,
a fabrica falha explicitamente. Injecao direta de repository continua disponivel;
nao e necessario sobrescrever `from_session` em cada dominio.

Create retorna ORM; update/delete retornam `Message`. Busca obrigatoria usa 404;
`required=False` retorna `None` apenas quando nao ha registro. O schema controla
validacao e null. Update usa `exclude_unset=True`; campos gerenciados nunca sao
aceitos. Os cinco fluxos acima sao exercitados por uma subclasse de teste.

`_operation(operation, user_request, target_id=None)` segue ReceiptService:
`try/yield/except/else`, handler compartilhado no erro, sucesso apenas no `else`.
Ele envolve a transacao, nao a substitui. Helpers internos evitam traducao e logs
duplicados ao compor lookup com mutacao. Alvo, requester e operacao acompanham os
logs. E reutilizavel em operacoes especializadas:

```python
async def specialized(self, user, target_id):
    async with self._operation("specialized", user.username, target_id):
        return await do_domain_work(target_id)
```

## Cache existente, opt-in

```python
class CachedItemService(BaseService[Item, ItemCreate, ItemUpdate, ItemSchema]):
    def _build_entity(self, user_id, data):
        return Item(user_id=user_id, **data)

service = CachedItemService(
    repository,
    alias="Item",
    logger_params=logging_params,
    schema_class=ItemSchema,
    cache_prefix="items",
    parents_alias=("dashboard",),
    default_ttl=120,
)
page = await service.list_all_cached(FilterPage(limit=10, offset=0), user)
item = await service.find_one_cached(user=user, filters={"id": item_id})
fresh = await service.find_one_cached(
    user=user, filters={"id": item_id}, clean_cache=True,
)
```

O quarto tipo generico descreve o schema de resposta. Cached retorna schema (lista
ou `CustomLimitOffsetPage` de schemas), tanto em hit quanto miss; CRUD comum
continua retornando ORM. O schema precisa representar a entidade e permitir
validacao por atributos. O TTL padrao e o mesmo do `CacheService`: 86400 segundos.

Reaproveitamos `CacheService` para chaves, get/set, serializacao, TTL e
`delete_with_parent_cache`. Nao existe outro backend/serializador. O namespace
`experimental:<recurso>:<owner>:` separa o experimento e os usuarios; recurso e pais
usam nomes minusculos com letras, digitos, `_` ou `-`, sem glob arbitrario.
Criterios canonicos com digest preservam caixa e evitam colisoes por delimitadores.
Todos os filtros, paginacao e ordenacao participam da identidade, mas
`clean_cache` nao. Filtros sao validados antes do acesso a cache e nao sao mutados.

`clean_cache=True` de lista limpa o recurso daquele owner antes de repopular;
refresh individual remove so a chave consultada. Lista vazia e hit valido.
Ausencia individual e erro de banco nunca sao cacheados.

Create/update/delete invalidam automaticamente recurso e pais configurados do
owner **apos commit**, inclusive aliases antigos por nome e listas. Nao e
necessario override para invalidacao comum. Sem schema configurado nao se
inicializa cache; metodos cached sem configuracao falham explicitamente.
Falhas de leitura/escrita propagadas pela infraestrutura passam por `_operation`.
Somente falha de invalidacao pos-commit e tolerada com warning contextual.
Nao ha garantia de consistencia forte banco/Redis; TTL limita dados obsoletos.

## Extensoes pequenas

Validacao/transformacao comum e feita em `_normalize(data, user, entity_id=None)`,
assincrono e sem alteracoes por padrao. `_prepare_create(data, user)` e
`_prepare_update(entity, data, user)` delegam para ele, passando o identificador
do registro atual somente no update. Sobrescreva apenas `_normalize` para regras
compartilhadas; os hooks de prepare continuam disponiveis para regras exclusivas
de uma operacao. A construcao e feita em `_build_entity(user_id, data)`. Os dados
usam `dict[str, object]`: verifique os tipos antes de consumir valores, em vez de
desabilitar a checagem com `Any`. Campos derivados confiaveis podem ser
acrescentados nesses hooks; ownership e timestamps continuam protegidos no update.

Exemplo com o helper de normalizacao existente, sem reescrever create/update:

```python
from fastapi import HTTPException
from app.shared.utils.string import to_snake_case

class NormalizedItemService(ItemService):
    async def _normalize(self, data, user, entity_id=None):
        if "name" in data:
            name = data["name"]
            if not isinstance(name, str):
                raise ValueError("Item name must be a string")
            data["name_code"] = to_snake_case(name)
            duplicate = await self.repository.find_by(
                user_id=user.id, filters={"name_code": data["name_code"]},
            )
            if duplicate is not None and (
                entity_id is None or duplicate.id != entity_id
            ):
                raise HTTPException(status_code=409, detail="Item already exists")
        return data

```

O repository desse exemplo permite filtro `name_code`, e o modelo tem esse campo.
Uma restricao de unicidade no banco continua necessaria contra corridas; traducao
de constraints especificas pertence ao dominio, nao a esta base.

Exclusao logica requer tanto persistencia quanto visibilidade explicitas:

```python
from app.models import utcnow

class LogicalItemRepository(ItemRepository):
    def _visibility(self):
        return (Item.deleted_at.is_(None),)

    async def _delete(self, entity):
        entity.deleted_at = utcnow()
```

Os checks de owner/transacao e o flush permanecem na primitiva publica `delete`.
O service continua herdado, e uma segunda exclusao resulta em 404. Nao ha
reconciliacao/cascata implicita: agregados receipt rules, leitura
compartilhada de perfis, locks, seeds, resolve, upload e dashboards nao estao
implementados aqui. O dominio category integra BaseService e BaseRepository,
mas mantem no proprio service o lock, a reconciliacao, a exclusao logica e o
seed como extensoes de dominio; o hook `_translate_exception` permite mapear
IntegrityError para 409/422 sem promoção das bases para `core`. A integracao
piloto de payer nao promove estas bases para `core` nem migra os demais
dominios. A API interna nao e uma substituta drop-in dos servicos atuais.

## Verificacao

```bash
poetry run pytest -q tests/app/temp
poetry run ruff check app/temp tests/app/temp
poetry run ruff format --check app/temp tests/app/temp
```

Os exemplos executaveis estao nos testes locais, com banco SQLite async
descartavel e `CacheService` real usando Redis falso. Nao dependem de Redis ou
PostgreSQL externos. Esses testes nao provam locks/concorrencia do PostgreSQL;
uma futura migracao de agregados exigira verificacao especifica no banco alvo.
