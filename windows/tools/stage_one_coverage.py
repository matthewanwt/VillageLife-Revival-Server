"""Source-bound Stage1 action/definition register, using the full fresh regression audit.

Does not open a player save, launch Android, or turn synthetic checks into native evidence.
"""
import collections
import csv
import datetime
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
import world
from release_review import fingerprint


def main():
    review = json.loads((ROOT / 'analysis/release-review.json').read_text(encoding='utf-8'))
    if review.get('source_sha256') != fingerprint() or not review.get('regression_audit_passed'):
        raise RuntimeError('Run the complete source-stable release review before generating Stage1 coverage')
    pointer = json.loads((ROOT / 'analysis/latest-feature-audit.json').read_text(encoding='utf-8'))
    audit_path = Path(pointer['folder']) / 'coverage.json'
    if not audit_path.resolve().is_relative_to((ROOT / 'analysis').resolve()):
        raise ValueError('Audit must be inside project analysis')
    audit = json.loads(audit_path.read_text(encoding='utf-8'))
    if not audit['regressions']['passed'] == audit['regressions']['run'] or audit['regressions']['failures'] or audit['regressions']['errors']:
        raise RuntimeError('Regression audit did not pass')
    actions = []
    def action(ident, method, implementation, automated, tests, expected, limits):
        actions.append({'id': ident, 'method': method, 'implementation': implementation,
            'automated': automated, 'native': 'not_verified_in_stage1',
            'shipped': 'pending_stage1_acceptance_package_and_manual_result',
            'test_evidence': tests, 'expected': expected, 'limits': limits})
    action('SHOP-READ', 'ClientMaterialService/GetUserMaterialTypes', 'implemented', 'passed_authenticated_save_journey',
        ['backend/test_shop_journeys.py:AuthenticatedShopJourney'],
        'Return current stock and learning/unlock state after reload; reject unauthorised requests.',
        'Original client display still needs manual acceptance.')
    action('SHOP-BUY', 'ClientMaterialService/BuyMaterialType', 'implemented', 'passed_original_definition_sweep_and_authenticated_journey',
        ['tools/feature_audit.py:purchase_cases', 'backend/test_shop_journeys.py'],
        'Original float32 direct-gem price, quantity and level bounds; deduct/deliver once, preserve on failure and reload.',
        'Only positive direct prices and supported quantity ranges; recipe, placement and use are separate actions. No new learning gate is invented for direct resource top-ups.')
    action('SHOP-BUNDLE', 'ClientMaterialService/BuyStoreItem', 'implemented', 'passed_all18_store_definitions',
        ['backend/test_shop_journeys.py:test_every_store_bundle_cost_delivery_replay_and_failure'],
        'Original store qty times multiples for original price times multiples, once per receipt; replay returns current inventory.',
        'Multiples1,2,100 tested;100 is an existing local input bound, not a recovered original limit. Fire-duration activation is outside this transaction.')
    action('SHOP-SELL', 'ClientMaterialService/SellMaterialType', 'implemented', 'passed_all283_sellable_definitions',
        ['backend/test_shop_journeys.py:test_every_sellable_material_cost_proceeds_and_replay'],
        'Remove stocked units and award original coinsRatio times quantity in material325; no double reward after reload.',
        '283 positive-ratio materials; sale UI availability and stock display still need manual checks.')
    for suffix, title in [('Start', 'learning starts once with original level/parent/area/slot gates'),
                          ('Complete', 'learning unlocks at original expiry without awarding stock'),
                          ('Skip', 'paid skip deducts the shared curve cost once and unlocks without awarding stock')]:
        action('SHOP-LEARN-' + suffix.upper(), 'ClientMaterialService/' + suffix + 'LearningMaterial',
            'implemented', 'passed_authored_learning_sweep', ['backend/test_learning.py', 'backend/test_shop_journeys.py'],
            title + '; persisted across reload.',
            '649 authored timed materials; natural and paid paths tested. Seasonal calendar and legacy key-charge semantics remain unrecovered; original timers do not prove original server selection policy.')
    action('SHOP-LEGACY-BALANCE', 'shared pre-operation tutorial synchronisation', 'fixed_in_stage1', 'passed_reproduced_authenticated_regression',
        ['backend/test_shop_journeys.py:test_completed_legacy_village_read_preserves_balances_and_xp', 'backend/test_progression_needs.py'],
        'A completed village with missing tutorial receipts retains current inventory; established shrine XP is not granted again. Retire old effects once.',
        'No reconstruction of balances already overwritten by an older build. Fresh unfinished tutorial assignments remain supported; fresh level1 zero-XP tutorial recovery is retained.')
    action('SHOP-KEY-CONVERSION', 'ClientMaterialService/ConvertKeysToGems', 'not_implemented', 'not_covered_no_recovered_complete_contract',
        ['analysis/server_contracts.json', 'backend/session.py'],
        'Recover original trigger, conversion, response and replay semantics before implementing.',
        'Original method/global labels exist but are insufficient to invent a payout. Explicit Stage1 gap, not silently counted passed.')
    action('SHOP-PLACEABLE-HANDOFF', 'placement and construction services', 'separate_stages2_and3', 'not_counted_as_shop_acceptance',
        ['notes/STAGED_IMPLEMENTATION_PLAN.md'], 'A purchase transaction alone does not prove preview, placement or construction.',
        'Mud shelter build crash, flowerbeds, paths and adjacency remain open for their stages.')
    action('SHOP-COMMERCIAL', 'gem+ / real-money / advertising screens', 'not_a_restored_payment_flow', 'not_counted_as_supported_purchase',
        ['notes/RESTORATION_TRACKER.json:VL-022'], 'Keep unsupported commercial actions separate from in-game gem purchases.',
        'Gem+ native crash remains; do not ask testers to buy real currency or describe commercial screens as fixed.')
    definitions = []
    def entry(kind, row, status, reason, tests):
        definitions.append({'kind': kind, 'definition_id': row['id'], 'name': row.get('name', row.get('description', '')),
            'automated': status, 'reason': reason, 'test_evidence': tests,
            'native': 'not_verified_in_stage1'})
    purchases = {str(row['material_id']): row for row in audit['purchases']}
    materials = world.rows('material_type')
    if set(purchases) != {r['id'] for r in materials}:
        raise RuntimeError('Purchase inventory and original definitions disagree')
    for row in materials:
        original = purchases[row['id']]
        entry('direct_purchase', row, original['status'], original.get('reason'), ['tools/feature_audit.py:purchase_cases'])
        sale = int(row['coinsRatio'] or 0) > 0 and row['id'] not in {'323', '325'}
        entry('sale', row, 'passed_server_fixture' if sale else 'not_applicable',
              'Positive original coin ratio' if sale else 'No positive original sale price; currencies are not sale stock', ['backend/test_shop_journeys.py'])
        timed = int(row['id']) > 0 and int(row['learnDurationSec']) > 0
        entry('learning', row, 'passed_server_fixture' if timed else 'not_applicable',
              'Start, natural finish and paid skip, with reload/replay' if timed else 'No authored positive learning duration', ['backend/test_learning.py'])
    for row in world.rows('store_item'):
        entry('store_bundle', row, 'passed_server_fixture', 'Original qty/price; multiples1,2,100, replay, current reply stock and insufficient funds', ['backend/test_shop_journeys.py'])
    keys = [(v['kind'], v['definition_id']) for v in definitions]
    if len(keys) != len(set(keys)):
        raise ValueError('Duplicate coverage row')
    result = {'stage': 1, 'generated_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'source_sha256': review['source_sha256'], 'audit_source': str(audit_path),
        'regressions': audit['regressions'], 'actions': actions, 'definitions': definitions,
        'counts_by_kind': {kind: dict(collections.Counter(v['automated'] for v in definitions if v['kind'] == kind)) for kind in sorted({v['kind'] for v in definitions})},
        'manual_acceptance': 'pending; notes/STAGE1_REPORT_AND_MANUAL_TESTS.md',
        'limitations': ['Synthetic original-data sweeps are not original-client UI or balance verification.',
                       'Excluded direct purchases may be obtained through other game flows; not automatically missing.',
                       'Definition coverage and action/method coverage are distinct; keys conversion remains a known gap.',
                       'No live save or Android was used by this generator.']}
    out = ROOT / 'analysis/stage-one-coverage'; out.mkdir(exist_ok=True, parents=True)
    (out / 'coverage.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    with (out / 'definitions.csv').open('w', encoding='utf-8-sig', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=['kind','definition_id','name','automated','native','reason'])
        writer.writeheader(); writer.writerows({k: v.get(k) for k in writer.fieldnames} for v in definitions)
    lines = ['# Stage1 action register', '', 'Source fingerprint: ' + review['source_sha256'], '',
             '| ID | Action | Implementation | Automated evidence | Native acceptance |', '|---|---|---|---|---|']
    lines += ['| ' + ' | '.join(str(v[k]) for k in ('id','method','implementation','automated','native')) + ' |' for v in actions]
    lines += ['', 'Definition coverage: ' + json.dumps(result['counts_by_kind'], sort_keys=True), '',
              'Read notes/STAGE1_REPORT_AND_MANUAL_TESTS.md before manual acceptance.']
    (out / 'ACTIONS.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps({'actions': len(actions), 'definition_rows': len(definitions), 'counts': result['counts_by_kind'], 'folder': str(out)}, indent=2))


if __name__ == '__main__': main()
