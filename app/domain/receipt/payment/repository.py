from __future__ import annotations

from datetime import date
from typing import Annotated, cast
from uuid import UUID

from sqlalchemy import select, desc, asc, func
from sqlalchemy.orm import aliased, selectinload


from fastapi import Query

from app.core.pagination import is_paginate
from app.core.repository.base import BaseRepository
from app.models import Beneficiary, Institution, Payment, Subcategory, Payer
from app.shared.schemas import FilterPage
from app.shared.utils.string import text_strip, to_snake_case


class PaymentRepository(BaseRepository[Payment]):
    model = Payment

    async def delete(self, entity: Payment) -> None:
        await self.session.delete(entity)
        await self.session.commit()

    @staticmethod
    def _get_name_code(name: str) -> str:
        return to_snake_case(name)

    @staticmethod
    def _get_order_column(order_by: str | None = None):
        match order_by:
            case "payment_date":
                return Payment.payment_date
            case "amount":
                return Payment.amount
            case _:
                return Payment.created_at

    def _order_by(
        self,
        query,
        page_filter: Annotated[FilterPage, Query()] | None = None,
    ):
        order = getattr(page_filter, "order", None) if page_filter else None
        order_by = getattr(page_filter, "order_by", None) if page_filter else None

        if order is None and order_by is None:
            return self._apply_order_by(query=query, page_filter=page_filter)

        column = self._get_order_column(order_by)
        query = query.order_by(asc(column) if order == "asc" else desc(column))
        return query

    def _build_filter(
        self,
        query,
        user_id: UUID,
        page_filter: Annotated[FilterPage, Query()] | None = None,
    ):
        relations = {
            "payer": Payer,
            "subcategory": Subcategory,
            "beneficiary": Beneficiary,
            "destination_institution": Institution,
            "source_institution": Institution,
        }
        query = query.where(Payment.user_id == user_id)
        if page_filter is None:
            return query
        raw_filters = page_filter.model_dump(exclude_none=True)
        for relation, model in relations.items():
            if raw_filters.get(relation):
                name = cast(str, raw_filters[relation])
                related_model = aliased(model)
                query = query.join(related_model, getattr(Payment, relation))
                if relation == "subcategory":
                    query = query.where(related_model.name == text_strip(name))
                else:
                    query = query.where(
                        related_model.name_code == self._get_name_code(name)
                    )
        if raw_filters.get("start_date"):
            query = query.where(Payment.payment_date >= raw_filters.get("start_date"))
            raw_filters.pop("start_date")
        if raw_filters.get("end_date"):
            query = query.where(Payment.payment_date <= raw_filters.get("end_date"))
            raw_filters.pop("end_date")
        return query

    @staticmethod
    def _only_filter_date(page_filter: Annotated[FilterPage, Query()] | None = None):
        if page_filter is not None:
            raw_filters = page_filter.model_dump(exclude_none=True)
            start_date = raw_filters.get("start_date")
            end_date = raw_filters.get("end_date")
            page_filter = FilterPage.build(
                start_date=start_date,
                end_date=end_date,
            )
        return page_filter

    async def list(
        self, user_id: UUID, page_filter: Annotated[FilterPage, Query()] | None = None
    ):
        query = select(self.model).options(
            selectinload(Payment.beneficiary),
            selectinload(Payment.subcategory),
            selectinload(Payment.payer),
            selectinload(Payment.source_institution),
            selectinload(Payment.destination_institution),
        )
        query = self._build_filter(query, user_id, page_filter)
        query = self._order_by(query, page_filter)
        if page_filter is not None and is_paginate(page_filter):
            return await self.list_paginate(query, page_filter)
        result = await self.session.scalars(query)
        return result.all()

    async def summary_count(
        self, user_id: UUID, page_filter: Annotated[FilterPage, Query()] | None = None
    ):
        query = select(self.model).options(
            selectinload(Payment.beneficiary),
            selectinload(Payment.subcategory),
            selectinload(Payment.payer),
            selectinload(Payment.source_institution),
            selectinload(Payment.destination_institution),
        )
        page_filter = self._only_filter_date(page_filter)
        query = self._build_filter(query, user_id, page_filter)
        result = await self.session.scalars(query)
        return {"count": len(result.all())}

    async def summary_total(
        self, user_id: UUID, page_filter: Annotated[FilterPage, Query()] | None = None
    ):
        query = select(self.model).options(
            selectinload(Payment.beneficiary),
            selectinload(Payment.subcategory),
            selectinload(Payment.payer),
            selectinload(Payment.source_institution),
            selectinload(Payment.destination_institution),
        )
        page_filter = self._only_filter_date(page_filter)
        query = self._build_filter(query, user_id, page_filter)
        result = await self.session.scalars(query)
        return {"total": sum(payment.amount for payment in result.all())}

    async def summary_order_by(
        self,
        user_id: UUID,
        order_by: str | None = None,
        page_filter: Annotated[FilterPage, Query()] | None = None,
    ):
        query = select(self.model).options(
            selectinload(Payment.beneficiary),
            selectinload(Payment.subcategory),
            selectinload(Payment.payer),
            selectinload(Payment.receipt),
            selectinload(Payment.source_institution),
            selectinload(Payment.destination_institution),
        )
        direction = asc if order_by == "asc" else desc
        query = query.order_by(direction(Payment.amount)).limit(1)
        page_filter = self._only_filter_date(page_filter)
        query = self._build_filter(query, user_id, page_filter)
        result = await self.session.scalars(query)
        return result.first()

    async def summary_beneficiary(
        self,
        user_id: UUID,
        beneficiary: str,
        page_filter: Annotated[FilterPage, Query()] | None = None,
    ):
        query = (
            select(self.model)
            .options(
                selectinload(Payment.beneficiary),
                selectinload(Payment.subcategory),
                selectinload(Payment.payer),
                selectinload(Payment.source_institution),
                selectinload(Payment.destination_institution),
            )
            .join(Payment.beneficiary)
            .where(Beneficiary.name_code == self._get_name_code(beneficiary))
        )

        page_filter = self._only_filter_date(page_filter)
        query = self._build_filter(query, user_id, page_filter)
        result = await self.session.scalars(query)
        return {
            "total": sum(payment.amount for payment in result.all()),
            "beneficiary": beneficiary,
        }

    def _build_dashboard_filter(
        self,
        query,
        user_id: UUID,
        start_date: date,
        end_date: date,
        institution: str | None = None,
        payer_id: UUID | None = None,
        subcategory_id: UUID | None = None,
        beneficiary_id: UUID | None = None,
    ):
        query = query.where(
            Payment.user_id == user_id,
            Payment.payment_date >= start_date,
            Payment.payment_date <= end_date,
        )

        if institution:
            query = query.join(Payment.source_institution).where(
                Institution.name_code == self._get_name_code(institution)
            )

        if beneficiary_id:
            query = query.where(Payment.beneficiary_id == beneficiary_id)

        if subcategory_id:
            query = query.where(Payment.subcategory_id == subcategory_id)

        if payer_id:
            query = query.where(Payment.payer_id == payer_id)

        return query

    async def dashboard_summary(
        self,
        user_id: UUID,
        start_date: date,
        end_date: date,
        institution: str | None = None,
        beneficiary_id: UUID | None = None,
    ):
        query = select(
            func.count(Payment.id).label("count"),
            func.coalesce(func.sum(Payment.amount), 0).label("total"),
            func.coalesce(
                func.round(func.avg(Payment.amount), 2),
                0,
            ).label("average"),
            func.coalesce(func.max(Payment.amount), 0).label("highest"),
        )

        query = self._build_dashboard_filter(
            query=query,
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
            institution=institution,
            beneficiary_id=beneficiary_id,
        )

        result = await self.session.execute(query)
        row = result.one()

        return {
            "count": row.count,
            "total": row.total,
            "average": row.average,
            "highest": row.highest,
        }

    async def dashboard_monthly(
        self,
        user_id: UUID,
        start_date: date,
        end_date: date,
        institution: str | None = None,
        beneficiary_id: UUID | None = None,
    ):
        period = func.to_char(Payment.payment_date, "YYYY-MM").label("period")

        query = select(
            period,
            func.count(Payment.id).label("count"),
            func.coalesce(func.sum(Payment.amount), 0).label("total"),
        )

        query = self._build_dashboard_filter(
            query=query,
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
            institution=institution,
            beneficiary_id=beneficiary_id,
        )

        query = query.group_by(period).order_by(period)

        result = await self.session.execute(query)

        return [
            {
                "period": row.period,
                "count": row.count,
                "total": row.total,
            }
            for row in result
        ]

    async def dashboard_institutions(
        self,
        user_id: UUID,
        start_date: date,
        end_date: date,
        institution: str | None = None,
        beneficiary_id: UUID | None = None,
    ):
        query = select(
            Institution.id.label("institution_id"),
            Institution.name_code.label("institution"),
            func.count(Payment.id).label("count"),
            func.coalesce(func.sum(Payment.amount), 0).label("total"),
        ).join(Payment.source_institution)

        query = self._build_dashboard_filter(
            query=query,
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
            institution=institution,
            beneficiary_id=beneficiary_id,
        )

        query = query.group_by(Institution.id, Institution.name_code).order_by(
            desc(func.sum(Payment.amount))
        )

        result = await self.session.execute(query)

        return [
            {
                "institution_id": row.institution_id,
                "institution": row.institution,
                "count": row.count,
                "total": row.total,
            }
            for row in result
        ]

    async def dashboard_beneficiaries(
        self,
        user_id: UUID,
        start_date: date,
        end_date: date,
        institution: str | None = None,
        beneficiary_id: UUID | None = None,
    ):
        query = select(
            Beneficiary.id.label("beneficiary_id"),
            Beneficiary.name.label("name"),
            func.count(Payment.id).label("count"),
            func.coalesce(func.sum(Payment.amount), 0).label("total"),
        ).join(Payment.beneficiary)

        query = self._build_dashboard_filter(
            query=query,
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
            institution=institution,
            beneficiary_id=beneficiary_id,
        )

        query = query.group_by(Beneficiary.id, Beneficiary.name).order_by(
            desc(func.sum(Payment.amount))
        )

        result = await self.session.execute(query)

        return [
            {
                "beneficiary_id": row.beneficiary_id,
                "name": row.name,
                "count": row.count,
                "total": row.total,
            }
            for row in result
        ]

    async def dashboard_subcategories(
        self,
        user_id: UUID,
        start_date: date,
        end_date: date,
        institution: str | None = None,
        subcategory_id: UUID | None = None,
    ):
        query = select(
            Subcategory.id.label("subcategory_id"),
            Subcategory.name.label("name"),
            func.count(Payment.id).label("count"),
            func.coalesce(func.sum(Payment.amount), 0).label("total"),
        ).join(Payment.subcategory)

        query = self._build_dashboard_filter(
            query=query,
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
            institution=institution,
            subcategory_id=subcategory_id,
        )

        query = query.group_by(Subcategory.id, Subcategory.name).order_by(
            desc(func.sum(Payment.amount))
        )

        result = await self.session.execute(query)

        return [
            {
                "subcategory_id": row.subcategory_id,
                "name": row.name,
                "count": row.count,
                "total": row.total,
            }
            for row in result
        ]

    async def dashboard_payers(
        self,
        user_id: UUID,
        start_date: date,
        end_date: date,
        institution: str | None = None,
        payer_id: UUID | None = None,
    ):
        query = select(
            Payer.id.label("payer_id"),
            Payer.name.label("name"),
            func.count(Payment.id).label("count"),
            func.coalesce(func.sum(Payment.amount), 0).label("total"),
        ).join(Payment.payer)

        query = self._build_dashboard_filter(
            query=query,
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
            institution=institution,
            payer_id=payer_id,
        )

        query = query.group_by(Payer.id, Payer.name).order_by(
            desc(func.sum(Payment.amount))
        )

        result = await self.session.execute(query)

        return [
            {
                "payer_id": row.payer_id,
                "name": row.name,
                "count": row.count,
                "total": row.total,
            }
            for row in result
        ]
