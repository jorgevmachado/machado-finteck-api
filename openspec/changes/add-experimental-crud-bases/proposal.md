# Proposal

## Why

Os servicos repetem listagem por proprietario, busca, verificacao de ausencia, persistencia, mensagens, logs e tratamento de erros; sete repositorios repetem a mesma exclusao fisica. As bases existentes em `core` nao resolvem esse uso atual sem acoplar convencoes antigas e comportamentos divergentes, portanto precisamos avaliar bases novas e isoladas antes de qualquer migracao.

## What Changes

- Criar, na implementacao futura, `BaseRepository` e `BaseService` experimentais em `app/temp`, fora de `core`, para listar, buscar, criar, atualizar e excluir.
- Centralizar o fluxo CRUD comum com tipos explicitos, isolamento por proprietario, paginacao existente, logs de sucesso somente apos conclusao e propagacao padronizada de erros.
- Adotar `_operation` de `ReceiptService` como modelo central: contexto assincrono reutilizavel com `try/yield/except/else`, tratamento de erros unico e sucesso somente ao concluir a operacao.
- Reaproveitar os mecanismos `list_all_cached`, `find_one_cached` e `_invalidate_cache` do `BaseService` existente, compondo `CacheService` para cache-aside, `clean_cache`, TTL, serializacao por schema e invalidacao do recurso e seus pais; adaptar o escopo por owner sem copiar os comportamentos legados inadequados.
- Permitir especializacao pequena e explicita para construcao de entidades, validacao, normalizacao, consultas, exclusao logica, cache e transacoes, sem embutir regras de dominios nas bases.
- Demonstrar o reaproveitamento em subclasses de teste representando CRUD simples e normalizacao de nomes, sem alterar servicos ou repositorios ativos.
- Documentar no pacote experimental o diagnostico arquitetural, os limites da generalizacao e os exemplos de uso.

## Capabilities

### New Capabilities

- `experimental-crud`: contrato interno de bases CRUD reutilizaveis, isoladas do runtime atual, com escopo de acesso obrigatorio e pontos de extensao controlados.

### Modified Capabilities

Nenhuma. `category-management` permanece integralmente inalterada, incluindo ownership, exclusao logica, reconciliacao e atomicidade.

## Impact

- Arquivos previstos: `app/temp/__init__.py`, `app/temp/repository.py`, `app/temp/service.py`, `app/temp/README.md` e testes em `tests/app/temp/`.
- Reutilizar infraestrutura existente de paginacao, schemas, logging, erros e cache. Cache de leitura e invalidacao serao mecanismos prontos da base, habilitados explicitamente, nao apenas hooks a reimplementar em cada dominio; nao adicionar bibliotecas.
- Nao alterar `app/core`, `app/domain`, modelos, migrations, rotas, injecao de dependencias ou contratos HTTP.
- As novas bases nao serao importadas pela aplicacao ativa; nao sao substitutas drop-in das bases existentes.
- Esta mudanca entrega um experimento verificavel. Migracao de dominios, promocao para `core` e remocao de duplicacao em producao exigem outra mudanca aprovada.
