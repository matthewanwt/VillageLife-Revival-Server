"""Original villager collection read and acknowledgement contracts."""
from __future__ import annotations

import json

COLLECT = 'ClientVillagerService/CollectVillager'


def collect_villager(state: dict, data: dict) -> dict:
    ident = data.get('VillagerBaseId')
    if type(ident) is not int or ident < 0:
        raise ValueError('Integer villager base identifier required')
    collection = state.get('villagerCollection')
    if not isinstance(collection, dict) or str(ident) not in collection:
        raise ValueError('Villager has not been awarded to this collection')
    status = collection[str(ident)]
    if type(status) is not int or status not in (1, 2, 3):
        raise ValueError('Villager is not awaiting collection')
    # The native collection model transitions awarded states 1/2 to 3.
    # This acknowledges a reveal; it does not award another villager or currency.
    if status != 3:
        collection[str(ident)] = 3
    return {}


def read_collection(state: dict) -> dict:
    collection = dict(state.get('villagerCollection', {}))
    try:
        villagers = [int(key) for key in collection]
    except (TypeError, ValueError) as exc:
        raise ValueError('Saved villager collection contains an invalid identifier') from exc
    return {'VillagerCollection': json.dumps(collection, separators=(',', ':')),
            'villagers': villagers}
