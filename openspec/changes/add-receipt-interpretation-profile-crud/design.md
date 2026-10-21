# Design

## Context

Veja `proposal.md`. A migration `77ce33061567` cria profiles, identification_rules e field_rules. O modelo atual reside em `app/models/receipt/`, possui relacionamento selectin e indices unicos parciais para Geral, instituicao por usuario e campo por perfil. Nao existe modulo de dominio para esse cadastro.

`CategoryRepository` demonstra unidade transacional com rollback, lock da raiz antes de recarregar filhos e paginacao por raiz. `CategoryUpdateSchema` ja distingue listas omitidas, null e listas completas de reconciliacao. O CRUD novo segue esses padroes sem chamar o servico de categorias. `app/main.py` registra routers explicitamente. O pipeline de Receipt ainda instancia interpretadores fixos e permanece intacto.

## Goals / Non-Goals

**Goals:** fronteira de agregado clara; contratos tipados; isolamento entre usuarios; reconciliacao atomica de duas colecoes.

**Non-Goals:** motor de execucao, interpretacao de documentos, resolucao Geral/instituicao, administracao do Geral, cache, seeds, versionamento e novas tabelas.

As escolhas de contrato detalhadas abaixo sao propostas para revisao. O escopo confirmado pelo usuario e a preparacao da proposta antes da implementacao.

## Decisions

### 1. Modulo e limites

Criar `app/domain/receipt/receipt_interpretation_profile/{__init__,enums,schema,business,repository,service,route}.py`, README no mesmo submodulo e testes em `tests/app/domain/receipt/receipt_interpretation_profile/`. Tudo relacionado ao agregado receipts permanece sob `app/domain/receipt/`; nao criar `app/domain/receipt_interpretation_profile/`. A raiz do cadastro controla as duas colecoes: nao criar endpoints ou servicos independentes para filhos.

Manter os tres modelos existentes em `app/models/receipt/`, com seus arquivos e exports atuais. Eles pertencem ao dominio receipt; a localizacao fisica em models preserva a arquitetura de persistencia do projeto. Nao mover entidades ORM para domain nem criar `app/models/receipt_interpretation_profile/`. Preservar os imports de Alembic e o registro unico no metadata.

Documentar o CRUD dentro do submodulo de receipt e referenciar sua documentacao no README existente dos modelos quando pertinente. Nao editar migrations aplicadas nem criar migration para organizacao de arquivos.

### 2. Contratos HTTP

Prefixo `/receipt-interpretation-profiles`:

| Operacao | Resposta |
| --- | --- |
| POST / | 201, agregado |
| GET / | 200, lista ou CustomLimitOffsetPage |
| GET /{profile_id} | 200, agregado |
| PUT /{profile_id} | 200, Message |
| DELETE /{profile_id} | 200, Message |

Criacao exige name e institution_code; is_active=true e listas vazias por default. Payload privado nunca aceita user_id, scope, timestamps ou IDs de criacao.

Nome usa normalizacao whitespace existente. Codigo tem trim, uppercase e regex ASCII `[A-Z0-9][A-Z0-9_-]{0,63}`; nao usar enum fixo de bancos. Codigo nao pode ser alterado pelo PUT para evitar mudar a identidade de um perfil implicitamente.

Resposta inclui scope calculado (system/private), mas nao ownership nem FKs internas dos filhos. Ordenar raizes por created_at/id e filhos por created_at/id; ordem de tentativa dos padroes fica dentro de configuration.patterns, nao na posicao da lista de filhos.

Filtros opcionais: name exato normalizado, institution_code exato normalizado e scope system/private. O padrao inclui Geral e privados; aplicar todos os filtros junto da condicao de visibilidade, sempre com parenteses no OR. Sem Geral persistido nao criar nada. Inativos continuam visiveis. Paginar somente raizes usando a infraestrutura existente.

### 3. Permissoes

Autenticacao com get_current_user em todas as rotas. Repositorio exige user_id para consultas publicas; visibilidade = owner atual OR Geral com user_id/institution_code nulos, sempre deleted_at nulo.

Mutacoes de privados exigem owner. Geral acessivel mas imutavel retorna 403; recurso de terceiro/desconhecido/excluido retorna 404. Regras nao permitem trocar de raiz nem restaurar filhos. Nenhum usuario, inclusive com papel administrativo, recebe uma excecao de escrita do Geral por esses endpoints.

Nao seedar Geral, nao aceitar Geral no POST e nao resolver permissoes atraves de dados enviados pelo cliente.

### 4. Schemas e validacao

Schemas de entrada extra=forbid; StrictBool e inteiros estritos; listas limitadas a 100 entradas por colecao. Enumerar todos os campos atuais de ReceiptData (sem criar dependencia ORM nos DTOs) e testar correspondencia com o contrato de saida.

Configuracao v1:

```json
{
  "strategy": "regex",
  "patterns": ["Valor pago:\\s*(?P<value>[\\d.]+,\\d{2})"],
  "parser": "decimal_br"
}
```

strategy aceita apenas regex; patterns tem 1..10 entradas ordenadas, nao vazias, maximo 2000 caracteres por padrao, todas compiladas com re.IGNORECASE e grupo nomeado value. Nao disponibilizar flags arbitrarias, scripts, funcoes importaveis, transformacoes livres ou fallback configuravel.

Parser text para str; decimal_br para fine, discount, interest, paid_amount, total_charges e document_amount; date_numeric_br/date_month_name_pt_br para due_date/payment_date. Conversores sao identificadores permitidos: sua execucao nao faz parte deste CRUD.

Identificacao aceita pattern compilavel com re.IGNORECASE, nao vazio, ate 2000 caracteres; weight inteiro estrito positivo; is_active bool estrito. Nao exige grupo value. Regex e preservada como enviada, sem trim que altere semantica; apenas rejeitar whitespace-only.

Compilacao valida sintaxe, nao complexidade computacional. Nao executar regex sobre documentos ou texto de exemplo neste CRUD. A entrega futura do motor precisa de limites de execucao antes de consumir essas configuracoes. Persistir configuration por model_dump(mode="json"); respostas validam o JSON existente pelo mesmo DTO. Dados legados invalidos geram erro de integridade/contrato explicitamente registrado, nao listas vazias ou fallback.

### 5. Reconciliacao e atomicidade

O PUT atualiza so os campos raiz enviados. Omitir colecao preserva seus membros; null rejeita; [] remove logicamente todos. Lista enviada representa estado final completo. Filhos retidos exigem campos completos (pattern/weight ou field_name/configuration); is_active omitido assume true como no contrato de categorias. id explicito null e proibido; filhos novos omitem id.

`business.py` gera planos puros de criacao/atualizacao/remocao para cada colecao, verificando IDs, tipos, campos finais duplicados e compatibilidade. Validar ambas antes de persistir. Nao delegar JSON arbitrario diretamente ao ORM.

Estender BaseRepository com fronteira transacional local seguindo CategoryRepository: adotar autobegin, bloquear transacoes aninhadas, commit unico, rollback inclusive em falha no commit. save/delete usam flush, sem commit intermediario. Nao usar helpers BaseService de CRUD que fragmentem o agregado.

Mutacoes bloqueiam a raiz com SELECT FOR UPDATE, depois recarregam filhos com populate_existing e revalidam. O lock deve preceder a leitura das colecoes para impedir reconciliacao com estado obsoleto. Capturar user.id/username antes do contexto para logs nao acessarem ORM expirado apos rollback.

O indice parcial field_name e imediato. Para troca ou reutilizacao de nomes, retirar temporariamente do indice os filhos vivos removidos/renomeados via deleted_at, fazer flush, aplicar nomes finais e restaurar deleted_at=None apenas nos retidos, depois flush final. Tudo dentro do mesmo lock/transacao; remocoes reais recebem exclusao definitiva logica, timestamps originais de historicos nao mudam. Nao usar nomes falsos, delete fisico ou recriar IDs retidos. Essa estrategia deve ter prova PostgreSQL.

Alternativa rejeitada: alterar a constraint para deferrable exigindo nova migration; o indice existente permite solucao transacional sem mudar schema. Nao usar commit entre as fases.

Excluir marca root e filhos vivos com mesmo timestamp, is_active=false, updated_at; historicos anteriores preservados. Sem ON DELETE CASCADE.

### 6. Erros, observabilidade e testes

422: schema, IDs de filhos, tipos, duplicates na lista final; 409: codigo ocupado, inclusive concorrencia; 403: Geral; 404: inacessivel; 401: autenticacao. Traduzir somente constraint conhecida de codigo; falhas desconhecidas permanecem erros de infraestrutura pelo handle_service_exception. Logs de sucesso somente apos commit, com IDs e operacao, sem regex ou documentos completos.

Sem cache nesta entrega: dados mutaveis e Geral compartilhado exigiriam invalidacao adicional sem ganho demonstrado. Ler filhos em lote via selectinload para evitar N+1.

Testes unitarios nos schemas, planos e service; rotas com fixtures existentes e dependency overrides; PostgreSQL descartavel seguindo o padrao de categorias para rollback, unicidade, troca de campos e locks. Verificar tabelas criadas pela cadeia Alembic existente, nao chamar banco local de desenvolvimento.

## Risks / Trade-offs

- [Perfis privados dependem do Geral ainda nao seedado] -> permitir cadastro e consulta vazia; documentar que o CRUD nao habilita interpretacao dinamica.
- [JSON legado fora do contrato] -> nao converter silenciosamente; erro explicito e eventual saneamento em mudanca separada.
- [Sem versionamento] -> nao integrar uploads antes de planejar rastreabilidade da configuracao usada.
- [Reconciliacao troca estado temporario] -> transacao, lock e testes reais asseguram ausencia de estados intermediarios visiveis e rollback.
- [Regex potencialmente custosa] -> limites de cadastro nao substituem limites do futuro executor.

## Migration Plan

Sem alteracao de tabelas planejada. A migration `77ce33061567` e pre-requisito; nao executar migrations em banco compartilhado. Manter os modelos e exports atuais. Confirmar metadata e cadeia Alembic em PostgreSQL descartavel, incluindo o indice Geral com expressao parentetizada. Se mudancas reais de schema se tornarem necessarias, propor revisao adicional sem editar historicas.
