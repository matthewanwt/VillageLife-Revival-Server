"""Repeatable synthetic 10 MB save / 50-read RPC benchmark, with a release budget."""
import argparse
import json
from pathlib import Path
import statistics
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tests')]
from test_original_client import fake_tables
from villagelife.persistence.sqlite_store import SqliteSaveRepository
from villagelife.protocol.original_client.catalog import OriginalDefinitions
from villagelife.protocol.original_client.services import OriginalClientGame
from villagelife.support import begin_diagnostic_run


def benchmark(samples=7):
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        fake_tables(root / 'tables.sqlite3')
        repo = SqliteSaveRepository(root / 'worlds.sqlite3')
        game = OriginalClientGame(repo, OriginalDefinitions(root / 'tables.sqlite3'))
        profile = game.login({'deviceId': 'invented-performance-fixture'})['data']['users'][0]
        identity = game.sessions.authenticate(profile)
        def prepare(payload):
            payload['padding'] = 'x' * 10_000_000
            payload['originalSave']['normal'] = {'areaId': 1, 'user': {'maxAreaId': 0},
                'world': {'entities': []}, 'inventory': {}, 'wants': []}
            return {}
        repo.mutate(identity.village_id, operation_key='padding', request={}, change=prepare)
        begin_diagnostic_run(repo)
        request = {key: profile[key] for key in ('deviceId', 'pId', 'sessionId')}
        request['data'] = {'calls': [{'id': str(i), 'service': 'ClientSettingService/GetUserGameSettings',
                                    'data': {}} for i in range(50)]}
        timings = []
        for _ in range(samples):
            started = time.perf_counter()
            reply = game.process(request)
            assert all(row['code'] == 200 for row in reply['data']['calls'])
            timings.append((time.perf_counter() - started) * 1000)
        return {'format': 'VillageLifePerformanceBudgetV1', 'synthetic_payload_bytes': 10_000_000,
            'calls_per_request': 50, 'samples_ms': [round(value, 2) for value in timings],
            'p50_ms': round(statistics.median(timings), 2),
            'p95_ms': round(sorted(timings)[min(len(timings) - 1, int(len(timings) * .95))], 2)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--max-ms', type=float, default=1500)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = benchmark()
    result['budget_ms'] = args.max_ms
    result['passed'] = result['p95_ms'] <= args.max_ms
    if args.output:
        args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['passed'] else 2)
