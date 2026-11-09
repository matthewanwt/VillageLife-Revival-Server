"""Consolidate curated community reports and the complete generated feature audit."""
import argparse
import collections
import csv
import datetime
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def collect(root=ROOT):
    tracker = json.loads((root / 'notes/RESTORATION_TRACKER.json').read_text(encoding='utf-8'))
    items = [dict(item, kind='community_or_release') for item in tracker['items']]
    ids = [item['id'] for item in items]
    if len(ids) != len(set(ids)):
        raise ValueError('Tracker IDs must be unique')
    audit_path = None
    pointer = root / 'analysis/latest-feature-audit.json'
    if pointer.exists():
        audit_path = Path(json.loads(pointer.read_text(encoding='utf-8'))['folder']) / 'coverage.json'
        if not audit_path.resolve().is_relative_to((root / 'analysis').resolve()):
            raise ValueError('Audit pointer must stay within project analysis')
        audit = json.loads(audit_path.read_text(encoding='utf-8'))
        for name, row in audit['methods'].items():
            items.append({'id': 'METHOD:' + name, 'title': name, 'kind': 'original_method',
                          'status': row['status'], 'priority': 2 if row.get('open_observed_error') else 3,
                          'release_blocker': False, 'evidence': ['Generated original method audit'],
                          'next': 'Check original call sites and native journey; historical errors may predate a fix.',
                          'detail': row})
        for kind, key, id_key in [('original_task', 'tasks', 'task_id'), ('original_purchase', 'purchases', 'material_id')]:
            for index, row in enumerate(audit.get(key, [])):
                ident = str(row[id_key])
                items.append({'id': kind.upper() + ':' + ident + ':' + str(index),
                              'title': str(row.get('name', ident)), 'kind': kind, 'status': row['status'],
                              'priority': 3, 'release_blocker': False, 'evidence': ['Generated original-data fixture audit'],
                              'next': row.get('reason') or 'Server fixture only; native progression/placement/rendering unverified.',
                              'detail': row})
        for row in audit.get('unsupported_branches', []):
            items.append({'id': 'BRANCH:' + row['file'] + ':' + str(row['line']),
                          'title': row['function'] + ': ' + row['reason'], 'kind': 'unsupported_branch',
                          'status': 'not_implemented', 'priority': 3, 'release_blocker': False,
                          'evidence': [row['file'] + ':' + str(row['line'])],
                          'next': 'Recover input-class contract and add boundary scenario before implementing.'})
    return {**tracker, 'generated_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'audit_source': str(audit_path) if audit_path else None,
            'counts': dict(collections.Counter(item['status'] for item in items)), 'items': items}


def render(result, out):
    out.mkdir(parents=True, exist_ok=True)
    (out / 'tracker.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    fields = ['id', 'kind', 'title', 'priority', 'status', 'release_blocker', 'next']
    with (out / 'tracker.csv').open('w', encoding='utf-8-sig', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(result['items'])
    rows = []
    for item in result['items']:
        values = [item.get(key, '') for key in fields]
        rows.append('<tr>' + ''.join('<td>' + html.escape(str(value)) + '</td>' for value in values) + '</tr>')
    page = '''<!doctype html><html lang="en"><meta charset="utf-8"><title>Village Life restoration tracker</title>
<style>body{font:15px system-ui;margin:28px;color:#16342d;background:#f4f7f4}h1{margin-bottom:8px}input,select{padding:10px;margin:10px 12px 20px 0}table{border-collapse:collapse;width:100%;background:white}td,th{padding:10px;text-align:left;border-bottom:1px solid #d7e1dc;vertical-align:top}th{position:sticky;top:0;background:#dce9e1}td:last-child{min-width:300px}small{display:block}</style>
<h1>Village Life restoration tracker</h1><p>Community reports, release checks and the original feature inventory in one view.</p>
<p>Server fixture passes do not prove native gameplay. Development fixes are separate from released fixes. Historical source reports remain unchanged.</p>
<input id="search" placeholder="Search reports, features or next actions" size="50"><select id="kind"><option value="">All types</option>'''
    page += ''.join('<option>' + html.escape(kind) + '</option>' for kind in sorted({v['kind'] for v in result['items']}))
    page += '</select><label><input type="checkbox" id="blockers">Release blockers only</label><p id="count"></p><table><thead><tr>'
    page += ''.join('<th>' + html.escape(field.replace('_', ' ').title()) + '</th>' for field in fields)
    page += '</tr></thead><tbody>' + ''.join(rows) + '''</tbody></table><script>
const rows=[...document.querySelectorAll('tbody tr')];
function filter(){let count=0;const q=document.querySelector('#search').value.toLowerCase(),kind=document.querySelector('#kind').value,block=document.querySelector('#blockers').checked;
for(const row of rows){const cells=row.cells;const show=(!q||row.textContent.toLowerCase().includes(q))&&(!kind||cells[1].textContent===kind)&&(!block||cells[5].textContent==='True');row.hidden=!show;if(show)count++;}document.querySelector('#count').textContent=count+' entries shown';}
document.querySelectorAll('input,select').forEach(el=>el.addEventListener('input',filter));filter();</script></html>'''
    (out / 'index.html').write_text(page, encoding='utf-8')
    lines = ['# Village Life current checklist', '',
             'Generated from notes/RESTORATION_TRACKER.json and the latest complete original-data audit.',
             'Historical reports are evidence, not current completion claims. No development fix is assumed shipped.', '',
             '| ID | Priority | Feature/report | Current state | Release blocker | Next action |',
             '|---|---|---|---|---|---|']
    for item in result['items']:
        if item['kind'] == 'community_or_release':
            values = [item[key] for key in ('id', 'priority', 'title', 'status', 'release_blocker', 'next')]
            lines.append('| ' + ' | '.join(str(v).replace('|', '\\|') for v in values) + ' |')
    lines += ['', 'Detailed original methods, tasks, purchases and unsupported branches are in the searchable dashboard and CSV.',
              '', 'Status counts: ' + json.dumps(result['counts'], sort_keys=True)]
    (out / 'CHECKLIST.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--open', action='store_true')
    args = parser.parse_args()
    out = ROOT / 'analysis/restoration-tracker'
    result = collect()
    render(result, out)
    print(json.dumps({'entries': len(result['items']), 'counts': result['counts'], 'dashboard': str(out / 'index.html')}, indent=2))
    if args.open:
        import os
        os.startfile(out / 'index.html')


if __name__ == '__main__':
    main()
