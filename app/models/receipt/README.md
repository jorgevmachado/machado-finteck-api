# Modelos de interpretacao de receipts

`ReceiptInterpretationProfile` agrupa regras de campos e de identificacao:

- Geral compartilhado: `user_id=None` e `institution_code=None`.
- Instituicao privada: `user_id` e `institution_code` preenchidos.
- Um unico Geral nao excluido e um perfil nao excluido por usuario/instituicao.
  Perfis inativos continuam reservando sua identidade; a exclusao logica permite
  cadastrar um novo perfil sem apagar o anterior.

`institution_code` e um codigo estavel, normalizado pelo contrato de entrada
do CRUD, nao um nome de exibicao. `name` e o nome apresentado.

`ReceiptIdentificationRule` referencia o perfil por `profile_id` e armazena
padrao e peso positivo. O CRUD nao permite alterar o Geral, inclusive suas
regras: essa autorizacao nao e implementada pelos modelos.

`ReceiptFieldRule` referencia o perfil por `profile_id`. Existe no maximo uma
regra nao excluida por perfil/campo, inclusive quando inativa. A configuracao
JSONB e obrigatoria; em PostgreSQL deve ser um objeto nao vazio.

Os relacionamentos ORM carregam os registros vinculados, inclusive inativos e
excluidos. O resolvedor dinamico filtra esses registros antes de executar
regras. Sem regra especifica ativa, usa-se a regra Geral; uma regra especifica
executada sem resultado nao implica fallback automatico.

O [CRUD de perfis](../../domain/receipt/receipt_interpretation_profile/README.md)
valida `configuration` com schemas Pydantic, campos/conversores permitidos,
sintaxe regex e limites de tamanho. Os checks de banco nao substituem essa
validacao. Usuarios editam apenas seus perfis privados; Geral e somente leitura
nessa API, sem endpoints administrativos.

O motor dinamico usa os perfis atuais no upload, com heranca do Geral, execucao
isolada e limitada por tempo/memoria e snapshot das regras em
`receipts.data["_interpretation"]`. O seed de desenvolvimento cria Geral e os
perfis privados dos bancos; a API continua sem permitir escrita no Geral.
Consulte os limites e a semantica no README do CRUD. Limites de tamanho e
validacao sintatica sozinhos nao garantem execucao segura de regex.

A migration `77ce33061567_receipt_rules.py` cria essas tabelas e e pre-requisito
do CRUD. O cadastro preserva os modelos e nao exige outra migration.
