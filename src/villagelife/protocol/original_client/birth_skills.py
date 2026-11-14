"""Newborn shield selection using the original charm preview rules."""
from __future__ import annotations

from collections import Counter

PROFESSION = 0
MATERNAL = 1
PATERNAL = 2


def skill_type(row):
    return int(row.get('skilltypeId', row.get('skillTypeId', row.get('type', 0))))


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

