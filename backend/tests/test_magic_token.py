from datetime import timedelta
from uuid import uuid4

import pytest

from app.services.magic_token import InvalidCheckInLink, generate_magic_token, validate_magic_token


def test_magic_token_roundtrip():
    episode_id = uuid4()
    token = generate_magic_token(episode_id, 5)

    assert isinstance(token, str) and len(token) > 20
    assert validate_magic_token(token) == {"episode_id": episode_id, "day": 5}


def test_magic_token_expired():
    token = generate_magic_token(uuid4(), day=3, expires_delta=timedelta(seconds=-1))

    with pytest.raises(InvalidCheckInLink, match="expired"):
        validate_magic_token(token)


def test_magic_token_tampered():
    token = generate_magic_token(uuid4(), day=2)

    with pytest.raises(InvalidCheckInLink, match="Invalid"):
        validate_magic_token(token[:-4] + "xyz1")


def test_magic_token_empty():
    with pytest.raises(InvalidCheckInLink, match="missing"):
        validate_magic_token("")
