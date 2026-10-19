# Domain Credit Card

O domain `credit_card` gerencia os cartões de crédito pertencentes ao usuário
autenticado. Ele concentra o CRUD do cadastro, incluindo bandeira, limite,
dias de fechamento e vencimento, status e metadados visuais.

O módulo mantém os dados cadastrais dos cartões; não realiza compras,
processamento de pagamentos, geração de faturas ou cálculo de limite disponível.

## Responsabilidades

- criar cartões vinculados ao usuário autenticado;
- impedir, na criação, o cadastro de um cartão com nome já existente para o usuário;
- listar e consultar somente cartões do proprietário;
- atualizar apenas os campos enviados no payload;
- excluir cartões de forma definitiva;
- invalidar entradas de cache relacionadas durante atualizações;
- registrar operações e tratar erros com os helpers compartilhados do projeto.

## Estrutura

| Arquivo | Responsabilidade |
|---|---|
| `route.py` | Endpoints protegidos em `/credit-cards` e parâmetros de listagem |
| `schema.py` | Contratos Pydantic de criação, atualização e resposta |
| `service.py` | Orquestra CRUD, ownership, verificação de nome na criação, cache, logs e erros |
| `repository.py` | Reutiliza `BaseRepository` e implementa exclusão física |
| `../../models/credit_card/credit_card.py` | Modelo SQLAlchemy da tabela `credit_cards` |
| `../../models/credit_card/enums.py` | Bandeiras aceitas por `CreditCardBrandEnum` |

## Endpoints

| Método | Rota | Ação |
|---|---|---|
| `POST` | `/credit-cards` | Cria um cartão e retorna seus dados (`201`) |
| `GET` | `/credit-cards` | Lista cartões, com suporte a paginação |
| `GET` | `/credit-cards/{param}` | Busca um cartão por identificador |
| `PUT` | `/credit-cards/{credit_card_id}` | Atualiza os campos enviados e retorna `Message` |
| `DELETE` | `/credit-cards/{credit_card_id}` | Exclui um cartão e retorna `Message` |

> [!IMPORTANT]
> Todos os endpoints exigem autenticação JWT e limitam as operações ao
> `user_id` do usuário autenticado. Um cartão inexistente ou pertencente a outro
> usuário resulta em `404`; um nome já cadastrado para o proprietário resulta
> em `409` na criação.

## Dados e regras

Na criação, `name`, `brand`, `closing_day` e `due_day` são obrigatórios.
`is_active` assume `true` quando omitido. Os campos `limit`, `last_four_digits`,
`description`, `color` e `icon` são opcionais.

As bandeiras aceitas são `VISA`, `MASTERCARD`, `ELO`, `AMEX`, `HIPERCARD`,
`DINERS` e `OTHER`.

A atualização usa `exclude_unset=True`: campos omitidos permanecem inalterados,
mesmo utilizando o método `PUT`. Os campos `name`, `brand`, `closing_day` e
`due_day` não aceitam `null` explícito.

As consultas são feitas diretamente pelo repositório, sem leitura de cache.
Na atualização, o serviço tenta invalidar o cache relacionado; falhas nessa
invalidação são registradas como aviso e não interrompem a operação.

## Exemplo

Payload de criação:

```json
{
  "name": "Cartão principal",
  "brand": "VISA",
  "closing_day": 5,
  "due_day": 12,
  "last_four_digits": "1234",
  "is_active": true
}
```

## Testes

```bash
make test-file file=tests/app/domain/credit_card
```
