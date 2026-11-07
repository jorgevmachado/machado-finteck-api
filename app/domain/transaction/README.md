# Transaction: seed e extrato

## Extrato unificado

`GET /transactions/statement` retorna avulsas, agendamentos gravados e
ocorrencias projetadas das series em uma lista unica. Exige autenticacao JWT;
nao exige admin e consulta somente registros do usuario autenticado.
Nao altera as rotas CRUD existentes.

```bash
curl -G http://localhost:8000/transactions/statement \
  -H "Authorization: Bearer $TOKEN" \
  --data-urlencode "start_date=2026-11-01" \
  --data-urlencode "end_date=2026-11-30" \
  --data-urlencode "page=1" \
  --data-urlencode "limit=12"
```

`start_date` e `end_date` sao obrigatorios e inclusivos. O periodo maximo e de
366 dias, sem datas invertidas. Filtros opcionais: `account_id`, `credit_card_id`,
`subcategory_id`, `direction`, `status`, `search` e `only_credit_card`.
Parametros invalidos ou desconhecidos retornam `422`.

`search` faz busca parcial no nome sem diferenciar maiusculas.
`only_credit_card=true` inclui somente entradas com cartao, `false` somente
entradas sem cartao, e sua omissao inclui ambas. `credit_card_id` tem
precedencia sobre `only_credit_card`.

```json
{
  "items": [
    {
      "source": "PROJECTED",
      "id": null,
      "name": "Assinatura",
      "note": null,
      "value": "100.00",
      "direction": "OUT",
      "status": "PENDING",
      "expected_on": "2026-11-10",
      "settled_on": null,
      "account_id": "00000000-0000-0000-0000-000000000001",
      "credit_card_id": null,
      "subcategory_id": null,
      "transaction_series_id": "00000000-0000-0000-0000-000000000002",
      "series_name": "Assinatura",
      "series_kind": "OPEN",
      "installments": null,
      "occurrence_index": 11,
      "occurrence_on": "2026-11-10"
    }
  ],
  "meta": {
    "total": 1,
    "limit": 12,
    "offset": 0,
    "next_page": null,
    "previous_page": null,
    "total_pages": 1,
    "current_page": 1
  }
}
```

Os filtros herdam `FilterPage`, seguindo o padrao de transactions: `page` e
`limit`, ou `offset` e `limit`, ativam `CustomLimitOffsetPage` (`items` e `meta`).
`page=1` e a primeira pagina; `page` tem precedencia sobre `offset`.
O limite padrao e 12, com teto de 100 pelo mecanismo compartilhado.
Sem `page` e sem `offset`, retorna uma lista simples, como as demais listagens.
A paginacao ocorre depois de combinar, substituir, filtrar e ordenar as
entradas; `meta.total` conta o resultado completo antes do recorte.
`clean_cache` e aceito por `FilterPage`, mas esta consulta nao usa cache.

`value` e serializado como string decimal. `order_by` aceita `expected_on`
(padrao), `name` ou `value`; `order` aceita `desc` (padrao) ou `asc`.
Nos empates, avulsas, gravadas e projetadas, com desempate estavel por
identificador e indice.

### Projecoes e substituicoes

- `TRANSACTION`: avulsa persistida, com UUID e campos de serie nulos.
- `SCHEDULED`: ocorrencia persistida; prevalece sobre a projecao do mesmo
  par `(transaction_series_id, occurrence_index)`.
- `PROJECTED`: ocorrencia calculada em memoria; `id=null` e identidade pelo
  par `(transaction_series_id, occurrence_index)`, a partir de **1**.
  Nao sao gerados UUIDs aleatorios para projecoes.

A serie e uma regra e nao gera uma linha adicional no extrato.
O calculo respeita `WEEK`, `MONTH`, `YEAR`, `frequency_interval`, ancoras,
`start_date`, `end_date` e o limite de parcelas de series `CLOSED`.
A primeira ocorrencia e a primeira data correspondente a ancora a partir do
inicio da serie; o intervalo e contado a partir dela. Por exemplo, inicio
em 15/09 com dia 10 tem primeira ocorrencia em 10/10.
Ancoras omitidas usam dia/mes/dia-da-semana da data inicial.
Dias da semana seguem ISO: segunda=1 e domingo=7.
Meses curtos ajustam o dia ao ultimo existente, sem perder a ancora nos meses
seguintes; 29/02 anual volta a 29/02 nos anos bissextos.

Projecoes sao sempre `PENDING`, inclusive em datas passadas. Confirmacao e
cancelamento dependem de um registro persistido. O GET nao materializa
ocorrencias, nao altera status e nao faz commit.

O periodo e aplicado sobre o `expected_on` final. Quando uma ocorrencia e
movida para outro mes, sua projecao original e suprimida mesmo se a versao
gravada estiver fora do periodo consultado. `occurrence_on` e o indice
identificam a ocorrencia original; `expected_on` e a data atual.
Os demais filtros sao aplicados depois dessa substituicao, evitando recriar
uma pendente quando a gravada esta cancelada, efetivada ou tem outros dados.

Series excluidas e seus agendamentos nao aparecem. Avulsas e agendamentos
com `deleted_at` preenchido tambem sao ignorados. Excluir fisicamente um
agendamento volta a permitir a projecao da serie. Dois agendamentos vivos
para o mesmo par serie/indice sao inconsistentes e retornam erro registrado
em log, em vez de selecionar arbitrariamente um deles.

`statement/route.py` delega ao servico; `statement/repository.py` consulta os
registros por dono; `statement/business.py` projeta e combina em memoria;
`statement/schema.py` define filtros e DTOs. Falhas de banco ou regras
invalidas de series persistidas retornam `500` com logging padrao.

## Seed de dados

`POST /transactions/seed` popula `transactions`, `transaction_series` e
`scheduled_transactions` com dados ficticios. Exige Bearer token de um usuario
cujo role persistido tenha `name_code="admin"` e nao esteja excluido.
A verificacao tambem ocorre em `TransactionService.seed`, inclusive em chamadas
diretas ao servico.

## Executar

Crie previamente pelo menos uma conta ativa para o administrador autenticado.
Cartoes e categorias sao opcionais. O seed nao cria esses recursos.

```bash
curl -X POST http://localhost:8000/transactions/seed \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "transactions": 100,
    "recurrences": 5,
    "installment_plans": 5,
    "months": 6,
    "seed": 42
  }'
```

O corpo `{}` utiliza os padroes abaixo; o corpo JSON e obrigatorio.

| Campo | Padrao | Limites |
|---|---|---|
| `transactions` | 100 | 0 a 1000 transacoes avulsas |
| `recurrences` | 5 | 0 a 100 series abertas |
| `installment_plans` | 5 | 0 a 100 series fechadas |
| `months` | 6 | 1 a 24 meses |
| `seed` | gerado pelo servidor | inteiro de 0 a 4294967295 ou `null` |

Ao menos uma quantidade deve ser positiva. Somente inteiros JSON sao aceitos;
campos extras, incluindo `user_id`, sao rejeitados.

Resposta `201 Created` (contagens e datas variam conforme a geracao):

```json
{
  "seed": 42,
  "start_date": "2026-06-01",
  "end_date": "2026-11-30",
  "transactions": 100,
  "transaction_series": 10,
  "scheduled_transactions": 50
}
```

`transaction_series` e a soma de recorrencias e parcelamentos.
`scheduled_transactions` informa o numero efetivo de ocorrencias persistidas.
A seed usada e devolvida mesmo quando gerada pelo servidor.

## Regras de geracao

- O periodo inclui o primeiro dia do mes de `months - 1` meses atras ate o
  ultimo dia do mes atual. A referencia e a data UTC do servidor.
- Transacoes avulsas sao distribuidas aleatoriamente nesse periodo. A quantidade
  de entradas e `floor(transactions * 0.15)`; as demais sao saidas.
- Avulsas usam nomes, pesos e `valueRange` de `transactions.json`.
  Recorrencias usam `recurrences.json`; parcelamentos usam
  `installment-plans.json`. Os tres arquivos sao JSON valido, validados pelo
  loader; catalogos vazios, unidades invalidas e faixas invertidas sao rejeitados.
  Valores sao sorteados em centavos, sem calculos monetarios em ponto flutuante.
- As series comecam em uma data aleatoria entre o inicio do periodo e hoje.
  Recorrencias usam `kind=OPEN`, sem fim ou numero de parcelas, e respeitam
  `direction`, `valueRange`, `categoryHint` e `unit` do template escolhido por
  `weight`. A frequencia pode ser `WEEK`, `MONTH` ou `YEAR`, sempre com intervalo
  1. A ancora e a data inicial: dia da semana ISO (1=segunda, 7=domingo) para
  semanais; dia do mes para mensais; mes e dia para anuais. Campos de ancora
  nao aplicaveis ficam nulos. As ocorrencias sao materializadas ate o fim do periodo.
- Parcelamentos usam `kind=CLOSED`, sao saidas mensais, com intervalo 1.
  `installmentsRange` determina o numero de parcelas (de 2 a 24 no catalogo
  atual), e `totalRange` determina o valor total da compra. O template e
  sorteado por `weight`, preservando seu nome e `categoryHint`.
  Todas as parcelas sao materializadas, inclusive se ultrapassarem o periodo.
  O total e dividido em centavos: `value` da serie e o valor base de uma parcela,
  e os centavos restantes sao distribuidos nas primeiras parcelas (mais um
  centavo em cada), garantindo que a soma seja exatamente o total sorteado.
  `end_date` coincide com a ultima parcela.
- Ocorrencias preservam os dados da serie e recebem `transaction_series_id`,
  `occurrence_on=expected_on` e `occurrence_index` sequencial a partir de 1.
  Valores de parcelas podem diferir do valor base em um centavo pelo rateio.
  Dias 29 a 31 sao ajustados ao ultimo dia de meses curtos, sem alterar a ancora
  original nos meses seguintes; anuais em 29 de fevereiro usam 28 nos anos comuns.
- Datas anteriores a hoje ficam `SETTLED`, com `settled_on=expected_on`;
  hoje e datas futuras ficam `PENDING`, sem `settled_on`.
- Somente contas e cartoes ativos e nao excluidos do administrador sao usados.
  Cartoes podem ser associados a saidas com probabilidade de 35%; entradas
  nunca recebem cartao. Sem cartoes, a geracao continua normalmente.
- `categoryHint` busca uma subcategoria de mesmo nome, ativa e nao excluida,
  de uma categoria tambem ativa e nao excluida do administrador. Sem
  correspondencia, `subcategory_id` fica nulo. Nomes repetidos usam a primeira
  correspondencia ordenada por IDs de categoria e subcategoria.

## Seguranca, atomicidade e repeticao

Todos os registros pertencem ao administrador autenticado. Nao e possivel
escolher outro dono, nem utilizar recursos de outros usuarios.

A gravacao do agregado e atomica: uma falha antes do commit desfaz toda a
execucao. Apos o commit, os caches dos recursos alterados sao invalidados;
falhas de cache sao registradas em log, sem desfazer dados ja confirmados.
O servico registra sucesso e erros pelo mecanismo padrao de logging.

O seed **adiciona** dados, nao apaga nem atualiza registros existentes. Nao e
idempotente: repetir a chamada cria novos registros. A mesma seed, parametros,
data UTC, tres catalogos e conjunto de contas/cartoes/categorias produz os mesmos
dados de negocio, mas nao os mesmos UUIDs ou timestamps. Alteracoes nesses
insumos ou no algoritmo podem alterar o resultado.

Use somente em bases destinadas a desenvolvimento ou demonstracao: os dados
ficticios participam das consultas normais. Nao ha limpeza automatica nem
bloqueio por ambiente.

| Status | Motivo |
|---|---|
| `401` | Token ausente ou invalido |
| `403` | Usuario sem role admin valido |
| `409` | Administrador sem conta ativa e nao excluida |
| `422` | Parametros invalidos |
| `500` | Falha no catalogo ou na persistencia; sem gravacao parcial |

## Implementacao e testes

`route.py` delega ao servico; `service.py` autoriza e orquestra;
`business.py` planeja os dados sem acesso a banco/cache; `seeds.py` valida e
carrega os tres catalogos; `repository.py` consulta recursos por dono e persiste em lote.

```bash
poetry run pytest -q tests/app/domain/transaction
make test
```
