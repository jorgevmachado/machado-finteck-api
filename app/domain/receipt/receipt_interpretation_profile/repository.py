from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import func, inspect, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import lazyload, selectinload

from app.core.pagination import CustomLimitOffsetPage, is_paginate
from app.core.pagination.pagination import get_limit_offset_params
from app.core.repository.base import BaseRepository
from app.domain.receipt.receipt_interpretation_profile.business import (
    RuleReconciliationPlan,
)
from app.domain.receipt.receipt_interpretation_profile.enums import ProfileScope
from app.domain.receipt.receipt_interpretation_profile.schema import (
    ReceiptFieldRuleReconcileSchema,
    ReceiptIdentificationRuleReconcileSchema,
    ReceiptInterpretationProfileFilter,
)
from app.models import (
    ReceiptFieldRule,
    ReceiptIdentificationRule,
    ReceiptInterpretationProfile,
)
from app.models.common import utcnow

logger = logging.getLogger(__name__)
_TRANSACTION_KEY = "app.domain.receipt.profile.transaction_active"


class ReceiptInterpretationProfileRepository(
    BaseRepository[ReceiptInterpretationProfile]
):
    model = ReceiptInterpretationProfile

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        if (
            self.session.info.get(_TRANSACTION_KEY)
            or self.session.in_nested_transaction()
        ):
            raise RuntimeError("Nested receipt profile transactions are not supported")
        self.session.info[_TRANSACTION_KEY] = True
        try:
            if not self.session.in_transaction():
                await self.session.begin()
            yield
            await self.session.commit()
        except BaseException:
            try:
                await self.session.rollback()
            except BaseException:
                logger.exception("Failed to roll back receipt profile transaction")
            raise
        finally:
            self.session.info.pop(_TRANSACTION_KEY, None)

    @staticmethod
    def _visibility(user_id: UUID):
        return (
            or_(
                ReceiptInterpretationProfile.user_id == user_id,
                ReceiptInterpretationProfile.user_id.is_(None),
            ),
            ReceiptInterpretationProfile.deleted_at.is_(None),
        )

    @staticmethod
    def _children():
        return (
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

    async def find_by(
        self, *, id: UUID, user_id: UUID, for_update: bool = False
    ) -> ReceiptInterpretationProfile | None:
        query = select(self.model).where(
            self.model.id == id, *self._visibility(user_id)
        )
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
            query.options(*self._children()).execution_options(populate_existing=True)
        )

    async def find_by_code(
        self, *, user_id: UUID, institution_code: str
    ) -> ReceiptInterpretationProfile | None:
        return await self.session.scalar(
            select(self.model).where(
                self.model.user_id == user_id,
                self.model.institution_code == institution_code,
                self.model.deleted_at.is_(None),
            )
        )

    async def list_all(
        self, page_filter: ReceiptInterpretationProfileFilter, *, user_id: UUID
    ) -> (
        list[ReceiptInterpretationProfile]
        | CustomLimitOffsetPage[ReceiptInterpretationProfile]
    ):
        conditions = list(self._visibility(user_id))
        if page_filter.name is not None:
            conditions.append(self.model.name == page_filter.name)
        if page_filter.institution_code is not None:
            conditions.append(
                self.model.institution_code == page_filter.institution_code
            )
        if page_filter.scope is not None:
            conditions.append(
                self.model.user_id.is_(None)
                if page_filter.scope == ProfileScope.SYSTEM
                else self.model.user_id == user_id
            )
        query = (
            select(self.model)
            .where(*conditions)
            .options(*self._children())
            .execution_options(populate_existing=True)
            .order_by(self.model.created_at, self.model.id)
        )
        if not is_paginate(page_filter):
            return list((await self.session.scalars(query)).all())
        params = get_limit_offset_params(page_filter)
        total = await self.session.scalar(
            select(func.count(self.model.id)).where(*conditions)
        )
        entities = await self.session.scalars(
            query.limit(params.limit).offset(params.offset)
        )
        return CustomLimitOffsetPage.create(
            items=list(entities.all()), total=total, params=params
        )

    async def save(
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
        if inspect(entity).persistent:
            entity.updated_at = now
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def delete(self, entity: ReceiptInterpretationProfile) -> None:
        self._require_transaction()
        now = utcnow()
        for item in (entity, *entity.field_rules, *entity.identification_rules):
            if item.deleted_at is None:
                item.deleted_at = now
                item.updated_at = now
                item.is_active = False
        await self.session.flush()

    def _require_transaction(self) -> None:
        if not self.session.info.get(_TRANSACTION_KEY):
            raise RuntimeError("Receipt profile mutations require transaction()")
