"""Explicit, replay-safe offline repairs on an updater's staged save copy only."""
import argparse
import copy
import hashlib
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
import world
import fun
import habitats
import collection
import progression
import session
import native_identity

MIGRATION = 'community-save-1'


def load_json(path):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError('Duplicate JSON key')
            value[key] = item
        return value
    def invalid(value):
        raise ValueError('Non-finite JSON number')
    return json.loads(Path(path).read_text(encoding='utf-8-sig'),
                      object_pairs_hook=pairs, parse_constant=invalid)


def migrate_document(saved, owner):
    candidate = copy.deepcopy(saved)
    if not isinstance(candidate, dict):
        raise ValueError('Save must be an object')
    if candidate.get('schemaVersion', 1) not in {1, 2, 3, 4} or candidate.get('version', 1) not in {1, 2, 3}:
        raise ValueError('Unsupported save version; a newer updater may be needed')
    repairs = []
    people = candidate['userHash']['data']['villagers']
    for person in people:
        if not person.get('id'):
            if not person.get('refId'):
                raise ValueError('Cannot recover a tutorial character identity')
            person['id'] = person['refId']
            repairs.append('Recovered tutorial identity from its saved reference')
    session.validate_character_ids(people)
    state = candidate.get('normal')
    if state is not None:
        if state.get('schemaVersion', 1) not in {1, 2, 3}:
            raise ValueError('Unsupported world version')
        # The historic area migration also clamps starter ages. An upgrade must
        # retain the player's actual lifecycle/energy, including aged starters.
        actors = {v['id']: copy.deepcopy(v) for v in state['world']['entities']
                  if v['templateType'] == 'villager_type'}
        if world.migrate_level_numbers(state):
            repairs.append('Upgraded legacy level numbering')
        if world.migrate_authored_area(state):
            for person in state['world']['entities']:
                if person['id'] in actors:
                    person.update(actors[person['id']])
            repairs.append('Upgraded authored world records; retained character ages and identities')
        if fun.migrate(state):
            repairs.append('Initialized missing original fun counters; retained exhausted counters')
        if world.repair_starter_family(state):
            repairs.append('Removed unsupported starter-parent links; retained tutorial twins and later births')
        if collection.migrate_skills(state):
            repairs.append('Restored missing authored charm skill levels; retained existing skills')
        if habitats.migrate(state,0):
            repairs.append('Added missing shelter places; retained existing beds, occupants and happiness timers')
        if progression.reconcile_level_rewards(state):
            repairs.append('Reconciled rewards supported by saved level receipts')
        if native_identity.reserve_ids(state, owner):
            repairs.append('Reserved stable native character identities')
        world.validate_world(state)
        # validate_world covers structural relations, work and inventory. Check
        # timestamps too: the updater must never silently reset ageing.
        for person in state['world']['entities']:
            if person['templateType'] == 'villager_type':
                for key in ('bornAt', 'startAge'):
                    number = person[key]
                    if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number) or number < 0:
                        raise ValueError('Invalid saved character age or birth timestamp')
    history = candidate.setdefault('updateMigrations', [])
    if not isinstance(history, list) or any(not isinstance(v, str) for v in history):
        raise ValueError('Invalid migration history')
    if MIGRATION not in history:
        history.append(MIGRATION)
    return candidate, repairs


def migrate_directory(state_dir):
    state_dir = Path(state_dir)
    plans = []
    profiles = {}
    for path in sorted(state_dir.glob('*.json')):
        if path.name.endswith('.tutorial.json'):
            continue
        value = load_json(path)
        # Profile files use the SHA256 of the original local device identity.
        if len(path.stem) == 64:
            device = value.get('deviceId')
            if not isinstance(device, str) or hashlib.sha256(device.encode()).hexdigest() != path.stem or not value.get('pId'):
                raise ValueError('Profile identity does not match its save filename')
            profiles[path.stem] = value
    for path in sorted(state_dir.glob('*.tutorial.json')):
        ident = path.name.removesuffix('.tutorial.json')
        if ident not in profiles:
            raise ValueError('Save has no matching player profile')
        before = load_json(path)
        after, repairs = migrate_document(before, str(profiles[ident]['pId']))
        again, repeated = migrate_document(after, str(profiles[ident]['pId']))
        if again != after or repeated:
            raise ValueError('Save repair is not replay-safe')
        plans.append((path, before, after, repairs))
    # Validate every player before writing any staged save. The caller owns the
    # private staging directory; the installed player folder is never passed in.
    for path, before, after, repairs in plans:
        if before != after:
            session.atomic_json(path, after)
    return {'profiles': len(profiles), 'villages': len(plans),
            'changed_villages': sum(before != after for _, before, after, _ in plans),
            'repairs': [repair for _, _, _, repairs in plans for repair in repairs],
            'unrecoverable': ['Unrecorded past sales or spending cannot be reconstructed.'],
            'validation': 'All villages validated; second migration made no changes'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--database', type=Path, help='Read-only original tables for standalone disposable validation')
    args = parser.parse_args()
    if args.database:
        database = args.database.resolve(strict=True)
        world.DATABASE = database
        session.DATABASE = database
    result = migrate_directory(args.state)
    session.atomic_json(args.report, result)
    print('Save migration and validation passed.')


if __name__ == '__main__':
    main()
