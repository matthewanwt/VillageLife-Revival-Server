"""Original villager collection read contract."""
from __future__ import annotations

import json


def read_collection(state: dict) -> dict:
    collection = dict(state.get('villagerCollection', {}))
    try:
        villagers = [int(key) for key in collection]
    except (TypeError, ValueError) as exc:
        raise ValueError('Saved villager collection contains an invalid identifier') from exc
    return {'VillagerCollection': json.dumps(collection, separators=(',', ':')),
            'villagers': villagers}
