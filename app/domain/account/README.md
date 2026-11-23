# Domain Account

O domain `account` gerencia as contas financeiras pertencentes ao usuário
autenticado. Ele concentra o CRUD de contas, filtros de listagem e o isolamento
dos dados por proprietário.

O módulo mantém os dados cadastrais das contas (tipo, instituição, agência,
número e metadados visuais); não realiza movimentações, conciliação ou cálculos.

## Responsabilidades

- criar contas vinculadas ao usuário autenticado;
- impedir, na criação, a duplicidade de nome de conta para o usuário;
- listar e filtrar somente as contas do proprietário;
- atualizar apenas os campos enviados no payload;
- excluir contas de forma definitiva;
- invalidar entradas de cache relacionadas durante atualizações;
- registrar operações e tratar erros com os helpers compartilhados do projeto.

## Estrutura

| Arquivo | Responsabilidade |
|---|---|
| `route.py` | Endpoints protegidos em `/accounts` e parâmetros de listagem |
| `schema.py` | Contratos Pydantic de criação, atualização e resposta |
| `service.py` | Herda CRUD de `app.core.BaseService`; especializa normalização e unicidade de nome |
| `repository.py` | Herda consultas, ownership e persistência de `app.core.BaseRepository`; busca de duplicidade por nome |
| `../../models/account/account.py` | Modelo SQLAlchemy da tabela `accounts` |
| `../../models/account/enums.py` | Tipos aceitos por `AccountTypeEnum` |

## Endpoints

| Método | Rota | Ação |
|---|---|---|
| `POST` | `/accounts` | Cria uma conta e retorna seus dados (`201`) |
| `POST` | `/accounts/seed` | Cria contas padrao ausentes (`200`) |
| `GET` | `/accounts` | Lista contas, com suporte a filtros e paginação |
| `GET` | `/accounts/{account_id}` | Busca uma conta por identificador |
| `PUT` | `/accounts/{account_id}` | Atualiza os campos enviados e retorna `Message` |
| `DELETE` | `/accounts/{account_id}` | Exclui uma conta e retorna `Message` |

> [!IMPORTANT]
> Todos os endpoints exigem autenticação JWT e limitam as operações ao
> `user_id` do usuário autenticado. Uma conta inexistente ou pertencente a outro
> usuário resulta em `404`; um nome já cadastrado para o proprietário resulta em
> `409` na criação.

## Dados e regras

Na criação, `name` e `type` são obrigatórios. `is_active` assume `true` quando
omitido e não aceita `null` (nem no update). Os campos `icon`, `color`, `agency`,
`description`, `account_number` e `financial_institution` são opcionais. O filtro
de listagem aceita `type` como enum de tipo de conta e `is_active` como booleano;
valores inválidos retornam `422`.

Os tipos aceitos são `CHECKING`, `SAVINGS`, `CASH`, `INVESTMENT` e `OTHER`.

A atualização usa `exclude_unset=True`: campos omitidos permanecem inalterados,
mesmo utilizando o método `PUT`. Os campos `name`, `type` e `is_active` não
aceitam `null` explícito.

As consultas são feitas diretamente pelo repositório, sem leitura de cache.
Na atualização, o serviço tenta invalidar o cache relacionado; falhas nessa
invalidação são registradas como aviso e não interrompem a operação.

## Exemplo

Payload de criação:

```json
{
  "name": "Conta principal",
  "type": "CHECKING",
  "agency": "1234",
  "account_number": "123456789",
  "is_active": true
}
```

## Seed

`POST /accounts/seed` segue o padrao de category: exige apenas autenticacao
JWT (nao exige admin), nao recebe corpo e usa `accounts.json`, validado por
`seeds.py`. As contas sao vinculadas ao usuario autenticado.

Retorna `{"created": 14, "skipped": 0}` na primeira execucao em uma conta vazia.
Nomes ja cadastrados para o mesmo usuario sao ignorados, sem alterar seus
dados. Repetir a chamada retorna `created=0`; outros usuarios possuem seus
proprios registros. A gravacao ocorre em uma unica transacao e o cache do
usuario e invalidado apos o commit quando houver criacoes.

```bash
curl -X POST http://localhost:8000/accounts/seed \
  -H "Authorization: Bearer $TOKEN"
```

## Testes

```bash
make test-file file=tests/app/domain/account
```