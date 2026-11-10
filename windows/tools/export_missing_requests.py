"""Produce a privacy-minimised missing-RPC report for maintainers.

Read only the recorder's allowlisted metadata. Never include HTTP headers, raw
request parameters, save files or the backend's ordinary private request log.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ROUTE_PATTERN = re.compile(r'^(?:/(?:web/ClientService/(?:Login|Process)|Playdemic\.Community\.Web/Client/Home|health)|unrecognised-route-sha256-[0-9a-f]{16})$')
OP_PATTERN = re.compile(r'^(?:[A-Za-z][A-Za-z0-9_.]{0,63}/[A-Za-z][A-Za-z0-9_.]{0,63}|unrecognised-operation-sha256-[0-9a-f]{16})$')
CATEGORIES = {'not_implemented', 'known_rule_gap', 'server_failure'}


def _safe_entry(row):
    if not isinstance(row, dict) or row.get('format') != 'VillageLifeMissingRequestV1':
        return None
    method, route, op = row.get('method'), row.get('route'), row.get('operation')
    category, status = row.get('category'), row.get('status')
    if method not in ('GET', 'POST') or not isinstance(route, str) or not ROUTE_PATTERN.fullmatch(route):
        return None
    if op is not None and (not isinstance(op, str) or not OP_PATTERN.fullmatch(op)):
        return None
    if category not in CATEGORIES or type(status) is not int or status not in (400, 404, 500, 501, 502, 503):
        return None
    n = row.get('observed_this_session', 1)
    n = n if type(n) is int and 1 <= n <= 2_000_000 else 1
    return {'method': method, 'route': route, 'operation': op, 'status': status,
            'category': category, 'observed_this_session': n}


def build_summary(path: Path) -> dict:
    grouped = defaultdict(lambda: {'samples': 0, 'max_session_observations': 0})
    rejected = 0
    if path.exists():
        # Only the most recent bounded recorder file is exported. Historical
        # rotation files remain local unless manually reviewed by a maintainer.
        with path.open('rb') as src:
            for line in src:
                if len(line) > 3000:
                    rejected += 1
                    continue
                try:
                    event = _safe_entry(json.loads(line.decode('utf-8')))
                except (ValueError, UnicodeError):
                    event = None
                if event is None:
                    rejected += 1
                    continue
                key = (event['method'], event['route'], event['operation'], event['status'], event['category'])
                grouped[key]['samples'] += 1
                grouped[key]['max_session_observations'] = max(grouped[key]['max_session_observations'], event['observed_this_session'])
    entries = [dict(method=k[0], route=k[1], operation=k[2], status=k[3], category=k[4], **v)
               for k, v in sorted(grouped.items(), key=lambda pair: str(pair[0]))]
    return {
        'format': 'VillageLifeMissingRequestSummaryV1',
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'entries': entries, 'rejected_entries': rejected,
        'contains_raw_game_requests': False, 'contains_save_data': False,
        'count_warning': 'Samples are throttled snapshots, not an exact number of received calls.',
    }


def export_missing(root=ROOT, *, output_dir=None) -> Path:
    root = Path(root)
    source = root / 'backend' / 'private_state' / 'diagnostics' / 'missing_requests.jsonl'
    destination = Path(output_dir) if output_dir is not None else root / 'support'
    destination.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    package = destination / f'VillageLife-MissingRequests-{stamp}.zip'
    report = build_summary(source)
    with zipfile.ZipFile(package, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('missing-requests-summary.json', json.dumps(report, indent=2, ensure_ascii=False))
        archive.writestr('README.txt',
            'Village Life missing-service report. No raw requests, save data, headers, device IDs or IPs are included.\n'
            'Please inspect missing-requests-summary.json before sharing. Send to a trusted maintainer, not a public channel.\n'
            'An empty list means no missing calls were recorded in this installation, not that the game is complete.\n')
    return package


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    output = export_missing(args.root)
    print('Missing-request report saved: ' + str(output), flush=True)
    print('Review the ZIP and share it privately with a developer. Saves and raw request bodies are excluded.', flush=True)


if __name__ == '__main__':
    main()
