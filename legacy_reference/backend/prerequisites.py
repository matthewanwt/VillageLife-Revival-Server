"""Non-consumed original requirement quantities; never grants or spends stock."""
from decimal import Decimal
from functools import lru_cache
import world


@lru_cache(maxsize=1)
def building_ancestors():
    """Original parent chains, indexed by completed world template (not stock)."""
    result = {}
    foundations = {r['id']: r for r in world.rows('building_task')}
    for foundation in foundations.values():
        building = world.by_id('building_type', foundation['buildingType'])
        materials = result.setdefault((building['entityRef'], int(building['entityID'])), set())
        current = foundation
        visited = set()
        while current['id'] not in visited:
            visited.add(current['id'])
            materials.add(world.by_id('building_type', current['buildingType'])['materialType'])
            if current['parentId'] == '-1':
                break
            current = foundations[current['parentId']]
    return {key: frozenset(value) for key, value in result.items()}


def milestones(state):
    """Non-stockable construction/area milestones for the native inventory UI."""
    found = set()
    for entity in state.get('world', {}).get('entities', []):
        if entity.get('localCreated') or entity.get('sourceWorkAreaId'):
            found.update(building_ancestors().get((entity['templateType'], entity['templateId']), ()))
    maximum = int(state.get('user', {}).get('maxAreaId', state.get('areaId', 0)))
    found.update(material for material, area in [('231', 1), ('232', 2), ('1536', 3)] if maximum >= area)
    return found


@lru_cache(maxsize=1)
def building_materials():
    return frozenset(material for values in building_ancestors().values() for material in values)


def quantity(state, material):
    # Script2440 explicitly handles material7 using the +0x3884 XP field,
    # which Script3734_SetXP writes. It is not an inventory stock item.
    if str(material) == '7':
        return Decimal(str(state['user'].get('xp', 0)))
    value = Decimal(str(state['inventory'].get(str(material), 0)))
    area_markers = {'231': 1, '232': 2, '1536': 3}
    if str(material) in area_markers and int(state['user'].get('maxAreaId', state.get('areaId', 0))) >= area_markers[str(material)]:
        value = max(value, Decimal(1))
    if str(material) == '130' and state.get('transitionKey') == 'bridge-1-to-2' and state.get('scenarioId') == 2:
        value = max(value, Decimal(1))
    if value >= 1 or str(material) not in building_materials():
        return value
    # Storage/workshop upgrade gates list several earlier tiers at once. They
    # remain milestones after replacement; do not manufacture spendable stock.
    for entity in state.get('world', {}).get('entities', []):
        if not entity.get('localCreated') and not entity.get('sourceWorkAreaId'):
            continue  # Authored placeholders do not establish construction.
        if str(material) in building_ancestors().get((entity['templateType'], entity['templateId']), ()):
            value = max(value, Decimal(1))
    return value
