from datetime import datetime, timezone
from uuid import uuid4

from app.models.auth.enums import StatusEnum
from app.models.auth.user import User


def test_user_model_instantiation():
    role_id = uuid4()
    user = User(
        role_id=role_id,
        name="john Doe",
        email="john@doe.com",
        username="johndoe",
        status=StatusEnum.ACTIVE,
        date_of_birth=datetime(1990, 7, 20, tzinfo=timezone.utc),
    )
    assert user.role_id == role_id
    assert user.name == "john Doe"
    assert user.email == "john@doe.com"
    assert user.username == "johndoe"
    assert user.status == StatusEnum.ACTIVE
    assert user.date_of_birth == datetime(1990, 7, 20, tzinfo=timezone.utc)
    assert user.created_at is not None
    assert user.updated_at is None
    assert user.deleted_at is None
