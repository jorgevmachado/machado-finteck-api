# Domain Payer

O domain `beneficiary.py` gerencia favorecidos, recebedores ou entidades às quais o
usuário realiza pagamentos. Ele fornece um CRUD protegido e mantém nomes
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
| `service.py` | Orquestra CRUD, ownership, unicidade, cache, logs e erros |
| `repository.py` | Persistência assíncrona com SQLAlchemy |

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
