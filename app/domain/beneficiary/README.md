# Domain Beneficiary

O domain `beneficiary` gerencia os favorecidos cadastrados por cada usuário — por
exemplo, pessoas ou empresas para as quais ele pretende realizar pagamentos. Ele
permite criar, listar, consultar, atualizar e excluir esses registros, mantendo
cada favorecido associado ao usuário autenticado.

## Responsabilidades

- validar e remover espaços excedentes do nome informado;
- gerar `name_code` a partir do nome para evitar duplicidades dentro da conta do
  mesmo usuário;
- limitar listagens e consultas aos favorecidos do usuário autenticado;
- atualizar o nome e seu código normalizado em conjunto;
- invalidar o cache de listagem e do registro alterado após mudanças;
- registrar operações e encaminhar erros pelas convenções de serviço da API.

Favorecidos com o mesmo nome normalizado podem existir para usuários diferentes,
mas não podem ser duplicados para o mesmo usuário.

## Estrutura

| Arquivo | Responsabilidade |
|---|---|
| `route.py` | Endpoints protegidos em `/beneficiaries` |
| `schema.py` | Validação dos dados de entrada e saída |
| `service.py` | Regras de unicidade, ownership, cache, logs e erros |
| `repository.py` | Persistência e consultas assíncronas com SQLAlchemy |
| `app/models/beneficiary/beneficiary.py` | Modelo e restrição de unicidade no banco |

## Endpoints

| Método | Rota | Ação |
|---|---|---|
| `POST` | `/beneficiaries` | Cadastra um favorecido |
| `GET` | `/beneficiaries` | Lista favorecidos; aceita filtros e paginação |
| `GET` | `/beneficiaries/{beneficiary_id}` | Consulta um favorecido |
| `PUT` | `/beneficiaries/{beneficiary_id}` | Atualiza o nome de um favorecido |
| `DELETE` | `/beneficiaries/{beneficiary_id}` | Exclui um favorecido |

> [!IMPORTANT]
> Todos os endpoints exigem autenticação JWT. O proprietário é identificado
> pela sessão autenticada; o cliente não escolhe o `user_id` do registro.

## Exemplo

```json
{
  "name": "  Companhia de Energia  "
}
```

O nome é armazenado sem espaços excedentes e gera internamente o código
`companhia_de_energia`. Esse código é usado para detectar nomes equivalentes
entre os favorecidos do mesmo usuário.

## Testes

```bash
make test-file file=tests/app/domain/beneficiary
```
