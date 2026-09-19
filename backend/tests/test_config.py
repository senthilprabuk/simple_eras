import pytest
from pydantic import ValidationError

from app.core.config import Settings


@pytest.mark.parametrize("secret", [
    "too-short",
    "change-this-to-a-secure-random-32-byte-secret-key-in-production",
])
def test_weak_or_placeholder_jwt_secret_refuses_to_start(secret):
    with pytest.raises(ValidationError):
        Settings(DATABASE_URL="postgresql://u:p@localhost/db", JWT_SECRET_KEY=secret)


def test_strong_jwt_secret_is_accepted():
    s = Settings(DATABASE_URL="postgresql://u:p@localhost/db", JWT_SECRET_KEY="a" * 64)
    assert s.JWT_SECRET_KEY == "a" * 64
