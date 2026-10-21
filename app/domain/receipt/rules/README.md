# Seed de regras de receipts

`POST /receipts/rules/seed` exige autenticacao e nao recebe body.
O catalogo e `default_receipt_rules.json`, validado por um contrato interno
que aceita `institution_code: null` para o unico perfil Geral compartilhado.
O POST comum de criacao continua exigindo codigo de instituicao nao nulo.

O seed cria Geral com `user_id: null` e os perfis de instituicoes com o
usuario autenticado como dono. Geral nao aceita regras de identificacao.
Perfis ja existentes, inclusive inativos ou renomeados, sao preservados pela
identidade: Geral compartilhado ou `(usuario, institution_code)`, nunca nome.
Registros excluidos logicamente nao impedem nova criacao.

Raizes e filhos sao salvos em uma unica transacao; falhas desfazem o seed
inteiro e usam o handler padrao. Um advisory lock transacional PostgreSQL
serializa chamadas de seed, evitando criacao concorrente do Geral.
Nao se chama o caso de uso create dentro dessa transacao.

A resposta informa `created` e `skipped`. Em uma base vazia, o catalogo atual
cria quatro perfis. Repetir para o mesmo usuario retorna quatro skipped;
para outro usuario, preserva Geral e cria seus tres perfis privados.

## Origem configuravel

As regras `source_institution` usam `strategy: source`. Toda informacao de banco
fica em `receipt_field_rules.configuration` (JSONB), nao em enums ou condicoes
Python por instituicao. O catalogo JSON apenas fornece os dados iniciais:

```json
{
  "strategy": "source",
  "identified_value": "Caixa",
  "extraction": {
    "strategy": "regex",
    "patterns": ["Banco Recebedor:\\s*(?P<value>.+?)(?=\\n|Pagador Final)"],
    "parser": "text"
  },
  "mappings": [
    {"contains": "CAIXA ECONOMICA FEDERAL", "value": "Caixa"},
    {"contains": "CAIXA ECONÔMICA FEDERAL", "value": "Caixa"}
  ]
}
```

O motor recebe o perfil contextual e `identified`: true significa que esse
perfil ja foi identificado pelo chamador e devolve `identified_value`; false
avalia os `matches` (contains/value) ordenados sobre o documento. Sem match,
tenta as regex de `extraction` em ordem e normaliza o valor capturado com os
`mappings` ordenados. Contains ignora caixa, mas preserva acentos. Se nenhum
mapeamento corresponder, devolve o texto capturado; sem evidencia, not_found.
Captura vazia produz ambiguous. As listas aceitam ate 20 entradas; os textos de
mapeamento aceitam ate 200 caracteres. Extracao e somente text/strip, sem
fallback entre campos. A estrategia source e exclusiva de source_institution.
A estrategia constant anterior continua valida para registros existentes.

Nubank e Itau possuem matches cadastrados; Caixa possui extracao e mapeamentos.
Nao e necessario alterar o motor para cadastrar outro nome ou outra instituicao.
As condicoes nao consultam outras instituicoes automaticamente: false reproduz
o caminho alternativo do metodo do perfil informado, nao identifica bancos.

`ReceiptRulesService.extract_source_institution(profile_id, text, user,
identified=...)` carrega a regra atual com isolamento de usuario. O motor em
`configuration/engine.py` executa regex em subprocesso Linux com timeout de
3 segundos, limite de CPU de 2 segundos, 512 MiB de memoria virtual e entrada
de ate 1 milhao de caracteres. Erros sao propagados pelo helper padrao do service.
O resultado contem value e status found/not_found/ambiguous.
Nao foi criada rota de upload nem identificador completo de perfis nesta entrega.

Para registros ja populados, repetir seed NAO substitui configuracoes antigas.
Use o PUT do perfil, mantendo IDs das regras retidas e todas as regras desejadas
na colecao field_rules, para trocar a configuracao constant por source.
Nenhuma migration ou tabela extra e necessaria.

## Testes unitarios

```bash
poetry run pytest -q tests/app/domain/receipt
```

A suite do agregado nao usa PostgreSQL, Docker ou conexoes reais. Sessao e
repository sao mockados; rotas usam dependency overrides; o motor testa a
logica pura e o protocolo de subprocesso com processos mockados.
Os cenarios cobrem contratos, ownership, reconciliacao, SQL gerado, fronteira
transacional, erros, seed e origem configuravel.

Esses testes verificam as chamadas de commit/rollback e lock e a ordem dos
flushes, mas nao provam constraints, rollback persistido ou concorrencia real
do PostgreSQL. O fixture seed_sessions e os testes que dependiam dele foram
removidos; nao ha simulacao que substitua essas garantias do banco.
