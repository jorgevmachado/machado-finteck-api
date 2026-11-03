from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID

from sqlalchemy import ColumnElement, Select, or_, select, text
from sqlalchemy.orm import lazyload, selectinload
from sqlalchemy.orm.util import object_state

from app.core.pagination import CustomLimitOffsetPage
from app.core.pagination.pagination import is_paginate
from app.domain.receipt.rules.business import RuleReconciliationPlan
from app.domain.receipt.rules.enums import ProfileScope
from app.domain.receipt.rules.field.schema import ReceiptFieldRuleReconcileSchema
from app.domain.receipt.rules.identification.schema import (
    ReceiptIdentificationRuleReconcileSchema,
)
from app.models import (
    ReceiptInterpretationProfile,
    ReceiptFieldRule,
    ReceiptIdentificationRule,
    utcnow,
)
from app.shared.schemas import FilterPage
from app.core.repository import BaseRepository


class ReceiptRulesRepository(BaseRepository[ReceiptInterpretationProfile]):
    model = ReceiptInterpretationProfile
    filter_fields = ("id", "name", "institution_code", "is_active")
    relations = (
        selectinload(
            ReceiptInterpretationProfile.field_rules.and_(
                ReceiptFieldRule.deleted_at.is_(None)
            )
        ),
        selectinload(
            ReceiptInterpretationProfile.identification_rules.and_(
                ReceiptIdentificationRule.deleted_at.is_(None)
            )
        ),
    )

    def _visibility(self) -> tuple[ColumnElement[bool], ...]:
        return (self.model.deleted_at.is_(None),)

    def _build_query(self, *, user_id: UUID) -> Select[ReceiptInterpretationProfile]:
        self.require_owner(user_id)
        return select(self.model).where(
            or_(self.model.user_id == user_id, self.model.user_id.is_(None)),
            *self._visibility(),
        )

    async def list_all(
        self, *, user_id: UUID, page_filter: FilterPage | None = None
    ) -> (
        list[ReceiptInterpretationProfile]
        | CustomLimitOffsetPage[ReceiptInterpretationProfile]
    ):
        raw = (
            page_filter.model_dump(exclude_none=True) if page_filter is not None else {}
        )
        filters = self.validate_filters(
            user_id=user_id,
            filters={field: raw[field] for field in self.filter_fields if field in raw},
        )
        query = self._build_filter(self._build_query(user_id=user_id), filters)
        scope = raw.get("scope")
        if scope is not None:
            query = query.where(
                self.model.user_id.is_(None)
                if ProfileScope(scope) == ProfileScope.SYSTEM
                else self.model.user_id == user_id
            )
        query = self._order_by(
            self._load_relations(query), order_by="created_at", order="asc"
        ).execution_options(populate_existing=True)
        if page_filter is not None and is_paginate(page_filter):
            return await self._list_paginate(query, page_filter=page_filter)
        return await self._execute_list(query)

    async def save_profile(
        self,
        entity: ReceiptInterpretationProfile,
        *,
        fields: RuleReconciliationPlan[ReceiptFieldRuleReconcileSchema] | None = None,
        identification: (
            RuleReconciliationPlan[ReceiptIdentificationRuleReconcileSchema] | None
        ) = None,
    ) -> ReceiptInterpretationProfile:
        self._require_transaction()
        now = utcnow()
        if fields is not None:
            live = {
                child.id: child
                for child in entity.field_rules
                if child.deleted_at is None
            }
            renamed = {
                entry.id
                for entry in fields.entries
                if entry.id is not None
                and live[entry.id].field_name != entry.field_name
            }
            # The partial unique index is immediate: release old keys before swaps.
            for child_id in set(fields.remove_ids) | renamed:
                child = live[child_id]
                child.deleted_at = now
                child.updated_at = now
                if child_id in fields.remove_ids:
                    child.is_active = False
            await self.session.flush()
            for entry in fields.entries:
                values = entry.model_dump(mode="json", exclude={"id"})
                if entry.id is None:
                    entity.field_rules.append(
                        ReceiptFieldRule(profile_id=entity.id, **values)
                    )
                else:
                    child = live[entry.id]
                    for key, value in values.items():
                        setattr(child, key, value)
                    child.deleted_at = None
                    child.updated_at = now
        if identification is not None:
            live_identification = {
                child.id: child
                for child in entity.identification_rules
                if child.deleted_at is None
            }
            for child_id in identification.remove_ids:
                child = live_identification[child_id]
                child.deleted_at = now
                child.updated_at = now
                child.is_active = False
            for entry in identification.entries:
                values = entry.model_dump(mode="json", exclude={"id"})
                if entry.id is None:
                    entity.identification_rules.append(
                        ReceiptIdentificationRule(profile_id=entity.id, **values)
                    )
                else:
                    child = live_identification[entry.id]
                    for key, value in values.items():
                        setattr(child, key, value)
                    child.updated_at = now
        if object_state(entity).persistent:
            entity.updated_at = now
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def find_by(
        self,
        *,
        user_id: UUID,
        filters: Mapping[str, object],
        for_update: bool = False,
    ) -> ReceiptInterpretationProfile | None:
        criteria = self.prepare_lookup(user_id=user_id, filters=filters)
        query = self._build_filter(self._build_query(user_id=user_id), criteria)
        if for_update:
            self._require_transaction()
            locked = await self.session.scalar(
                query.options(
                    lazyload(self.model.field_rules),
                    lazyload(self.model.identification_rules),
                ).with_for_update(of=self.model)
            )
            if locked is None:
                return None
        return await self.session.scalar(
            self._load_relations(query).execution_options(populate_existing=True)
        )

    async def lock_seed(self) -> None:
        self._require_transaction()
        await self.session.execute(
            text(
                "SELECT pg_advisory_xact_lock(hashtextextended('receipt-profile-seed', 0))"
            )
        )

    async def find_by_code(
        self, *, user_id: UUID | None, institution_code: str | None
    ) -> ReceiptInterpretationProfile | None:
        return await self.session.scalar(
            select(self.model).where(
                self.model.user_id == user_id,
                self.model.institution_code == institution_code,
                *self._visibility(),
            )
        )

    async def find_by_name(
        self,
        *,
        name: str,
        user_id: UUID,
        exclude_id: UUID | None = None,
    ) -> ReceiptInterpretationProfile | None:
        query = self._build_filter(
            super()._build_query(user_id=user_id), {"name": name}
        )
        if exclude_id is not None:
            query = query.where(self.model.id != exclude_id)
        return await self.session.scalar(query)

    async def delete_profile(self, entity: ReceiptInterpretationProfile) -> None:
        self._require_transaction()
        now = utcnow()
        for item in (entity, *entity.field_rules, *entity.identification_rules):
            if item.deleted_at is None:
                item.deleted_at = now
                item.updated_at = now
                item.is_active = False
        await self.session.flush()
