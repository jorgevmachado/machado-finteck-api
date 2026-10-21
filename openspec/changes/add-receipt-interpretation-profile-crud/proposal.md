# Proposal

## Why

As tabelas de perfis ja existem, mas ainda nao ha uma API para gerenciar as configuracoes privadas de identificacao e extracao. Um CRUD independente permite cadastrar essas configuracoes sem misturar administracao de regras com processamento de comprovantes.

## What Changes

- Adicionar o submodulo `app/domain/receipt/receipt_interpretation_profile/` com CRUD autenticado do perfil e regras filhas como uma unidade transacional, dentro do dominio receipt.
- Expor cinco operacoes em `/receipt-interpretation-profiles`: criar, listar, consultar, atualizar e excluir logicamente.
- Permitir leitura do Geral compartilhado e dos perfis privados do usuario; restringir escritas aos perfis privados do proprietario.
- Definir schemas tipados para identificacao e extracao, validando regex, campos, conversores e compatibilidade de tipos.
- Reconciliar listas de filhos no update, preservando listas omitidas, rejeitando identidades estrangeiras e evitando persistencia parcial.
- Manter os tres modelos de configuracao em `app/models/receipt/`, preservando exports publicos e tabelas atuais; nao criar dominio ou pacote de modelos independente para os perfis.
- Adicionar testes, documentacao e exemplos HTTP.

Fora de escopo: administracao ou seed do Geral, interpretador dinamico, resolucao de heranca, simulacao, integracao com upload, execucao de regex cadastrada sobre comprovantes, cache de regras e versionamento historico. Configuracoes salvas ainda nao alteram o processamento atual.

## Capabilities

### New Capabilities

- `receipt-interpretation-profile-management`: gerenciamento autenticado de perfis privados e suas regras, com consulta do Geral e persistencia atomica.

### Modified Capabilities

Nenhuma. `category-management` fornece prior art de reconciliacao sem alterar seu contrato.

## Impact

- Submodulo no dominio receipt e testes em `tests/app/domain/receipt/receipt_interpretation_profile/`; registro do router em `app/main.py`.
- Documentacao junto ao dominio receipt, sem mover modelos, renomear tabelas ou editar migrations historicas.
- Reutilizacao das constraints da migration `77ce33061567`, do `BaseRepository`, da paginacao, autenticacao e helpers de log/erro.
- Sem dependencias novas, alteracao dos interpretadores existentes ou execucao de migrations em bancos compartilhados.
