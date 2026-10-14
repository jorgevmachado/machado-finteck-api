from typing import Annotated, Any

from fastapi import Depends, Query
from fastapi_pagination.ext.sqlalchemy import paginate
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.pagination import CustomLimitOffsetPage, is_paginate
from app.core.pagination.pagination import get_limit_offset_params
from app.shared.schemas import FilterPage

Session = Annotated[AsyncSession, Depends(get_session)]


class BaseRepository[ModelT]:
    model: type[ModelT]
    relations: tuple[Any, ...] = ()
    default_order_by: str | None = None

    def __init__(self, session: Session):
        self.session = session

    def _apply_order_by(
        self, query, page_filter: Annotated[FilterPage, Query()] = None
    ):
        order_by = getattr(page_filter, "order_by", None) if page_filter else None
        if not order_by:
            order_by = self.default_order_by
        if order_by is None:
            return query

        order_path = order_by.strip()

        if not order_path:
            return query

        path_parts = order_path.split(".")
        current_model = self.model

        for relation_name in path_parts[:-1]:
            relation_attr = getattr(current_model, relation_name, None)
            relation_property = getattr(relation_attr, "property", None)

            if relation_attr is None or relation_property is None:
                raise ValueError(
                    f'Invalid default_order_by relation "{relation_name}"'
                    f" for {current_model.__name__}"
                )

            if not hasattr(relation_property, "mapper"):
                raise ValueError(
                    f'Invalid default_order_by path "{order_path}": "{relation_name}"'
                    f" is not a relationship"
                )

            if relation_property.uselist:
                raise ValueError(
                    f'Invalid default_order_by path "{order_path}":'
                    f" collection relationships are not supported"
                )

            query = query.outerjoin(relation_attr)
            current_model = relation_property.mapper.class_

        field_name = path_parts[-1]
        order_attr = getattr(current_model, field_name, None)
        order_property = getattr(order_attr, "property", None)

        if order_attr is None or order_property is None:
            raise ValueError(
                f'Invalid default_order_by field "{field_name}" for {current_model.__name__}'
            )

        if not hasattr(order_property, "columns"):
            raise ValueError(
                f'Invalid default_order_by path "{order_path}": '
                f"last token must be a mapped column"
            )

        return query.order_by(order_attr)

    @staticmethod
    def _extract_relations_filters(
        raw_filters: dict[str, Any],
        relation: str,
    ) -> dict[str, Any]:
        relations_filters: dict[str, Any] = {}

        for key in list(raw_filters.keys()):
            value = raw_filters[key]
            if value is None:
                continue
            if "_" not in key or not key.startswith(f"{relation}_"):
                continue
            field = key.removeprefix(f"{relation}_").strip()
            if not field:
                continue

            relations_filters[field] = value
            raw_filters.pop(key, None)
        return relations_filters

    @staticmethod
    def _resolve_model_attr(current_model, attr_name: str):
        model_attr = getattr(current_model, attr_name, None)
        model_property = getattr(model_attr, "property", None)
        return model_attr, model_property

    @staticmethod
    def _build_name_predicate(model_attr, model_property, value: Any):
        if not hasattr(model_property, "mapper"):
            return None

        related_model = model_property.mapper.class_
        name_attr = getattr(related_model, "name", None)
        name_property = getattr(name_attr, "property", None)

        if (
            name_attr is None
            or name_property is None
            or not hasattr(name_property, "columns")
        ):
            return None

        if model_property.uselist:
            return model_attr.any(name_attr == value)

        return model_attr.has(name_attr == value)

    def _build_single_token_predicate(self, model_attr, model_property, value: Any):
        if hasattr(model_property, "columns"):
            return model_attr == value

        return self._build_name_predicate(model_attr, model_property, value)

    def _build_nested_predicate(
        self,
        model_attr,
        model_property,
        path_tokens: list[str],
        value: Any,
    ):
        if not hasattr(model_property, "mapper"):
            return None

        related_model = model_property.mapper.class_
        nested_predicate = self._build_relation_predicate(
            related_model,
            path_tokens[1:],
            value,
        )

        if nested_predicate is None:
            return None

        if model_property.uselist:
            return model_attr.any(nested_predicate)

        return model_attr.has(nested_predicate)

    def _build_relation_predicate(
        self, current_model, path_tokens: list[str], value: Any
    ):
        if not path_tokens:
            return None

        model_attr, model_property = self._resolve_model_attr(
            current_model, path_tokens[0]
        )
        if model_attr is None or model_property is None:
            return None

        if len(path_tokens) == 1:
            return self._build_single_token_predicate(model_attr, model_property, value)

        return self._build_nested_predicate(
            model_attr, model_property, path_tokens, value
        )

    def _apply_relations_filters(
        self, query, relations_filters: dict[str, Any], relation: str
    ):
        if not relations_filters:
            return query

        relation_attr = getattr(self.model, relation, None)
        relation_property = getattr(relation_attr, "property", None)

        if relation_attr is None or relation_property is None:
            return query

        if not hasattr(relation_property, "mapper"):
            return query

        relation_model = relation_property.mapper.class_
        valid_columns = set(relation_model.__mapper__.columns.keys())

        predicates = []

        for field, value in relations_filters.items():
            if value is None:
                continue

            predicate = self._build_filter_predicate(
                relation_model=relation_model,
                field=field,
                value=value,
                valid_columns=valid_columns,
            )

            if predicate is not None:
                predicates.append(predicate)

        if not predicates:
            return query

        combined_predicate = and_(*predicates)

        if relation_property.uselist:
            return query.where(relation_attr.any(combined_predicate))

        return query.where(relation_attr.has(combined_predicate))

    def _build_filter_predicate(
        self,
        relation_model,
        field: str,
        value: Any,
        valid_columns: set[str],
    ):
        path_tokens = field.split("__") if "__" in field else [field]
        predicate = self._build_relation_predicate(relation_model, path_tokens, value)

        if predicate is not None:
            return predicate

        if len(path_tokens) == 1:
            plural_path = [f"{path_tokens[0]}s", "name"]
            predicate = self._build_relation_predicate(
                relation_model, plural_path, value
            )
            if predicate is not None:
                return predicate

        if field not in valid_columns:
            return None

        return getattr(relation_model, field) == value

    async def total(self):
        query = select(func.count()).select_from(self.model)
        value = await self.session.scalar(query)
        return int(value or 0)

    async def save(self, entity: ModelT) -> ModelT:
        self.session.add(entity)
        await self.session.commit()
        await self.session.refresh(entity)
        return entity

    async def update(self, entity: ModelT) -> ModelT:
        entity = await self.session.merge(entity)
        await self.session.commit()
        await self.session.refresh(entity)
        return entity

    def _resolve_relation_name(self, raw_filters: dict[str, Any]) -> str | None:
        if not raw_filters:
            return None

        mapper = getattr(self.model, "__mapper__", None)
        if mapper is None:
            return None

        for relation_name in mapper.relationships.keys():
            prefix = f"{relation_name}_"
            if any(key.startswith(prefix) for key in raw_filters):
                return relation_name

        return None

    async def list_all(self, page_filter: Annotated[FilterPage, Query()] = None):
        query = select(self.model)
        relation: str | None = None
        relations_filters: dict[str, Any] = {}

        for option in self.relations:
            query = query.options(option)

        if page_filter is not None:
            raw_filters = self._prepare_raw_filters(page_filter)
            relation = self._resolve_relation_name(raw_filters)
            if relation is not None:
                relations_filters = self._extract_relations_filters(
                    raw_filters, relation
                )
            query = self._apply_main_filters(query, raw_filters)
            if relation is not None:
                query = self._apply_relations_filters(
                    query, relations_filters, relation
                )

        query = self._apply_order_by(query, page_filter)

        if is_paginate(page_filter):
            params = get_limit_offset_params(page_filter)

            if relations_filters:
                count_query = select(func.count()).select_from(
                    query.order_by(None).subquery()
                )
                total = int(await self.session.scalar(count_query) or 0)

                paginated_query = query.limit(params.limit).offset(params.offset)
                for option in self.relations:
                    paginated_query = paginated_query.options(option)

                paginated_result = await self.session.scalars(paginated_query)

                return CustomLimitOffsetPage.create(
                    items=paginated_result.all(),
                    total=total,
                    params=params,
                )

            result_paginate = await paginate(self.session, query, params=params)

            if isinstance(result_paginate, CustomLimitOffsetPage):
                return result_paginate

            total = getattr(result_paginate, "total", None)
            if total is None and hasattr(result_paginate, "meta"):
                total = getattr(result_paginate.meta, "total", None)

            return CustomLimitOffsetPage.create(
                items=result_paginate.items,
                total=total,
                params=params,
            )
        result = await self.session.scalars(query)
        return result.all()

    @staticmethod
    def _prepare_raw_filters(page_filter: FilterPage) -> dict[str, Any]:
        raw_filters = page_filter.model_dump(exclude_none=True)
        raw_filters.pop("offset", None)
        raw_filters.pop("limit", None)
        raw_filters.pop("page", None)
        raw_filters.pop("order_by", None)
        return raw_filters

    def _apply_main_filters(self, query, raw_filters: dict[str, Any]):
        valid_columns = set(self.model.__mapper__.columns.keys())
        filters = {
            key: value
            for key, value in raw_filters.items()
            if key in valid_columns and value is not None
        }

        if not filters:
            return query

        conditions = [
            getattr(self.model, key) == value for key, value in filters.items()
        ]
        return query.where(*conditions)

    async def find_by(self, **kwargs) -> ModelT | None:
        query = select(self.model)

        has_special_filter = False
        for relation_name in self.model.__mapper__.relationships.keys():
            for key in list(kwargs.keys()):
                if not key.startswith(f"{relation_name}_"):
                    continue

                field = key.removeprefix(f"{relation_name}_").strip()
                if not field:
                    continue

                value = kwargs.pop(key, None)
                if value is None:
                    continue

                predicate = self._build_relation_predicate(
                    self.model, [relation_name, field], value
                )
                if predicate is not None:
                    query = query.where(predicate)
                    has_special_filter = True

        valid_columns = set(self.model.__mapper__.columns.keys())
        original_kwargs = kwargs.copy()
        filters = {
            k: v for k, v in kwargs.items() if k in valid_columns and v is not None
        }

        if not filters and not has_special_filter:
            return None

        ignored_filters = {
            k: v
            for k, v in original_kwargs.items()
            if k not in valid_columns and v is not None
        }
        if ignored_filters:
            return None

        for option in self.relations:
            query = query.options(option)

        if filters:
            query = query.filter_by(**filters)

        return await self.session.scalar(query)
