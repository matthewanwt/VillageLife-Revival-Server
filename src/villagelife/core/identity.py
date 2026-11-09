"""Stable identities are separate: account != village != device != villager."""
import uuid


def new_id() -> str:
    return str(uuid.uuid4())


def pair_ids(a: str, b: str) -> tuple[str, str]:
    if not a or not b or a == b:
        raise ValueError('Two different non-empty account identities required')
    return (a, b) if a < b else (b, a)
