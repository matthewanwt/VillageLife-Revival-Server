"""Original shelter removal; no eviction, currency changes or invented refunds."""
from __future__ import annotations

SERVICE = 'ClientUserShelterService/DeleteUserShelter'


def validate_shelter_removal(state, data, definitions, *, require_empty=True):
    ident = data.get('userShelterId')
    if not isinstance(ident, str) or not ident or len(ident) > 240:
        raise ValueError('Shelter identifier required')
    deleted = state.get('deletedShelters', [])
    if not isinstance(deleted, list) or any(not isinstance(value, str) for value in deleted):
        raise ValueError('Unknown shelter removal history')
    entities = state['world']['entities']
    matches = [e for e in entities if e.get('id') == ident]
    if not matches:
        if ident in deleted:
            return None
        raise ValueError('Unknown shelter')
    if len(matches) != 1 or matches[0].get('templateType') != 'shelter' or ident in deleted:
        raise ValueError('Ambiguous shelter identity')
    home = matches[0]
    template = home.get('templateId')
    if type(template) is not int:
        raise ValueError('Unknown shelter template')
    # Script_2722_canDeleteWObject: shelter type5 rejects template19 and
    # otherwise permits deletion only when the authored immovable field is0.
    definition = definitions.item('shelter', template)
    if template == 19 or str(definition.get('immovable')) != '0':
        raise ValueError('This shelter cannot be removed')
    position = home.get('position')
    if not isinstance(position, dict) or position.get('areaId') != state.get('areaId'):
        raise ValueError('Shelter is in another area')
    beds = home.get('beds', [])
    if not isinstance(beds, list) or any(not isinstance(b, dict) for b in beds):
        raise ValueError('Unknown shelter bed layout')
    ids = [b.get('id') for b in beds]
    if any(not isinstance(value, str) or not value for value in ids) or len(ids) != len(set(ids)):
        raise ValueError('Ambiguous shelter bed identity')
    other_ids = [b.get('id') for e in entities if e is not home and e.get('templateType') == 'shelter' for b in e.get('beds', [])]
    if set(ids).intersection(other_ids):
        raise ValueError('Shelter bed identity is shared with another home')
    if require_empty:
        if any(b.get('villagerId') for b in beds) or any(
                e.get('templateType') == 'villager_type' and e.get('shelterBedId') in set(ids)
                for e in entities):
            raise ValueError('Move residents out before removing this shelter')
    jobs = state.get('workAreas', {})
    if not isinstance(jobs, dict):
        raise ValueError('Unknown active task layout')
    for job in jobs.values():
        if not isinstance(job, dict):
            raise ValueError('Unknown active task record')
        if job.get('status') in {'harvested', 'cancelled'}:
            continue
        snapshot = job.get('sourceSnapshot')
        if snapshot is None:
            snapshot = {}
        elif not isinstance(snapshot, dict):
            raise ValueError('Unknown active task source snapshot')
        if (any(job.get(key) == ident for key in ('sourceId', 'targetId', 'subjectId'))
                or snapshot.get('id') == ident):
            raise ValueError('Shelter is still used by an active task')
    return home


def remove_shelter(state, data, definitions):
    home = validate_shelter_removal(state, data, definitions)
    if home is None:
        return {}, False
    ident = home['id']
    state['world']['entities'] = [e for e in state['world']['entities'] if e is not home]
    state.setdefault('deletedShelters', []).append(ident)
    return {}, True
