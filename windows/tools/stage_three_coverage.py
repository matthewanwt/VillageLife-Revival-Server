"""Source-bound foundation/construction coverage, not native gameplay certification."""
import collections
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
import buildings,world
from release_review import fingerprint


def main():
    review=json.loads((ROOT/'analysis/release-review.json').read_text(encoding='utf-8'))
    if review.get('source_sha256')!=fingerprint() or not review.get('regression_audit_passed'):
        raise RuntimeError('Fresh complete source-stable regression review required')
    pointer=json.loads((ROOT/'analysis/latest-feature-audit.json').read_text(encoding='utf-8'))
    source=Path(pointer['folder'])/'coverage.json'
    if not source.resolve().is_relative_to((ROOT/'analysis').resolve()):raise ValueError('Unsafe audit path')
    audit=json.loads(source.read_text(encoding='utf-8'))
    variants={(str(row['task_id']),str(row.get('foundation_id'))):row for row in audit['tasks']}
    definitions=[]
    for foundation in world.rows('building_task'):
        task=world.by_id('task',foundation['taskId']);building=world.by_id('building_type',foundation['buildingType'])
        evidence=variants.get((task['id'],foundation['id']))
        definitions.append({'foundation_id':foundation['id'],'task_id':task['id'],'name':task['name'],
            'entity_type':building['entityRef'],'entity_template':building['entityID'],
            'completion_kind_declared':building['entityRef'] in buildings.SUPPORTED_BUILD_KINDS,
            'automated':evidence['status'] if evidence else 'no_applicable_fixture_mapping',
            'reason':evidence.get('reason') if evidence else 'No matching variant in full original-data sweep',
            'native':'pending_stage3_acceptance'})
    cases=[
        ('BUILD-PREREQUISITE','Real user/shrine XP for original material7 level requirements; completed Bridge milestone without stock grant; no consumption by this non-consumed gate.'),
        ('BUILD-FARM','Mud Farm House normal/paid completion and authored five-tier identity-preserving upgrade chain. No crop/plot operation implemented.'),
        ('BUILD-START-REPLAY','Authenticated start receipts survive finish/harvest; same accepted request returns current completion time, no duplicate work or charge; conflicting reuse rejected.'),
        ('BUILD-SHELTER-POSITION','Mud Shelter result position ID agrees with saved/projected/movable identity; original bed records remain.'),
        ('BUILD-EXISTING-FAMILIES','Existing shelter/storage/workshop/fun/fire/decor/source completion checks retained; original-definition fixtures do not prove native previews or all construction UI.'),
        ('BUILD-UNSUPPORTED','Gem mines, fishing structures, hunting lodges, crop plots and original progression-object schemas remain explicitly unsupported until recovered.')]
    result={'stage':3,'batch':'first','version':'0.2.10-community-test','source_sha256':review['source_sha256'],
        'audit_source':str(source),'regressions':audit['regressions'],'actions':[{'id':i,'scope':s,'native':'pending'} for i,s in cases],
        'definitions':definitions,'counts':{'foundations':len(definitions),'automated':dict(collections.Counter(r['automated'] for r in definitions)),
        'by_entity_type':dict(collections.Counter(r['entity_type'] for r in definitions))},
        'report':'notes/STAGE3_REPORT_AND_MANUAL_TESTS.md',
        'limitations':['Authored variants include obsolete/sentinel content; missing mappings are not silently passed.',
        'Farm-house construction is not farming production; Stage4 resource operations remain separate.',
        'Receipts cannot identify historic requests that predate the start-receipt field.',
        'Native higher-level building reports remain only partly diagnosed; verify exact item/phase before claiming a fix.']}
    out=ROOT/'analysis/stage-three-coverage';out.mkdir(parents=True,exist_ok=True)
    (out/'coverage.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    lines=['# Stage3 first-batch register','','| Action | Scope | Native |','|---|---|---|']
    lines+=['| '+c['id']+' | '+c['scope']+' | pending |' for c in result['actions']]
    lines+=['','Definition counts: '+json.dumps(result['counts']),*result['limitations']]
    (out/'ACTIONS.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({'actions':len(cases),**result['counts'],'folder':str(out)},indent=2))


if __name__=='__main__':main()
