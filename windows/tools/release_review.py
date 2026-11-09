"""Source-bound regression/optimisation evidence and a fail-closed release gate."""
import argparse
import copy
import datetime
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time
import tracemalloc

ROOT = Path(__file__).resolve().parents[1]


def fingerprint(root=ROOT):
    digest = hashlib.sha256()
    paths = [*(root / 'backend').glob('*.py'), *(root / 'tools').glob('*.py'),
             *(root / 'launcher').glob('*.cs'), *root.glob('*.cmd'), root / 'VERSION.json']
    paths += [p for folder in ('launcher/community-release', 'StartVillageLife')
              for p in (root / folder).glob('*') if p.is_file() and p.suffix in {'.dll', '.exe', '.json'}]
    paths += [root / 'notes/BUILDING_IMPLEMENTATION_SCOPE.json']
    for path in sorted(paths):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def benchmark(root=ROOT):
    sys.path.insert(0, str(root / 'backend'))
    import session
    import world
    import migrate_save
    import cProfile
    import io
    import pstats
    cases = []
    for count in (6, 100, 300):
        for cache in (world.raw_rows, world._parsed_rows, world._id_index, world.global_value, session._fresh_tutorial_json):
            cache.cache_clear()
        start = time.perf_counter()
        saved = session.fresh_tutorial()
        state = world.build_bridge_world(saved, 1000)
        cold_ms = (time.perf_counter() - start) * 1000
        actors = [p for p in state['world']['entities'] if p['templateType'] == 'villager_type']
        while len(actors) < count:
            person = copy.deepcopy(actors[0])
            person.update(id='performance-' + str(len(actors)), refId='', relations=[], shelterBedId='')
            state['world']['entities'].append(person)
            actors.append(person)
        world.validate_world(state)
        before = copy.deepcopy(state)
        measurements = {}
        profile = cProfile.Profile()
        tracemalloc.start()
        profile.enable()
        for name, operation in [('startup', lambda: world.startup(state, 1000)),
                                ('area_content', lambda: world.area_content(state, state['areaId'], 1000)),
                                ('serialize_save', lambda: json.dumps(state, ensure_ascii=False, indent=2)),
                                ('copy_for_mutation', lambda: copy.deepcopy(state))]:
            times = []
            for _ in range(5):
                started = time.perf_counter()
                operation()
                times.append((time.perf_counter() - started) * 1000)
            measurements[name] = {'median_ms': round(statistics.median(times), 3), 'max_ms': round(max(times), 3)}
        profile.disable()
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        if state != before:
            raise AssertionError('Performance review mutated the village')
        saved['normal'] = state
        start = time.perf_counter()
        migrated, _ = migrate_save.migrate_document(saved, 'benchmark-owner')
        migration_ms = (time.perf_counter() - start) * 1000
        if migrate_save.migrate_document(migrated, 'benchmark-owner')[0] != migrated:
            raise AssertionError('Migration replay changed benchmark village')
        output = io.StringIO()
        pstats.Stats(profile, stream=output).sort_stats('cumulative').print_stats(12)
        cases.append({'actors': count, 'entities': len(state['world']['entities']),
                      'synthetic': True, 'cold_seed_ms': round(cold_ms, 3),
                      'measurements_with_profiler': measurements, 'peak_traced_bytes': peak,
                      'save_bytes': len(json.dumps(state, ensure_ascii=False, indent=2).encode()),
                      'migration_ms': round(migration_ms, 3), 'hotspots': output.getvalue()})
    return {'cases': cases, 'limitations': [
        'Synthetic local server workloads; not Android FPS or a representative player balance test.',
        'Warm timings include profiling and allocation-tracing overhead; no universal hardware threshold.',
        'No network, actual disk backup throughput or second-PC measurements are implied.'],
        'manual_review': 'pending'}


def check_release(root=ROOT, *, field_test=False):
    blockers = []
    tracker = json.loads((root / 'notes/RESTORATION_TRACKER.json').read_text(encoding='utf-8'))
    for item in tracker['items']:
        if not field_test and item['release_blocker'] and item['status'] not in {'release_verified', 'released'}:
            blockers.append(item['id'] + ': ' + item['title'])
    path = root / 'analysis/release-review.json'
    review = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    if review.get('source_sha256') != fingerprint(root):
        blockers.append('Regression/optimisation review is missing or stale')
    if not review.get('regression_audit_passed'):
        blockers.append('Fresh complete regression and feature audit required')
    if review.get('optimisation', {}).get('manual_review') != 'accepted':
        blockers.append('Optimisation findings must be reviewed before release')
    return blockers


def assert_release(root=ROOT):
    blockers = check_release(root)
    if blockers:
        raise RuntimeError('Community release is blocked:\n' + '\n'.join(blockers))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args()
    if args.run:
        before = fingerprint()
        # feature_audit runs both complete test suites plus original-data sweeps.
        result = subprocess.run([sys.executable, str(ROOT / 'tools/feature_audit.py')], cwd=ROOT)
        optimisation = benchmark()
        after = fingerprint()
        review = {'generated_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  'source_sha256': after, 'source_unchanged_during_review': before == after,
                  'regression_audit_passed': result.returncode == 0 and before == after,
                  'optimisation': optimisation}
        (ROOT / 'analysis/release-review.json').write_text(json.dumps(review, indent=2), encoding='utf-8')
        print('Regression and performance evidence recorded; manual optimisation review remains required.')
    blockers = check_release()
    print(json.dumps({'release_ready': not blockers, 'blockers': blockers}, indent=2))
    return 1 if blockers else 0


if __name__ == '__main__':
    sys.exit(main())
