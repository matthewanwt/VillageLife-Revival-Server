"""Persistent per-save pseudo-random draws for original-client gameplay.

The seed is created with system entropy once, then SHA-256 counter draws make
later choices reproducible from the save.  Failed/replayed operations retain
their transactional save semantics because the counter lives in the save.
"""
from __future__ import annotations

import hashlib
import secrets


def new_state() -> dict:
    return {'algorithm': 'sha256-counter-v1', 'seed': secrets.token_hex(32), 'counter': 0}


def randbelow(state: dict, stop: int) -> int:
    if isinstance(stop, bool) or not isinstance(stop, int) or stop <= 0:
        raise ValueError('Random range must be a positive integer')
    if not isinstance(state, dict) or state.get('algorithm') != 'sha256-counter-v1':
        raise ValueError('Unsupported saved random generator state')
    try:
        seed = bytes.fromhex(state['seed'])
        counter = state['counter']
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError('Invalid saved random generator state') from exc
    if len(seed) != 32 or isinstance(counter, bool) or not isinstance(counter, int) or counter < 0:
        raise ValueError('Invalid saved random generator state')
    limit = (1 << 256) - ((1 << 256) % stop)
    while True:
        if counter >= 1 << 128:
            raise ValueError('Saved random generator counter exhausted')
        block = hashlib.sha256(seed + counter.to_bytes(16, 'big')).digest()
        counter += 1
        state['counter'] = counter
        value = int.from_bytes(block, 'big')
        if value < limit:
            return value % stop


def choice(state: dict, values: list):
    if not values:
        raise ValueError('Cannot choose from an empty original definition set')
    return values[randbelow(state, len(values))]
