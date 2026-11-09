"""Source-bound register for the user's 69 screenshot-confirmed shop entries."""
import collections
import json
from pathlib import Path
from release_review import fingerprint

ROOT = Path(__file__).resolve().parents[1]


def main():
    review = json.loads((ROOT / 'analysis/release-review.json').read_text(encoding='utf-8'))
    if review['source_sha256'] != fingerprint() or not review['regression_audit_passed']:
        raise RuntimeError('A fresh source-stable complete review is required')
    scope = json.loads((ROOT / 'notes/BUILDING_IMPLEMENTATION_SCOPE.json').read_text(encoding='utf-8'))
    audit_pointer = json.loads((ROOT / 'analysis/latest-feature-audit.json').read_text(encoding='utf-8'))
    audit_path = Path(audit_pointer['folder']) / 'coverage.json'
    if not audit_path.resolve().is_relative_to((ROOT / 'analysis').resolve()):
        raise ValueError('Audit must be inside this workspace')
    audit = json.loads(audit_path.read_text(encoding='utf-8'))
    items = []
    for original in scope['items']:
        item = dict(original)
        structure = bool(item['foundation_ids'])
        item.update(automated='passed_server_fixture', native='pending',
                    acquisition='foundation/upgrade: natural and paid completion' if structure else 'craft/paid completion',
                    operation='eligible activity, reward and replay' if item['activity_ids'] else
                        'lighting and burn timer' if item['name'].endswith('Fire') else
                        'water gathering and harvest' if item['name'].endswith('Well') else
                        'structure/upgrade identity; family operations checked separately')
        if item['category'] == 'Shelters':
            item['limit'] = 'VL-058 higher housing capacities deliberately deferred; occupancy not fully accepted'
        items.append(item)
    result = {'version': '0.2.11-community-test', 'source_sha256': fingerprint(),
              'source': scope['source'], 'audit': str(audit_path), 'regressions': audit['regressions'],
              'counts_by_category': dict(collections.Counter(i['category'] for i in items)),
              'items': items, 'native_acceptance': 'pending',
              'shared_tests': ['test_all_building_items.AllBuildingItems', 'test_farming.FarmingTests',
                               'test_fun_matrix.FunMatrixTests', 'test_learning.LearningTests'],
              'limits': ['Synthetic later-area access maxAreaId=3 is explicit in fixtures; normal story UnlockArea/ProgressArea is unfinished (VL-061).',
                         'Housing capacity and related limits deferred at user request (VL-058).',
                         'Farm recipes preserve original task rewards, including mismatched farming_task275 material3177/task1553 reward3181; no authored-data rewrite.',
                         'Native previews, animations, pathfinding, storage behaviour and long-session performance require manual testing.']}
    folder = ROOT / 'analysis/all-building-items'
    folder.mkdir(exist_ok=True)
    (folder / 'coverage.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    lines = ['# All listed buildings and items — manual acceptance', '',
             'Update to 0.2.11. These entries pass server fixtures; all native rows remain pending.', '',
             '| Category | Item | Obtain/build/upgrade | Use | Move/restart where offered |',
             '|---|---|---|---|---|']
    lines += [f"| {i['category']} | {i['name']} | [ ] | [ ] | [ ] |" for i in items]
    lines += ['', *result['limits']]
    (folder / 'MANUAL_CHECKLIST.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps({'items': len(items), 'categories': result['counts_by_category'],
                      'regressions': result['regressions'], 'folder': str(folder)}, indent=2))


if __name__ == '__main__':
    main()
