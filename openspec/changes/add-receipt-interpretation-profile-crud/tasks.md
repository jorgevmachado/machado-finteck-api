# Tasks

Grupos 1 e 2 podem ser preparados independentemente. Grupo 3 depende deles; grupo 4 depende da persistencia e contratos; grupo 5 verifica a entrega integrada. Nao implementar motor ou integracao com upload.

## 1. Organizacao dentro do dominio receipt

- [x] 1.1 Criar o submodulo `app/domain/receipt/receipt_interpretation_profile/` e testes espelhados em `tests/app/domain/receipt/receipt_interpretation_profile/`, mantendo os tres modelos em `app/models/receipt/`; verificar ausencia de dominios ou pacotes de modelos independentes para perfis.
- [x] 1.2 Preservar imports, exports publicos e registro dos modelos no metadata Alembic; verificar configuracao dos mappers sem registro duplicado, nomes de tabelas intactos e nenhuma migration historica modificada.

## 2. Schemas e regras puras

- [x] 2.1 Criar schemas de criacao, reconciliacao, resposta e filtros, com normalizacao de nome/codigo, campos gerenciados proibidos, scope calculado e omissao/null conforme spec; verificar testes de defaults, IDs nulos, codigo imutavel e limites de colecoes.
- [x] 2.2 Definir enums de campos/conversores e configuracao regex tipada, validando syntax, grupo value, 1..10 padroes, limite 2000 e compatibilidade do parser; verificar testes focados de todos os tipos e correspondencia entre campos aceitos e ReceiptData.
- [x] 2.3 Implementar validacao de identificacao e planos puros de reconciliacao para ambas as colecoes, rejeitando IDs repetidos/estrangeiros/excluidos e campos finais duplicados; verificar testes de listas omitidas, vazias, mistas e trocas validas.
- [x] 2.4 Criar README em `app/domain/receipt/receipt_interpretation_profile/` com configuracao JSON v1, limites, diferenca entre cadastrar e executar regex e semantica do PUT; verificar exemplos com os schemas, sem executar padroes contra documentos.

## 3. Persistencia transacional do agregado

- [x] 3.1 Implementar repository baseado em BaseRepository com visibilidade owner/Geral, filtros, contagem por raiz e carregamento em lote de filhos vivos; verificar testes PostgreSQL de isolamento, Geral ausente, inativos visiveis, ordenacao e paginacao sem duplicatas.
- [x] 3.2 Implementar fronteira de transacao seguindo CategoryRepository, lock da raiz antes dos filhos e save sem commit intermediario; verificar testes de rollback apos falha de filho/commit e reutilizacao de sessao.
- [x] 3.3 Implementar reconciliacao atomica, incluindo liberacao temporaria do indice parcial para troca/reuso de field_name e exclusao logica com timestamps preservados; verificar em PostgreSQL troca, substituicao, empty list, falha entre fases e ausencia de restauração de filhos historicos.
- [x] 3.4 Adicionar provas PostgreSQL concorrentes para codigo duplicado e mutacoes sobre a mesma raiz; verificar 409 para colisao de codigo e revalidacao apos lock para filho removido.
- [x] 3.5 Documentar transacoes, constraints e requisitos do ambiente descartavel no README; verificar os testes com cadeia Alembic existente e indice do Geral sem usar banco de desenvolvimento.

## 4. Service e API

- [x] 4.1 Implementar service para criar/listar/consultar/atualizar/excluir, ownership da autenticacao, Geral somente leitura e traducao especifica de conflitos; verificar testes de 403/404/409/422 e falhas de infraestrutura propagadas pelos helpers.
- [x] 4.2 Integrar logs de sucesso apos commit e tratamento padrao de excecoes, capturando metadados do usuario antes de rollback; verificar testes de falha sem sucesso falso e sem acessar atributos ORM expirados ou logar configuracoes completas.
- [x] 4.3 Implementar e registrar exatamente as cinco rotas autenticadas com response_model e paginacao existentes; verificar testes HTTP de contratos, 401, UUID invalido, rejeicao de user_id, Geral imutavel e ausencia de endpoints de filhos.
- [x] 4.4 Completar README e exemplos HTTP de perfil Nubank, duas colecoes, PUT omitido/vazio/misto, consulta do Geral e exclusao; verificar payloads pelos testes de rota e documentar que perfis nao alteram upload nesta entrega.

## 5. Verificacao integrada

- [x] 5.1 Executar testes focados do novo submodulo e regressao dos imports/interpretacao de receipt, verificando que o CRUD nao mudou o pipeline fixo; executar lint e format check dos arquivos tocados e corrigir somente problemas ligados a entrega.
- [x] 5.2 Executar `make test` conforme checklist do projeto e registrar bloqueios reais se existirem; verificar ausencia de migrations historicas alteradas, dependencias novas, seeds, administracao do Geral e motor de interpretacao no diff final.

## Evidencias de verificacao

- `make test`: lint aprovado, 868 testes aprovados e relatorio de cobertura gerado.
- PostgreSQL descartavel migrado ate head: unicidade do Geral, conflito concorrente
  de codigo, lock/revalidacao, trocas de campos e rollback verificados.
- Ruff format check e diff check dos arquivos desta entrega aprovados.
- Nenhuma migration ou dependencia foi alterada para implementar o CRUD.
  Alteracoes preexistentes no worktree foram preservadas; o diff check global
  aponta whitespace preexistente em
  `tests/app/domain/receipt/interpretation/interpreters/test_base.py:9`.
- Sem seed, endpoints administrativos ou integracao do cadastro ao motor/upload.

## Workflow follow-up

- Revisar a implementacao e arquivar somente apos conclusao das tarefas.
- Planejar separadamente seed do Geral, versionamento, resolucao de heranca e execucao segura antes de integrar regras cadastradas ao upload.
