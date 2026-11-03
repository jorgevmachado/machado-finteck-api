# Design

## Context

Ver `proposal.md` para a motivacao. O levantamento das camadas identificou estes grupos:

| Grupo observado | Evidencia no codigo | Aproveitamento / limite |
|---|---|---|
| CRUD simples | `app/domain/account/service.py`, `app/domain/credit_card/service.py` | Listagem com `with_updates(user_id=...)`, busca com 404, update parcial, delete, logs e erros repetidos; construcao e schemas diferem. |
| CRUD com nomes normalizados | `app/domain/{payer,beneficiary,institution}/service.py` | Mesmo fluxo dos simples, acrescido de `name_code`, verificacao de duplicidade, invalidacao e `resolve`. Normalizacao/unicidade nao pertencem a uma base universal. |
| Exclusao fisica identica | `repository.py` de account, credit_card, payer, beneficiary, institution, receipt e receipt/payment | Todos executam `session.delete(entity)` e `commit`; a primitiva pode ser unica, mas o commit precisa pertencer a uma fronteira explicita. |
| Agregados | `app/domain/category/{service,repository}.py`, `app/domain/receipt/rules/{service,repository}.py` | Transaction context, flush, locks, reconciliacao e exclusao logica. Perfis ainda permitem leitura de registros do sistema com `user_id` nulo. Nao podem ser tratados como CRUD simples. |
| Orquestracao especializada | `app/domain/receipt/service.py`, `app/domain/receipt/payment/{service,repository}.py` | `_operation` ja centraliza erros/logs; upload, interpretacao, confirmacao e dashboards devem permanecer especificos. Payment possui listagem especializada. |
| Autenticacao e extracao | `app/domain/auth/service.py`, `app/domain/receipt/extraction/service.py` | Login, registro e extracao nao sao CRUD generico; nao precisam herdar as bases. |
| Bases atuais | `app/core/service/base.py`, `app/core/repository/base.py` | Reaproveitar cache-aside de `list_all_cached`/`find_one_cached`, configuracao por schema/prefixo e invalidacao com pais. Nao transportar inferencia UUID/nome, filtros legados, cache obrigatorio, sucesso em `finally`, mutacao de filtros ou fallback vazio. Repository ja fornece filtros/relacoes/paginacao, mas `save` e `update` fazem commit proprio. |

O contrato publicado em `openspec/specs/category-management/spec.md` exige isolamento, exclusao logica e atomicidade. Nao ha conflito se categorias continuarem inalteradas; substituir seu repositorio pelo fluxo fisico generico violaria esse contrato.

Os testes em `tests/app/domain/account/test_account_service.py` e `tests/app/domain/payer/test_payer_service.py` ja verificam ownership e falhas explicitas. `tests/app/domain/category/test_category_repository.py` cobre autobegin, rollback, flush sem commit e rejeicao de transacoes aninhadas. Reutilizar essas expectativas como referencias, sem modificar os testes atuais.

## Goals / Non-Goals

**Goals:**

- Reduzir codigo de novos CRUDs por heranca simples e poucos pontos de extensao, com contratos tipados e auditaveis.
- Separar mecanica SQL no repository de orquestracao, resposta e regras no service.
- Demonstrar o CRUD comum e uma especializacao realista em testes, antes de discutir adocao.
- Combinar a tatica `_operation` do agregado receipt com mecanismos de cache ja existentes, evitando nova infraestrutura ou repeticao de invalidacao por dominio.

**Non-Goals:**

- Nao criar um framework de plugins, gerador de classes, roteador CRUD automatico ou motor arbitrario de consultas.
- Nao prometer assinatura compativel com todos os servicos existentes.
- Nao corrigir divergencias ou bugs legados durante esta mudanca.
- Nao implementar reconciliacao de agregados, locks especificos, seeds, `resolve`, upload ou dashboards.
- Nao migrar `AccountService`, que continua standalone conforme a convencao atual do projeto.

## Decisions

### 1. Pacote independente e pequeno

Criar `app/temp/repository.py`, `app/temp/service.py`, exports em `__init__.py` e `README.md`, conforme o caminho atualizado em `proposal.md`. Os nomes exportados serao `BaseRepository` e `BaseService`; imports qualificados distinguirao essas classes das existentes em `core`.

Nao herdar integralmente das bases antigas: seus commits e comportamentos de erro impedem um contrato novo consistente. Reaproveitar os fluxos uteis do BaseService por adaptacao no experimento e compor diretamente `app/core/cache/service.py` (`CacheService`), alem dos helpers de `app/core/pagination`, `app/core/logging`, `app/core/exceptions` e schemas compartilhados. Dependencia de `temp` para essa infraestrutura e permitida; dependencia inversa nao. Nao alterar `core` para extrair helpers nesta etapa.

Alternativa rejeitada: modificar diretamente as bases em `core`, pois isso mistura experimento e runtime e contraria o isolamento solicitado.

### 2. Contrato minimo do repositorio

O repositorio recebe `AsyncSession` explicitamente, sem `Depends` ou `Query`. Define `model`, campos permitidos para filtros/ordenacao e opcoes de carregamento. Tipar consultas, entidades e resultados com generics compativeis com Python 3.13; nao adicionar dependencia de tipagem ou casts amplos.

API prevista:

- `list_all(*, user_id: UUID, page_filter: FilterPage | None)` retorna `list[ModelT] | CustomLimitOffsetPage[ModelT]`.
- `find_by(*, user_id: UUID, filters: Mapping[str, object])` retorna `ModelT | None`; exige pelo menos um criterio de recurso, alem do owner.
- `save`, `update` e `delete` recebem entidade e `user_id` explicitos, verificam o proprietario e exigem o contexto transacional experimental ativo; nao fazem commit.
- `transaction()` concentra inicio/adocao, commit e rollback; consultas podem ser compostas nessa fronteira.

Construir uma consulta raiz com predicado obrigatorio de `user_id` separado dos filtros do cliente. Um hook de consulta/visibilidade adiciona condicoes e loaders especializados sem remover esse predicado no fluxo padrao. Validar campos desconhecidos em vez de ignora-los. Metadados de paginacao/cache nao viram filtros SQL. Reutilizar `is_paginate` e `get_limit_offset_params`; aplicar os mesmos predicados a itens e total. Preferir filtros relacionais com `has`/`any` quando uma extensao precisar deles, evitando multiplicar linhas raiz.

O padrao suporta filtros escalares e ordenacao por colunas explicitamente permitidas, com `id` como desempate. Nao reproduzir automaticamente a linguagem legada de caminhos relacionais. Consultas especializadas entram por override pequeno. Modelos sem `user_id` exigem outro contrato explicito, fora do fluxo padrao desta versao.

Alternativas rejeitadas: `**kwargs` misturando filtros, identidade e logging; filtros implicitos descobertos pelo nome; dependencia das rotas nas bases.

### 3. Service como template de operacao, nao catalogo de regras

O service recebe repositorio tipado, alias e `LoggingParams`. Operacoes publicas recebem o usuario confiavel; extraem `user.id` e `user.username`, sem aceitar identidade fornecida no payload como autoridade.

Fornecer `list_all`, `find_by` com ausencia opcional explicita, `create`, `update` e `delete`. Criacao retorna `ModelT`; update/delete retornam `Message`, seguindo os CRUDs atuais. Busca obrigatoria usa 404; busca opcional retorna `None` somente quando a consulta terminou sem erro. Nao inferir se um texto e ID ou nome: o chamador fornece criterios explicitos.

Extensoes protegidas pequenas:

- Construcao de entidade a partir do schema de criacao e owner, obrigatoriamente implementada pelo consumidor; dataclasses ORM possuem construtores diferentes.
- Validacao/transformacao antes de criar ou atualizar, com acesso ao registro atual quando necessario.
- Aplicacao padrao de `model_dump(exclude_unset=True)` no update, preservando diferenca entre omissao e null validado pelo schema.
- Substituicao explicita das primitivas de persistencia/consulta para necessidades especializadas.
- Cache de leitura e invalidacao padrao apos commit, habilitados por configuracao; extensao somente para dependencias adicionais especificas.

Rejeitar campos gerenciados (`id`, `user_id`, timestamps) que cheguem aos dados de escrita e confirmar o owner da entidade construida antes de persistir. Campos derivados somente entram por transformacao confiavel do consumidor. O exemplo normalizado calcula `name_code`, verifica duplicidade no mesmo owner e permite manter o proprio nome, sem embutir `name_code` na base.

Nao exigir override de um metodo publico inteiro para mudar validacao ou construcao. Nao criar um hook para cada linha: extrair somente variacoes demonstradas pelos testes.

Alternativa rejeitada: construcao universal por `model(**payload.model_dump())`, que mistura input publico, campos derivados e campos gerenciados.

### 4. Uma fronteira de transacao por mutacao

`create`, `update` e `delete` abrem `repository.transaction()` antes da validacao e busca mutavel; o contexto faz commit uma unica vez. Primitivas fazem `add`/`merge`/`delete`, `flush` e refresh necessario antes do commit. Validacao e escritas de extensoes ficam na mesma fronteira.

Adotar a transacao iniciada por leitura automatica quando a sessao e exclusiva da requisicao, seguindo o comportamento observado nos repositorios de agregados. Rejeitar reentrada experimental e savepoints externos usando controle compartilhado em `session.info`; nao oferecer composicao aninhada de mutacoes publicas. Extensoes que precisam de multiplas escritas usam primitivas dentro da fronteira externa.

Usar sessao com `expire_on_commit=False`, como `app/core/database/database.py`. O contexto e dono do commit de toda a sessao; nao compartilhar essa sessao entre operacoes concorrentes nem adotar transacoes arbitrarias de outro coordenador. Essa precondicao precisa constar no README.

Falhas inclusive de commit/cancelamento tentam rollback e preservam a causa original; falha no rollback recebe log proprio. A traducao HTTP fica exclusivamente na camada service, usando `handle_service_exception`. Nao retornar sucesso nem executar invalidacao se commit falhar.

Alternativas rejeitadas: commit em cada primitiva e um modo booleano `commit=True/False` por chamada, que permitem persistencia parcial por acidente.

### 5. Exclusao fisica padrao, politica especializada explicita

O comportamento padrao corresponde aos sete repositorios simples: remover a linha. A presenca de `deleted_at` nao ativa soft delete automaticamente.

Demonstrar em testes uma extensao que substitui a primitiva de delete por marcacao logica e acrescenta visibilidade de registros vivos na consulta, usando a mesma orquestracao do service. Nao implementar cascata de categorias ou perfis nessa extensao demonstrativa. Leitura compartilhada de perfis do sistema tampouco e o padrao owner-only.

Alternativa rejeitada: transformar todos os deletes em logicos, uma mudanca observavel injustificada.

### 6. `_operation` de receipt como eixo da orquestracao

Adotar explicitamente `ReceiptService._operation` (`app/domain/receipt/service.py`) como referencia principal: `@asynccontextmanager`, `try: yield`, `except Exception: handle_service_exception(..., raise_exception=True)` e `else: log_service_success(...)`. Generalizar somente alias, logger, nome de operacao, requester e alvo opcional; nao copiar regras de recibos.

Cada entrada publica de CRUD ou cache abre esse contexto uma vez. Usar helpers internos sem envelope proprio quando uma leitura cached precisa consultar o banco ou uma mutacao precisa buscar a entidade; evitar chamadas publicas aninhadas com traducao/log duplicado. O contexto tambem fica disponivel para operacoes especializadas em subclasses, como ocorre hoje em receipt.

Nas mutacoes, `_operation` envolve `repository.transaction()` e invalidacao pos-commit: primeiro validar/persistir, depois sair da transacao, invalidar e concluir o contexto. Assim falha de commit nunca gera sucesso. `_operation` nao e uma transacao e nao substitui o coordenador do repository. Logs internos da infraestrutura de cache podem existir, mas nao devem ser confundidos com sucesso da operacao publica.

Alternativas rejeitadas: repetir try/except em cada metodo, usar decorators com estado implicito ou registrar sucesso em `finally`.

### 7. Reaproveitamento dos mecanismos de cache do BaseService

O novo service oferece `list_all_cached`, `find_one_cached` e `_invalidate_cache`, adaptando o fluxo do BaseService existente: construir chave, consultar cache, buscar no banco em miss e armazenar resultado. Reutilizar `CacheService.build_key_list`, `build_key_one`, `get_list`, `get_one`, `set_list`, `set_one` e `delete_with_parent_cache`, incluindo TTL e schema de resposta. Nao criar cliente Redis, serializador ou backend alternativo.

Cache permanece opt-in por configuracao de schema de resposta, prefixo e pais; TTL usa o padrao de `CacheService` ou valor explicitamente configurado. Sem configuracao, CRUD comum nao instancia cache; chamar um metodo cached sem configuracao gera erro explicito, nao um fallback silencioso.

As leituras comuns continuam retornando ORM; metodos cached retornam `SchemaT`, lista de `SchemaT` ou `CustomLimitOffsetPage[SchemaT]` tanto em hit quanto em miss. Validar/converter resultados antes de escrever usando o schema configurado, com `from_attributes` quando necessario, preservando a forma customizada da pagina. Tratar `cached is not None` como hit, incluindo lista vazia; nao cachear ausencia individual ou erros.

Adaptacoes necessarias ao reaproveitamento:

- Construir prefixo delimitado por recurso e owner confiavel, por exemplo `experimental:<resource>:<owner>:`; nunca usar escopo recebido do cliente. Aplicar o mesmo namespace aos pais configurados.
- Incluir todos os criterios efetivos em chaves: filtros, ordenacao, paginacao e identidade da consulta individual. Usar representacao canonica e digest da biblioteca padrao para criterios individuais, pois `CacheManager.build_key` normaliza strings para minusculas e valores sensiveis a caixa nao podem colidir. Os filtros devem usar valores JSON normalizados e ordem estavel.
- Copiar filtros antes de remover `clean_cache` da identidade; validar criterios antes de consultar cache. `clean_cache` de lista limpa o recurso daquele owner; refresh individual remove a chave exata, depois ambos buscam e repopulam.
- Invalidar o namespace do recurso e seus pais apos commit em create/update/delete. Limpar todo o recurso do owner cobre listas e aliases antigos de nomes sem manter indice auxiliar. Deixar um ponto de extensao apenas para dependencias adicionais.
- Repassar erros de leitura/escrita de cache que escapem da infraestrutura a `_operation`, sem mascara-los como lista vazia. Um miss legitimo consulta o banco; uma falha de banco nunca vira miss ou resultado cacheavel.
- Restringir tolerancia a falha a invalidacao pos-commit: registrar warning com owner/operacao/alvo sem transformar uma mutacao ja confirmada em erro de persistencia. Nao prometer consistencia forte entre banco e Redis.

Alternativas rejeitadas: entregar apenas hook de invalidacao para cada dominio reimplementar cache, herdar integralmente o BaseService antigo, cache obrigatorio, chaves sem owner e invalidacao antes do commit.

### 8. Evidencia de simplificacao sem migracao

Adicionar testes em `tests/app/temp/test_repository.py` e `test_service.py`, com fixtures locais em `conftest.py` quando necessario. Usar subclasses de teste de recurso simples e recurso com nome normalizado; nenhum novo dominio, rota ou modelo de producao.

Os exemplos precisam executar CRUD herdado, nao apenas verificar constantes ou contar linhas. Repository deve ter testes com SQLite async descartavel e dados de dois owners para validar SQL real, totais, rollback e exclusao. Service usa mocks para falhas/ordem de chamadas e testes compostos com repositorio real para provar reaproveitamento e persistencia. Uma extensao de exclusao logica e uma mutacao composta demonstram os limites.

O README deve apresentar matriz arquitetural equivalente ao diagnostico acima, API publica, precondicoes transacionais e exemplos curtos. Nao criar adaptadores de producao apenas para demonstracao.

Adicionar testes de cache com a infraestrutura existente e Redis falso local quando necessario, incluindo serializacao real de ORM para schema, lista/pagina em hit e miss, TTL, refresh, owner, filtros sensiveis a caixa e invalidacao de pais. Testar `_operation` em uma acao especializada de subclasse, sem exigir CRUD nem alteracao de receipt.

## Risks / Trade-offs

- Duas bases com os mesmos nomes podem confundir consumidores -> imports qualificados e aviso experimental; nenhuma integracao automatica.
- Generalizacao excessiva pode esconder regras -> normalizacao, unicidade, reconciliacao e visibilidade especial ficam em extensoes ou implementacoes atuais.
- A sessao adotada pode conter outras escritas -> exigir exclusividade, documentar posse da transacao e rejeitar fronteiras experimentais aninhadas.
- Cache pode permanecer obsoleto apos falha de invalidacao ou corrida com leitura concorrente -> warning explicito, TTL e invalidacao compartilhada pos-commit; nao prometer consistencia forte.
- A infraestrutura atual possui convencoes de chaves e serializacao legadas -> namespace experimental delimitado, criterios canonicos e testes de ida/volta; nao corrigir `core` fora desta mudanca.
- SQLite nao prova locks ou concorrencia PostgreSQL -> nao implementar agregados/locks nesta versao; futura migracao exige testes especificos no banco alvo.
- A duplicacao ativa nao diminui imediatamente -> este e o experimento solicitado, nao a migracao; demonstrar ganho em subclasses executaveis antes de adotar.
- Rejeicao de filtros desconhecidos difere da base antiga -> contrato experimental deliberado, sem mudar os chamadores atuais.

## Migration Plan

1. Implementar e validar somente o pacote experimental, seus testes e documentacao.
2. Manter startup, rotas e dependencias atuais sem imports de `app.temp`.
3. Revisar os exemplos e decidir adocao em outra mudanca, com comparacao de contratos por dominio.
4. Reverter o experimento removendo apenas os arquivos novos caso seja rejeitado; nao existe migracao de dados ou rollback de banco.
