"""Original villager identity and naming actions."""
from __future__ import annotations


class OriginalVillagerRules:
    @staticmethod
    def set_name(state: dict, data: dict) -> tuple[str, str]:
        ident = data.get('villagerId')
        if not isinstance(ident, str) or not ident:
            raise ValueError('Villager identifier required')
        actor = next((entity for entity in state.get('world', {}).get('entities', [])
                      if entity.get('id') == ident and entity.get('templateType') == 'villager_type'), None)
        if actor is None:
            raise ValueError('Unknown villager in this village')
        name = data.get('name')
        if (not isinstance(name, str) or not name.strip() or len(name.strip().encode('utf-8')) > 64
                or any(ord(char) < 32 for char in name)):
            raise ValueError('Invalid villager name')
        return ident, name.strip()
