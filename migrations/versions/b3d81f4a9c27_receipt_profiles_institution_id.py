"""receipt profiles institution_id

Revision ID: b3d81f4a9c27
Revises: 2e7f31ff6244
Create Date: 2026-11-23 10:00:00.000000

Liga `receipt_interpretation_profiles` a `institutions` por FK e unifica o
vocabulario de `institution_code` com `Institution.name_code`.

Antes: `institution_code` era texto livre, com codigos de marca vindos do seed
(`ITAU`, `NUBANK`, `CAIXA`) que nunca casavam com `to_snake_case(name)` das
instituicoes cadastradas (`itau_unibanco`, `nu_pagamentos`, ...). Como
`_identify` soma pesos por codigo e devolve "unknow" no empate, dois perfis
ativos para a mesma instituicao derrubavam a identificacao.

Depois: `institution_id` e a fonte da verdade e `institution_code` passa a ser
o snapshot `name_code.upper()`, entao os dois lados falam o mesmo vocabulario.

O backfill roda em Python reusando `to_snake_case`, nao em SQL: `regexp_replace`
sobre `lower(translate(...))` diverge da normalizacao do runtime (deixa `_` nas
pontas e nao remove acentos fora do mapa, ex. `Å` -> `banco_ngstrom`), o que
recriaria o descasamento que esta migration existe para eliminar.

O downgrade NAO restaura os codigos de marca originais (`ITAU`/`NUBANK`/`CAIXA`):
a informacao se perde no upgrade. Recriar o catalogo e semear de novo se preciso.
"""

from typing import Sequence, Union
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

from app.shared.utils.string import to_snake_case

revision: str = "b3d81f4a9c27"
down_revision: Union[str, Sequence[str], None] = "2e7f31ff6244"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Nome canonico por codigo legado do seed. Codigos fora deste mapa usam o
# `name` do proprio perfil.
LEGACY_CODES = {
    "ITAU": "Itaú Unibanco",
    "NUBANK": "Nu Pagamentos",
    "CAIXA": "Caixa Econômica Federal",
}

SELECT_LEGACY = sa.text(
    """
    SELECT DISTINCT ON (p.user_id, p.institution_code)
        p.user_id,
        p.institution_code,
        p.name
    FROM receipt_interpretation_profiles AS p
    WHERE p.user_id IS NOT NULL
      AND p.institution_code IS NOT NULL
      AND p.institution_id IS NULL
    ORDER BY p.user_id, p.institution_code, p.created_at
    """
)

# A UniqueConstraint de `institutions` e (user_id, name_code) e NAO ignora
# soft-deleted: uma instituicao apagada com o mesmo codigo ainda bloqueia o
# INSERT, entao a busca nao filtra `deleted_at`.
SELECT_INSTITUTION = sa.text(
    """
    SELECT id, name_code
    FROM institutions
    WHERE user_id = :user_id
      AND name_code = :name_code
    """
)

INSERT_INSTITUTION = sa.text(
    """
    INSERT INTO institutions (id, user_id, name, name_code, created_at)
    VALUES (:id, :user_id, :name, :name_code, now())
    """
)

# Inclui soft-deleted: `ck_receipt_profiles_scope` vale para toda linha, nao so
# as vivas, e um perfil apagado sem `institution_id` derrubaria o upgrade.
UPDATE_PROFILE = sa.text(
    """
    UPDATE receipt_interpretation_profiles
    SET institution_id = :institution_id,
        institution_code = :institution_code,
        updated_at = now()
    WHERE user_id = :user_id
      AND institution_code = :legacy_code
      AND institution_id IS NULL
    """
)


def _institution_name(institution_code: str, profile_name: str) -> str:
    return LEGACY_CODES.get(institution_code, profile_name)


def _name_code(name: str, institution_code: str) -> str:
    code = to_snake_case(name)
    # `to_snake_case` pode esvaziar nomes so de simbolos; o codigo antigo e o
    # unico identificador estavel que resta.
    return code or to_snake_case(institution_code) or institution_code.lower()


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "receipt_interpretation_profiles",
        sa.Column("institution_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_receipt_profiles_institution_id",
        "receipt_interpretation_profiles",
        "institutions",
        ["institution_id"],
        ["id"],
    )

    bind = op.get_bind()
    for user_id, institution_code, profile_name in bind.execute(
        SELECT_LEGACY
    ).all():
        name = _institution_name(institution_code, profile_name)
        name_code = _name_code(name, institution_code)

        institution = bind.execute(
            SELECT_INSTITUTION,
            {"user_id": user_id, "name_code": name_code},
        ).first()
        if institution is None:
            institution_id = uuid4()
            bind.execute(
                INSERT_INSTITUTION,
                {
                    "id": institution_id,
                    "user_id": user_id,
                    "name": name,
                    "name_code": name_code,
                },
            )
        else:
            institution_id = institution.id

        bind.execute(
            UPDATE_PROFILE,
            {
                "institution_id": institution_id,
                "institution_code": name_code.upper(),
                "user_id": user_id,
                "legacy_code": institution_code,
            },
        )

    op.drop_constraint(
        "ck_receipt_profiles_scope",
        "receipt_interpretation_profiles",
        type_="check",
    )
    op.create_check_constraint(
        "ck_receipt_profiles_scope",
        "receipt_interpretation_profiles",
        "(user_id IS NULL AND institution_id IS NULL) OR "
        "(user_id IS NOT NULL AND institution_id IS NOT NULL)",
    )
    op.drop_index(
        "uq_receipt_profiles_owner_institution_live",
        table_name="receipt_interpretation_profiles",
    )
    op.create_index(
        "uq_receipt_profiles_owner_institution_live",
        "receipt_interpretation_profiles",
        ["user_id", "institution_id"],
        unique=True,
        postgresql_where=sa.text("user_id IS NOT NULL AND deleted_at IS NULL"),
        sqlite_where=sa.text("user_id IS NOT NULL AND deleted_at IS NULL"),
    )


def downgrade() -> None:
    """Downgrade schema.

    O vocabulario de `institution_code` nao volta a `ITAU`/`NUBANK`/`CAIXA`:
    a informacao original se perde no upgrade.
    """
    op.drop_index(
        "uq_receipt_profiles_owner_institution_live",
        table_name="receipt_interpretation_profiles",
    )
    op.create_index(
        "uq_receipt_profiles_owner_institution_live",
        "receipt_interpretation_profiles",
        ["user_id", "institution_code"],
        unique=True,
        postgresql_where=sa.text("user_id IS NOT NULL AND deleted_at IS NULL"),
        sqlite_where=sa.text("user_id IS NOT NULL AND deleted_at IS NULL"),
    )
    op.drop_constraint(
        "ck_receipt_profiles_scope",
        "receipt_interpretation_profiles",
        type_="check",
    )
    op.create_check_constraint(
        "ck_receipt_profiles_scope",
        "receipt_interpretation_profiles",
        "(user_id IS NULL AND institution_code IS NULL) OR "
        "(user_id IS NOT NULL AND institution_code IS NOT NULL)",
    )
    op.drop_constraint(
        "fk_receipt_profiles_institution_id",
        "receipt_interpretation_profiles",
        type_="foreignkey",
    )
    op.drop_column("receipt_interpretation_profiles", "institution_id")