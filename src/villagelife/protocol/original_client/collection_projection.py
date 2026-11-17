"""Wire-only ordinary appearance IDs; collection awards remain canonical."""
from copy import deepcopy

def ordinary_seed(entity, definitions):
    """Recognize only proven ordinary seed records, never guess a rare ID.

    Unknown/imported records are passed through for separate review. Explicit
    collection provenance always wins, including one-star rare newborns whose
    stored rarity is zero. Equipment may be changed later, so either matching
    authored seed equipment or matching nonempty authored genetics is evidence.
    """
    if (entity.get('templateType') != 'villager_type'
            or 'collectionBaseId' in entity
            or type(entity.get('rarity')) is not int or entity['rarity'] != 0
            or type(entity.get('villagerBaseId')) is not int
            or entity['villagerBaseId'] <= 0):
        return False
    try:
        seed = definitions.item('villager_starting_variation', entity['villagerBaseId'])
    except KeyError:
        return False
    same_equipment = (bool(seed.get('equipment'))
                      and entity.get('equipment') == seed['equipment'])
    same_genetics = (bool(seed.get('genetics'))
                    and entity.get('genetics') == seed['genetics'])
    if not (same_equipment or same_genetics):
        return False
    # A legacy rare without explicit provenance can also have rarity zero.
    # If its authored rare appearance matches, the namespaces are ambiguous.
    try:
        rare = definitions.item('gachaVillager', entity['villagerBaseId'])
    except KeyError:
        return True
    if entity.get('equipment') == rare.get('equipment'):
        return False
    return True


def project_entities(entities, definitions, state=None):
    result = deepcopy(entities)
    # AreaRules owns a separate world projector. Its wire entities may omit
    # appearance evidence, so consult only a unique matching saved person.
    people, ambiguous = {}, set()
    if isinstance(state, dict):
        for person in state.get('world', {}).get('entities', []):
            if person.get('templateType') != 'villager_type':
                continue
            ident = person.get('id')
            if ident in people:
                ambiguous.add(ident)
            else:
                people[ident] = person
    for entity in result:
        ident = entity.get('id')
        witness = people.get(ident, entity) if ident not in ambiguous else None
        if (witness is not None
                and witness.get('villagerBaseId') == entity.get('villagerBaseId')
                and ordinary_seed(witness, definitions)):
            # Native index 0 is the unlisted, zero-filled sentinel; authored
            # collection rows start at 1. Never use -1 (unsafe native indexing).
            entity['villagerBaseId'] = 0
    return result
