# Domain Payer

O domínio `payer` gerencia pagadores vinculados ao usuário autenticado.
Ele fornece um CRUD protegido e mantém nomes
normalizados para evitar cadastros duplicados por usuário.

## Responsabilidades

- criar um payer vinculado ao usuário autenticado;
- normalizar o nome em `name_code`;
- garantir unicidade de nome normalizado por usuário;
- listar e consultar somente payers do proprietário;
- atualizar nome e código normalizado de forma consistente;
- excluir payers e invalidar o cache relacionado.

## Estrutura

| Arquivo | Responsabilidade |
|---|---|
| `route.py` | Endpoints protegidos em `/payers` |
| `schema.py` | Validação dos contratos de entrada e saída |
| `service.py` | Herda CRUD de `app.temp.BaseService`; especializa normalização, unicidade e `resolve` |
| `repository.py` | Herda consultas, ownership e persistência de `app.temp.BaseRepository`; normaliza IDs |

## Piloto das bases

Este é o primeiro domínio integrado às bases de `app/temp`. Listagem, busca,
criação, atualização e exclusão são herdadas, sem reimplementar seus fluxos.
`_operation` centraliza erros e logs, seguindo a tática de receipt.
`resolve` reutiliza os helpers internos para evitar tradução e logs duplicados.

Cada mutação possui uma única transação; a exclusão continua física. A
normalização e a unicidade por `name_code` permanecem regras locais do payer.
O cache usa `CacheService` com namespace por proprietário e invalidação herdada
após commit. `list_all_cached` e `find_one_cached` estão disponíveis, mas os GETs
continuam consultando o banco como antes; não foi ativado cache de leitura nas
rotas. As rotas, formatos de resposta e mensagens de atualização/exclusão
permanecem iguais. A API interna de busca usa `user` e `filters` explícitos.

## Endpoints

| Método | Rota | Ação |
|---|---|---|
| `POST` | `/payers` | Cria um payer |
| `GET` | `/payers` | Lista e filtra payers |
| `GET` | `/payers/{payer_id}` | Busca um payer |
| `PUT` | `/payers/{payer_id}` | Atualiza um payer |
| `DELETE` | `/payers/{payer_id}` | Exclui um payer |

> [!IMPORTANT]
> Todos os endpoints exigem autenticação JWT. O `user_id` enviado pelo cliente
> nunca é utilizado para definir ou ampliar o escopo de acesso.

## Exemplo

```json
{
  "name": "Companhia de Energia"
}
```

O nome acima gera internamente o código `companhia_de_energia`.

## Testes

```bash
make test-file file=tests/app/domain/payer
```
