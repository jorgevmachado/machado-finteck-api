from http import HTTPStatus
from typing import Annotated, Any, cast

from fastapi import HTTPException, Query
from pydantic import BaseModel

from app.core.cache.service import CacheService
from app.core.exceptions import handle_service_exception
from app.core.logging import LoggingParams, log_service_success
from app.core.pagination.pagination import exception_pagination
from app.models import utcnow
from app.shared.schemas import FilterPage, Message
from app.shared.utils.string import is_valid_uuid, to_snake_case


class BaseService[
    RepositoryT,
    ModelT,
    SchemaT: BaseModel = BaseModel,
    UpdateSchemaT: BaseModel = BaseModel,
]:
    def __init__(
        self,
        alias: str,
        repository: RepositoryT,
        logger_params: LoggingParams,
        schema_class: type[SchemaT],
        cache_prefix: str | None = None,
        parents_alias: list[str] | None = None,
    ):
        prefix = cache_prefix or alias.replace(" ", "_").lower()
        self.alias = alias
        self.repository = repository
        self.cache_prefix = cache_prefix
        self.parents_alias = parents_alias
        self.logger_params = logger_params
        self.cache_service = CacheService(
            alias=alias,
            prefix=prefix,
            logger_params=logger_params,
            schema_class=schema_class,
        )

    async def list_all(
        self,
        page_filter: Annotated[FilterPage, Query()] = None,
        user_request: str | None = None,
    ):
        try:
            return await self.repository.list_all(page_filter=page_filter)
        except Exception as exception:
            handle_service_exception(
                exception,
                logger=self.logger_params.logger,
                service=self.logger_params.service,
                operation="list_all",
                user_request=user_request,
                raise_exception=False,
            )
            return exception_pagination(page_filter)
        finally:
            log_service_success(
                self.logger_params,
                operation="list_all",
                message="List all successfully",
                user_request=user_request,
            )

    async def list_all_cached(
        self,
        page_filter: Annotated[FilterPage, Query()] = None,
        user_request: str | None = None,
        **kwargs,
    ):
        clean_cache = page_filter.clean_cache if page_filter else False
        if clean_cache:
            await self.cache_service.delete_domain()
        if page_filter:
            page_filter.clean_cache = None
        key = self.cache_service.build_key_list(page_filter=page_filter)
        cached = await self.cache_service.get_list(key)
        if cached:
            return cached
        result = await self.list_all(page_filter=page_filter, user_request=user_request)

        await self.cache_service.set_list(key, result)

        return result

    async def find_one(
        self,
        param: str,
        **kwargs,
    ):
        finance_id = kwargs.get("finance_id") if kwargs else None
        user_request = kwargs.get("user_request") if kwargs else None
        with_deleted = kwargs.get("with_deleted") if kwargs else False
        reference_year = kwargs.get("reference_year") if kwargs else None
        finance_id = cast(str, finance_id) if finance_id else None
        reference_year = cast(int, reference_year) if reference_year else None
        try:
            find_by_filters: dict[str, str | int] = (
                {"finance_id": finance_id} if finance_id else {}
            )
            if reference_year is not None:
                find_by_filters["reference_year"] = reference_year

            if is_valid_uuid(param):
                result = await self.repository.find_by(
                    id=param, with_deleted=with_deleted, **find_by_filters
                )
            else:
                result = await self.repository.find_by(
                    name=param, with_deleted=with_deleted, **find_by_filters
                )

            if result is None:
                raise HTTPException(
                    status_code=HTTPStatus.NOT_FOUND,
                    detail=f"{self.alias} not found",
                )
            return result
        except Exception as exception:
            handle_service_exception(
                exception,
                logger=self.logger_params.logger,
                service=self.logger_params.service,
                operation="find_one",
                user_request=user_request,
                raise_exception=True,
            )
        finally:
            log_service_success(
                self.logger_params,
                operation="find_one",
                message=f"Find one {self.alias} successfully",
                user_request=user_request,
            )

    async def _invalidate_cache(
        self, identifier: str | None = None, finance_id: str | None = None
    ) -> None:
        try:
            await self.cache_service.delete_with_parent_cache(self.parents_alias)
            if identifier:
                cache_key = identifier
                if finance_id:
                    cache_key = f"{finance_id}:{identifier}"
                await self.cache_service.cache.delete_cache(cache_key)
        except Exception:
            self.logger_params.logger.warning(
                "Cache invalidation skipped for %s due to an infrastructure error.",
                self.alias,
                exc_info=True,
            )

    async def find_one_cached(
        self,
        param: str,
        **kwargs,
    ):
        cache_key = param
        finance_id = kwargs.get("finance_id") if kwargs else None
        finance_id = cast(str, finance_id) if finance_id else None
        if finance_id:
            cache_key = f"{finance_id}:{param}"

        reference_year = kwargs.get("reference_year") if kwargs else None
        reference_year = cast(int, reference_year) if reference_year else None
        if reference_year:
            cache_key = f"{cache_key}:{reference_year}"
        key = self.cache_service.build_key_one(param=cache_key)
        clean_cache = kwargs.get("clean_cache") if kwargs else False

        if clean_cache:
            await self.cache_service.cache.delete_cache(key)
        cached = await self.cache_service.get_one(key)
        if cached:
            return cached
        item = await self.find_one(param, **kwargs)
        await self.cache_service.set_one(key, item)
        return item

    async def find_by(self, **kwargs):
        user_request = kwargs.get("user_request", None)
        without_throw = kwargs.get("without_throw", False)
        kwargs.pop("without_throw", None)
        try:
            result = await self.repository.find_by(**kwargs)
            if result is None and not without_throw:
                raise HTTPException(
                    status_code=HTTPStatus.NOT_FOUND,
                    detail=f"{self.alias} not found",
                )
            return result
        except Exception as exception:
            handle_service_exception(
                exception,
                logger=self.logger_params.logger,
                service=self.logger_params.service,
                operation="find_by",
                user_request=user_request,
            )
        finally:
            log_service_success(
                self.logger_params,
                operation="find_by",
                message=f"Find by {self.alias} successfully",
                user_request=user_request,
            )

    async def update(
        self, param: str, update_schema: UpdateSchemaT, **kwargs
    ) -> ModelT:
        user_request = kwargs.get("user_request", None)
        finance_id = kwargs.get("finance_id") if kwargs else None
        finance_id = cast(str, finance_id) if finance_id else None
        kwargs.pop("finance_id", None)
        try:
            entity = await self.find_one(param, user_request=user_request)
            if entity is None:
                raise HTTPException(
                    status_code=HTTPStatus.NOT_FOUND,
                    detail=f"{self.alias} not found",
                )
            update_data = update_schema.model_dump(exclude_unset=True)
            self._sync_code_fields(update_schema, entity, update_data)
            for key, value in update_data.items():
                if isinstance(entity, dict):
                    entity[key] = value
                else:
                    setattr(entity, key, value)
            await self._invalidate_cache(identifier=param, finance_id=finance_id)
            return await self.repository.update(entity)
        except Exception as exception:
            handle_service_exception(
                exception,
                logger=self.logger_params.logger,
                service=self.logger_params.service,
                operation="update",
                user_request=user_request,
                raise_exception=True,
            )
        finally:
            log_service_success(
                self.logger_params,
                operation="update",
                message=f"Update {self.alias} successfully",
                user_request=user_request,
            )

    @staticmethod
    def _sync_code_fields(
        update_schema: BaseModel,
        entity: ModelT,
        update_data: dict[str, Any],
    ) -> None:
        schema_fields = getattr(type(update_schema), "model_fields", {})
        field_pairs = (("name", "name_code"), ("source", "source_code"))

        for source_field, code_field in field_pairs:
            if code_field not in schema_fields or source_field not in update_data:
                continue

            updated_value = update_data[source_field]
            if not isinstance(updated_value, str):
                continue

            current_value = (
                entity.get(source_field)
                if isinstance(entity, dict)
                else getattr(entity, source_field, None)
            )
            if updated_value != current_value:
                update_data[code_field] = to_snake_case(updated_value)

    async def update_entity(
        self,
        entity: ModelT,
        user_request: str | None = None,
    ) -> ModelT:
        try:
            updated = await self.repository.update(entity=entity)
            await self.cache_service.delete_with_parent_cache(self.parents_alias)
            return updated
        except Exception as exception:
            handle_service_exception(
                exception,
                logger=self.logger_params.logger,
                service=self.logger_params.service,
                operation="update",
                user_request=user_request,
                raise_exception=True,
            )
        finally:
            log_service_success(
                self.logger_params,
                operation="update",
                message=f"Update Entity {self.alias} successfully",
                user_request=user_request,
            )

    async def soft_delete(self, param: str, **kwargs) -> Message:
        user_request = kwargs.get("user_request") if kwargs else None
        finance_id = kwargs.get("finance_id") if kwargs else None
        finance_id = cast(str, finance_id) if finance_id else None
        kwargs.pop("finance_id", None)
        successfully_message = f"Deleted {self.alias} successfully"
        try:
            entity = await self.find_one(param=param, finance_id=finance_id, **kwargs)
            if entity is None:
                raise HTTPException(
                    status_code=HTTPStatus.NOT_FOUND,
                    detail=f"{self.alias} not found",
                )
            await self._invalidate_cache(identifier=param, finance_id=finance_id)
            entity.deleted_at = utcnow()
            await self.repository.update(entity)
            return Message(message=successfully_message)
        except Exception as exception:
            handle_service_exception(
                exception,
                logger=self.logger_params.logger,
                service=self.logger_params.service,
                operation="soft_delete",
                user_request=user_request,
                raise_exception=True,
            )
        finally:
            log_service_success(
                self.logger_params,
                operation="soft_delete",
                message=successfully_message,
                user_request=user_request,
            )
