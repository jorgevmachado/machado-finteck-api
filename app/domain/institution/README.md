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

Aplique `make migrate` antes de usar o seed em uma base existente. A migration
`2e7f31ff6244` remove a unicidade global de `name_code`, preservando a constraint
`uq_institutions_user_id_name_code`. O downgrade exige que nao existam codigos
repetidos entre usuarios; caso existam, o banco rejeita a restauracao da
restricao global sem apagar dados.

## Estrutura

| Arquivo | Responsabilidade |
|---|---|
| `route.py` | Endpoints protegidos em `/institutions` |
| `schema.py` | Validação dos dados de entrada e saída |
| `service.py` | Herda CRUD de `app.core.BaseService`; especializa normalização e unicidade |
| `repository.py` | Herda consultas, ownership e persistência de `app.core.BaseRepository` |
| `app/models/institution/institution.py` | Modelo e restrição de unicidade no banco |

## Endpoints

| Método | Rota | Ação |
|---|---|---|
| `POST` | `/institutions` | Cadastra uma instituição |
| `POST` | `/institutions/seed` | Cria instituicoes padrao ausentes (`200`) |
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

## Seed

`POST /institutions/seed` segue o padrao de category: exige apenas autenticacao
JWT (nao exige admin) e nao recebe corpo. O catalogo `institutions.json` contem
instituicoes financeiras presentes no catalogo de contas, sem a entrada
"Dinheiro em especie", e e validado por `seeds.py`.

Retorna `{"created": 13, "skipped": 0}` para um usuario sem instituicoes.
O servico compara o `name_code` normalizado somente dentro dos registros do
usuario autenticado e ignora os existentes, preservando seus dados.
Repetir a chamada nao duplica registros; usuarios diferentes recebem suas
proprias instituicoes. A gravacao e atomica e o cache do usuario e invalidado
apos o commit quando houver criacoes.

```bash
curl -X POST http://localhost:8000/institutions/seed \
  -H "Authorization: Bearer $TOKEN"
```

## Testes

```bash
make test-file file=tests/app/domain/institution
```
