# Transaction: seed de dados

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
