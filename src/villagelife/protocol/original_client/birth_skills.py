"""Newborn shield selection using the original charm preview rules."""
from __future__ import annotations

from collections import Counter
import hashlib
import json

PROFESSION = 0
MATERNAL = 1
PATERNAL = 2


def skill_type(row):
    return int(row.get('skilltypeId', row.get('skillTypeId', row.get('type', 0))))


def authored_adult_shields(defs, seed, max_rank):
    """Adult charm slots: father, mother, profession, then additional ranks."""
    valid = {int(row['id']) for row in defs.rows('villager_skill') if int(row['id']) > 0}
    skills, counts = [], Counter()
    for slot, raw in enumerate(seed.get('skills', '').split(',')):
        if not raw.strip().isdecimal():
            continue
        ident = int(raw)
        if ident not in valid or counts[ident] >= max_rank:
            continue
        skills.append({'skilltypeId': ident,
                       'skillOriginType': (PATERNAL, MATERNAL, PROFESSION)[slot] if slot < 3 else PROFESSION})
        counts[ident] += 1
    return skills


def restore_birth_shields(defs, state, max_rank):
    """Recover missing inherited ranks only from a recorded, completed birth."""
    people = {p['id']: p for p in state.get('world', {}).get('entities', [])
              if p.get('templateType') == 'villager_type'}
    changed = False
    for record in state.get('pregnancies', {}).values():
        if record.get('status') != 'born' or not record.get('inheritedSkills'):
            continue
        for ident in record.get('bornChildren', []):
            person = people.get(ident)
            if person is None:
                continue
            skills = person.setdefault('skills', [])
            counts = Counter(map(skill_type, skills))
            for shield in record['inheritedSkills']:
                kind = skill_type(shield)
                origin = int(shield.get('skillOriginType', -1))
                if origin not in (MATERNAL, PATERNAL) or kind <= 0:
                    continue
                try:
                    defs.item('villager_skill', kind)
                except KeyError:
                    continue
                if any(skill_type(row) == kind and int(row.get('skillOriginType', -1)) == origin for row in skills):
                    continue
                if counts[kind] < max_rank:
                    skills.append({'skilltypeId': kind, 'skillOriginType': origin})
                    counts[kind] += 1
                    changed = True
    return changed


def restore_starter_shields(defs, state, max_rank=3):
    """Restore the two inherited/one adult slots for proven ordinary starters.

    The table contains no original skill distribution. Missing ancestral ranks
    use a stable, uniform restoration fallback; existing choices are preserved.
    No parent identities or family-tree connections are invented.
    """
    available = sorted(int(row['id']) for row in defs.rows('villager_skill')
                       if int(row['id']) > 0 and str(row.get('area')) == '1')
    if not available:
        return False
    refs = {json.loads(row['dataJSON'])['refId'] for row in defs.rows('seq_state_tablet_ftue')
            if row.get('sequenceType') == '62'}
    seeds = {int(row['id']): row for row in defs.rows('villager_starting_variation')}
    people = {p['id']: p for p in state.get('world', {}).get('entities', [])
              if p.get('templateType') == 'villager_type'}
    proven = []
    for person in people.values():
        seed = seeds.get(person.get('villagerBaseId'))
        if (not seed or seed.get('refId') not in refs or person.get('refId') != seed.get('refId')
                or seed.get('SpecialType', '0') != '0' or 'collectionBaseId' in person):
            continue
        if not ((seed.get('equipment') and person.get('equipment') == seed['equipment'])
                or (seed.get('genetics') and person.get('genetics') == seed['genetics'])):
            continue
        proven.append((person, float(seed['startAge']) >= 13))
    changed = False
    # Initial adults first, so their existing/restored professions can become
    # the infants' real maternal and paternal ranks.
    for person, adult in sorted(proven, key=lambda pair: not pair[1]):
        skills = person.get('skills', [])
        counts = Counter(map(skill_type, skills))
        for origin in ((PATERNAL, MATERNAL, PROFESSION) if adult else (PATERNAL, MATERNAL)):
            if any(int(row.get('skillOriginType', -1)) == origin for row in skills):
                continue
            kind = None
            if not adult and origin in (MATERNAL, PATERNAL):
                parents = [people.get(relation.get('villagerId')) for relation in person.get('relations', [])
                           if int(relation.get('type', -1)) == 0]
                parent = next((p for p in parents if p is not None
                               and p.get('gender') == (1 if origin == MATERNAL else 0)), None)
                if parent is not None:
                    kind = next((skill_type(row) for row in parent.get('skills', [])
                                 if int(row.get('skillOriginType', -1)) == PROFESSION), None)
            if kind not in available:
                digest = hashlib.sha256(f'{person["id"]}:starter-shield:{origin}'.encode()).digest()
                kind = available[int.from_bytes(digest[:8], 'big') % len(available)]
            if counts[kind] >= max_rank:
                continue
            skills.append({'skilltypeId': kind, 'skillOriginType': origin})
            counts[kind] += 1
            person['skills'] = skills
            changed = True
    if changed:
        state.setdefault('rules', {})['starter_skills'] = {
            'status':'restoration fallback; original random distribution unverified',
            'selection':'stable uniform Woodland skills; retain existing choices and known parental professions'}
    return changed


def parent_shields(defs, mother, father):
    shields = []
    # RuneReviewSkills reads the first profession shield from each parent.
    # Inherited and purchased ranks cannot become the parent's profession.
    for parent, source in ((father, PATERNAL), (mother, MATERNAL)):
        for row in parent.get('skills', []):
            if int(row.get('skillOriginType', -1)) != PROFESSION:
                continue
            ident = skill_type(row)
            if ident > 0:
                try:
                    defs.item('villager_skill', ident)
                except KeyError:
                    continue
                shields.append({'skilltypeId': ident, 'skillOriginType': source})
                break
    return shields


def newborn_shields(defs, inherited, charm, max_rank):
    if charm is None:
        return [dict(row) for row in inherited]
    valid = {int(row['id']) for row in defs.rows('villager_skill') if int(row['id']) > 0}
    skills = []
    counts = Counter()
    # The first three authored slots are the default parents and profession
    # used by adult charms. The baby reveal reads the additional slots.
    for raw in charm.get('skills', '').split(',')[3:]:
        raw = raw.strip()
        if not raw.isdecimal():
            continue
        ident = int(raw)
        if ident in valid and counts[ident] < max_rank:
            skills.append({'skilltypeId': ident, 'skillOriginType': PROFESSION})
            counts[ident] += 1
    for shield in inherited:
        ident = skill_type(shield)
        matching = next((row for row in skills if row['skilltypeId'] == ident
                         and row['skillOriginType'] == PROFESSION), None)
        if matching is not None:
            # The preview colours an existing matching shield first. This
            # keeps an authored mastery within its three-rank limit.
            matching['skillOriginType'] = shield['skillOriginType']
        elif counts[ident] < max_rank:
            skills.append(dict(shield))
            counts[ident] += 1
    return skills

