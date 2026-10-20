# Domain Institution

O domain `institution` gerencia as instituições financeiras cadastradas por cada
usuário, como bancos ou corretoras. Ele permite criar, listar, consultar,
renomear e excluir instituições, mantendo cada registro vinculado ao usuário
autenticado.

## Responsabilidades

- validar o nome e remover espaços excedentes;
- gerar `name_code` a partir do nome para identificar nomes equivalentes;
- impedir instituições com o mesmo nome normalizado na conta do mesmo usuário;
- restringir listagens e consultas às instituições do usuário autenticado;
- manter o nome e o código normalizado sincronizados ao renomear;
- invalidar o cache de listagem e do registro alterado após mudanças;
- registrar operações e encaminhar erros pelas convenções de serviço da API.

Usuários diferentes podem cadastrar instituições com o mesmo nome.

## Estrutura

| Arquivo | Responsabilidade |
|---|---|
| `route.py` | Endpoints protegidos em `/institutions` |
| `schema.py` | Validação dos dados de entrada e saída |
| `service.py` | Regras de unicidade, ownership, cache, logs e erros |
| `repository.py` | Persistência e consultas assíncronas com SQLAlchemy |
| `app/models/institution/institution.py` | Modelo e restrição de unicidade no banco |

## Endpoints

| Método | Rota | Ação |
|---|---|---|
| `POST` | `/institutions` | Cadastra uma instituição |
| `GET` | `/institutions` | Lista instituições; aceita filtros e paginação |
| `GET` | `/institutions/{institution_id}` | Consulta uma instituição |
| `PUT` | `/institutions/{institution_id}` | Atualiza o nome de uma instituição |
| `DELETE` | `/institutions/{institution_id}` | Exclui uma instituição |

> [!IMPORTANT]
> Todos os endpoints exigem autenticação JWT. O proprietário é identificado
> pela sessão autenticada; o cliente não escolhe o `user_id` do registro.

## Exemplo

```json
{
  "name": "  Banco Exemplo  "
}
```

O nome é armazenado sem espaços excedentes e gera internamente o código
`banco_exemplo`, usado para verificar duplicidades entre as instituições do
mesmo usuário.

## Testes

```bash
make test-file file=tests/app/domain/institution
```
