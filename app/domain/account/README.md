# Domain Account

O domain `account` gerencia as contas financeiras pertencentes ao usuário
autenticado. Ele concentra o CRUD de contas, filtros de listagem e o isolamento
dos dados por proprietário.

## Responsabilidades

- criar contas com tipo, instituição, agência, número e metadados visuais;
- listar e filtrar somente as contas do usuário autenticado;
- consultar, atualizar e excluir uma conta por identificador;
- impedir acesso a contas pertencentes a outro usuário;
- invalidar entradas de cache relacionadas após atualizações.

## Estrutura

| Arquivo | Responsabilidade |
|---|---|
| `route.py` | Endpoints protegidos em `/accounts` |
| `schema.py` | Contratos Pydantic de entrada e saída |
| `service.py` | Orquestra CRUD, ownership, cache, logs e erros |
| `repository.py` | Persistência assíncrona com SQLAlchemy |

## Endpoints

| Método | Rota | Ação |
|---|---|---|
| `POST` | `/accounts` | Cria uma conta |
| `GET` | `/accounts` | Lista e filtra contas |
| `GET` | `/accounts/{param}` | Busca uma conta |
| `PUT` | `/accounts/{account_id}` | Atualiza uma conta |
| `DELETE` | `/accounts/{account_id}` | Exclui uma conta |

> [!IMPORTANT]
> Todos os endpoints exigem autenticação JWT e limitam as operações ao
> `user_id` obtido do token.

## Testes

```bash
make test-file file=tests/app/domain/account
```
