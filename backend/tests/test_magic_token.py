from datetime import timedelta
from uuid import uuid4
import pytest
from fastapi import HTTPException

from app.services.magic_token import generate_magic_token, validate_magic_token


def test_magic_token_roundtrip():
    episode_id = uuid4()
    day = 5
    token = generate_magic_token(episode_id, day)

    assert isinstance(token, str) and len(token) > 20

    data = validate_magic_token(token)
    assert data["episode_id"] == episode_id
    assert data["day"] == 5


def test_magic_token_expired():
    episode_id = uuid4()
    # Expired 1 second ago
    token = generate_magic_token(episode_id, day=3, expires_delta=timedelta(seconds=-1))

    with pytest.raises(HTTPException) as exc:
        validate_magic_token(token)
    assert exc.value.status_code == 401
    assert "expired" in exc.value.detail.lower()


def test_magic_token_tampered():
    episode_id = uuid4()
    token = generate_magic_token(episode_id, day=2)
    # Corrupt token
    tampered = token[:-4] + "xyz1"

    with pytest.raises(HTTPException) as exc:
        validate_magic_token(tampered)
    assert exc.value.status_code == 401
    assert "invalid" in exc.value.detail.lower()


def test_magic_token_empty():
    with pytest.raises(HTTPException) as exc:
        validate_magic_token("")
    assert exc.value.status_code == 401
