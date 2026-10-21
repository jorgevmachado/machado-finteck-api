# Perfis de interpretacao

O cadastro pertence a `app/domain/receipt/receipt_interpretation_profile/`.
Os modelos continuam em `app/models/receipt/`, nas tres tabelas existentes.
O contrato de configuracao foi ampliado sem alterar tabelas ou criar migration.

Cada perfil privado pertence ao usuario autenticado. Geral e compartilhado
(`user_id` e `institution_code` nulos), somente consultavel nesta API.
Nenhum endpoint cria ou administra Geral; se ele ainda nao existe, nao e
criado automaticamente. Um perfil de instituicao pode existir sem regras.

## Dados iniciais de instituicoes

`default_profiles.json` e uma lista de payloads de criacao para Nubank, Itau e
Caixa. Preserva os 10 patterns e pesos de
`app/domain/receipt/interpretation/institutions/rules/`, na mesma ordem.
Cada item pode ser enviado individualmente ao POST abaixo; nao enviar a lista
inteira, pois nao existe endpoint batch de perfis.
O usuario autenticado sera o dono dos perfis. Repetir a criacao de um codigo
existente para esse usuario retorna 409, nao atualiza o cadastro.

Os campos especificos tambem estao mapeados: Nubank tem datas com mes em
portugues e origem constante; Itau tem autenticacao e origem; Caixa tem origem.
`general_profile.json` define os 18 campos padrao do BaseInterpreter, incluindo
os 12 patterns de beneficiario, normalizacao do codigo de barras e fallbacks
de pagador efetivo e valor do documento. Campos sem extrator usam `not_found`.
Capturas foram convertidas para o grupo nomeado `value`, preservando a ordem.
Os nomes constantes de origem reproduzem o retorno do interpreter quando a
instituicao selecionada e a correspondente; os helpers alternativos de origem
nao sao executados nesse caminho.

### Executar seed em desenvolvimento

Confira DATABASE_URL e informe o UUID de um usuario existente:

```bash
poetry run python -m app.domain.receipt.receipt_interpretation_profile.seed \
  --user-id UUID_DO_USUARIO --confirm-development
```

O comando valida ambos os JSONs, cria o Geral compartilhado e os tres perfis
privados para esse usuario em uma unica transacao, serializada com advisory
lock. Nao cria usuarios, nao roda migrations e nao e executado automaticamente.
Registros existentes sao preservados e contados como skipped. Para preencher
perfis antigos que tinham apenas identificacao, execute com `--replace-existing`:
isso substitui as regras vivas pelos defaults, inclusive no Geral compartilhado,
afetando outros usuarios que herdam dele. Use apenas quando essa substituicao
for desejada. IDs de campos/patterns correspondentes sao preservados; filhos
removidos sao excluidos logicamente. Falhas revertem toda a importacao.

## Contratos

| Metodo | Caminho | Resposta |
| --- | --- | --- |
| POST | /receipt-interpretation-profiles | 201, agregado |
| GET | /receipt-interpretation-profiles | 200, lista ou pagina |
| GET | /receipt-interpretation-profiles/{profile_id} | 200, agregado |
| PUT | /receipt-interpretation-profiles/{profile_id} | 200, message |
| DELETE | /receipt-interpretation-profiles/{profile_id} | 200, message |

Todas as rotas exigem JWT. Credenciais invalidas retornam 401; Geral nao pode
ser alterado/excluido (403); perfil desconhecido, excluido ou de terceiro
retorna 404; codigo ocupado retorna 409; payload ou identidade de filho
invalido retorna 422. Os codigos sao normalizados para uppercase e aceitam
`[A-Z0-9][A-Z0-9_-]{0,63}`. O codigo e imutavel apos criacao.

GET inclui Geral e privados, inclusive inativos, excluindo registros removidos
logicamente. Filtros `name`, `institution_code` e `scope=system|private` sao
combinados. `page` ou `offset` ativa a paginacao existente; `limit` sozinho
nao altera o formato de lista. A contagem e por perfil, nao por regra.

## Configuracao v1

```json
{
  "name": "Meu Nubank",
  "institution_code": "NUBANK",
  "identification_rules": [
    {"pattern": "\\bNU\\s+PAGAMENTOS\\b", "weight": 100}
  ],
  "field_rules": [
    {
      "field_name": "payment_date",
      "configuration": {
        "strategy": "regex",
        "patterns": ["(?P<value>\\d{2}\\s+[A-Z]{3}\\s+\\d{4})"],
        "parser": "date_month_name_pt_br"
      }
    }
  ]
}
```

Crie com `POST /receipt-interpretation-profiles` e esse JSON, usando
`Authorization: Bearer <token>` e `Content-Type: application/json`.
Use o `id` devolvido no caminho dos proximos exemplos.

Cada colecao aceita ate 100 filhos. Campos seguem ReceiptData; dinheiro usa
`decimal_br`, datas `date_numeric_br` ou `date_month_name_pt_br`, texto `text`.
Cada configuracao regex aceita 1..20 patterns ordenados, ate 2000 caracteres cada,
compilaveis com IGNORECASE e grupo nomeado `value`. Regras de identificacao
nao exigem grupo e usam peso inteiro estrito positivo. Campos extras,
ownership, timestamps e IDs de criacao sao proibidos.

Configuracoes regex antigas continuam validas. `normalization` assume `strip`;
`remove_whitespace` e exclusivo de barcode; `ocr_day` corrige N/I/L para 1
no dia de datas com mes por nome. `fallback_field` permite somente
effective_payer -> payer e document_amount -> paid_amount, quando o destino nao
esta FOUND e a origem esta FOUND. Nao permite ciclos ou codigo arbitrario.
`strategy=constant` com `value` textual e exclusivo de source_institution;
`strategy=not_found` representa ausencia intencional de extrator em qualquer campo.
JSON legado invalido produz erro explicito, nao fallback silencioso.

## Resolucao e processamento dinamico

ReceiptService.upload (e batch, que chama upload) consulta os perfis atuais do
usuario mais Geral antes da interpretacao. Nao usa cache nem as classes fixas
para escolher regras. Os interpreters antigos continuam disponiveis para
compatibilidade e comparacao, mas nao sao o caminho de upload.

Somente perfis/regras ativos e nao excluidos participam. Pesos das regex
identificadoras encontradas sao somados; o maior score unico escolhe o perfil.
Sem correspondencia ou em empate, usa Geral. Diferentemente do servico legado,
o caminho dinamico nao desempata com heuristicas fixas de banco/origem.
Mencoes a mais de um banco ainda podem afetar o score; pesos nao foram
recalibrados sem comprovantes representativos.

Um override ausente ou inativo herda a regra do Geral. Um override ativo que
nao encontra valor NAO tenta a regra Geral em seguida. Patterns sao tentados
na ordem: o primeiro match e convertido, e conversao invalida resulta em
AMBIGUOUS, sem tentar os proximos. O InterpretationValidator existente continua
decidindo campos obrigatorios; status received/failed segue seus erros.
Geral ausente/inativo bloqueia upload com 503: execute o seed antes de usar.

Execucao regex ocorre fora do event loop, em processo Linux descartavel:
5 segundos de parede, 4 segundos de CPU, 512 MiB de espaco de enderecamento,
ate 4 workers simultaneos por processo da API (espera maxima de 5 segundos).
Limites de entrada: 1 milhao de caracteres extraidos, 100 perfis visiveis e
4 MB de configuracao serializada. Limites excedidos, timeout, erro de processo
ou configuracao invalida geram falha explicita; nao persistem sucesso nem
recorrem silenciosamente ao interpreter fixo. Processos sao encerrados ao final.

O resultado guarda snapshot versionado dos perfis consultados, IDs e perfil
selecionado em `receipts.data["_interpretation"]`; o retorno publico ReceiptData
continua contendo somente os campos extraidos. Isso permite reproduzir a
configuracao usada mesmo apos mudancas no cadastro, sem nova coluna no banco.
Nao existe historico administrativo de versoes dos perfis nesta entrega.

## Atualizacao e transacoes

PUT preserva campos/listas omitidos. `null` nao e aceito. Uma lista enviada
representa todos os filhos desejados: com `id` atualiza, sem `id` cria, filhos
ausentes sao excluidos logicamente. `[]` remove todos. Filhos retidos exigem
seus campos completos; `is_active` omitido assume true. Nao e permitido mover
filhos entre perfis/colecoes nem restaurar filhos excluidos. Campos finais
devem ser unicos, inclusive em regras inativas.

O repository possui uma fronteira de commit/rollback unica. Mutacoes bloqueiam
a raiz antes de recarregar os filhos. Trocas de field_name liberam o indice
parcial temporariamente dentro da mesma transacao, sem nomes ficticios ou
exclusao fisica. Falhas em qualquer fase ou no commit desfazem o agregado.
DELETE desativa e exclui logicamente raiz e filhos vivos; timestamps de filhos
ja excluidos sao preservados. Nao ha cache nesta entrega.

### Exemplos de PUT

`PUT /receipt-interpretation-profiles/{profile_id}` preservando ambas as listas:

```json
{"name": "Nubank pessoal", "is_active": false}
```

Removendo somente as regras de identificacao, preservando as de campos:

```json
{"identification_rules": []}
```

Lista mista: substitua o UUID abaixo pelo `id` de uma regra de campo **viva
desse perfil** devolvida pelo GET. Ela sera mantida/atualizada; a segunda sera
criada e todas as regras de campo nao listadas serao removidas logicamente.
As regras de identificacao sao preservadas.

```json
{
  "field_rules": [
    {
      "id": "00000000-0000-0000-0000-000000000001",
      "field_name": "payment_date",
      "configuration": {
        "strategy": "regex",
        "patterns": ["(?P<value>\\d{2}/\\d{2}/\\d{4})"],
        "parser": "date_numeric_br"
      }
    },
    {
      "field_name": "paid_amount",
      "configuration": {
        "strategy": "regex",
        "patterns": ["Valor:\\s*(?P<value>[\\d.]+,\\d{2})"],
        "parser": "decimal_br"
      }
    }
  ]
}
```

Removendo todos os filhos vivos, sem excluir o perfil:

```json
{"field_rules": [], "identification_rules": []}
```

### Consulta e exclusao

`GET /receipt-interpretation-profiles?scope=system` retorna Geral caso exista,
ou `[]`. `GET /receipt-interpretation-profiles/{id_do_geral}` consulta esse
agregado; PUT e DELETE retornam 403. Nenhuma dessas chamadas cria Geral.

`GET /receipt-interpretation-profiles?institution_code=NUBANK` consulta o perfil
privado; `?offset=0&limit=12` devolve `{items, meta}`. Raizes e filhos sao
ordenados por `created_at, id`.

`DELETE /receipt-interpretation-profiles/{profile_id}` devolve
`{"message":"Delete receipt profile <id> successfully"}`. Chamadas posteriores
ao perfil removido retornam 404, mas seu codigo pode ser reutilizado.

## Validacao local

Testes unitarios usam pytest e mocks. Testes de constraints, migration,
concorrencia e rollback usam PostgreSQL descartavel via testcontainers,
exigem Docker e nao acessam o banco de desenvolvimento:

```bash
poetry run pytest -q tests/app/domain/receipt/receipt_interpretation_profile
```
