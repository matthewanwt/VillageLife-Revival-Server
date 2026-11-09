"""Source-bound Stage2 placement register; never uses a live save or Android."""
import collections
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
import world
from release_review import fingerprint


def main():
    review=json.loads((ROOT/'analysis/release-review.json').read_text(encoding='utf-8'))
    if review.get('source_sha256')!=fingerprint() or not review.get('regression_audit_passed'):
        raise RuntimeError('Fresh source-stable regression review required')
    methods=[
        ('PLACE-OWNED','CreateUserDecorItem','555 owned definitions consume stock; no extra price; replay after moving does not duplicate'),
        ('PLACE-SHOP','CreateUserDecorItem','259 visible definitions charge original prices; insufficient currency leaves state unchanged'),
        ('MOVE','UpdatePosition','Explicit coordinates, same saved position identity, no currency charge; receipt replay cannot undo a newer move'),
        ('ROTATE','UpdatePosition','Rotation persists with movement; original client determines which items/rotations it offers'),
        ('DELETE','DeleteUserDecorItem','Only selected identity removed; repeated delete and delayed accepted move retry do not resurrect it; no invented refund'),
        ('FOUNDATION-ID','GetUserBuildingTasks','Saved foundation position ID agrees with world projection; construction is Stage3'),
        ('NEIGHBOUR','GetAreaContent','Two synthetic adjacent objects retain separate identities across move/delete/reload'),
        ('NATIVE-PREVIEW','original placement UI','Pending manual testing; server success does not establish native asset preview, grid/collision or adjacency correctness')]
    actions=[{'id':ident,'method':method,'scope':scope,
              'automated':'not_established' if ident=='NATIVE-PREVIEW' else 'passed_regression',
              'native':'pending_stage2_manual_acceptance','evidence':['backend/test_placement_journeys.py','backend/test_placement.py']}
             for ident,method,scope in methods]
    decor=[]
    for row in world.rows('decor_item'):
        material=world.by_id('material_type',row['material_type'])
        decor.append({'id':row['id'],'name':material['name'],'material_id':row['material_type'],
            'owned_lifecycle':'passed_server_fixture','shop_transaction':'passed_server_fixture' if row['hidden']=='0' else 'hidden_excluded_from_shop_sweep',
            'price_gems':row['price_gems'],'price_coins':row['price_coins'],
            'collision_component':row['collisionComponent'],'native':'not_verified_in_this_batch'})
    collisions=[{'id':row['id'],'name':row['name'],'rectangle':row['rectangle'],
                 'status':'original_data_only; native geometry not reproduced by server tests'}
                for row in world.rows('collision_component')]
    result={'stage':2,'source_sha256':review['source_sha256'],'actions':actions,'decorations':decor,
        'collision_definitions':collisions,'counts':{'owned_decorations':len(decor),
        'visible_shop_decorations':sum(d['shop_transaction']=='passed_server_fixture' for d in decor),
        'collision_definitions_inventoried':len(collisions)},
        'manual_report':'notes/STAGE2_REPORT_AND_MANUAL_TESTS.md',
        'limitations':['Synthetic lifecycle success does not establish native previews, collisions, visual adjacency or all original assets.',
                      'Existing local0..10000 coordinate bounds remain a reconstruction; original negative-coordinate scenery exists. Original playable bounds need further evidence before changing them.',
                      'No new refund, collision geometry or rotation restriction is invented.',
                      'Higher-level unlocked building Connection Lost (VL-050) is deferred to Stage3 at user request.',
                      'Receipts prevent retries of moves accepted by this build, not unidentified historical requests predating receipts.']}
    out=ROOT/'analysis/stage-two-coverage';out.mkdir(parents=True,exist_ok=True)
    (out/'coverage.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    lines=['# Stage2 action register','','| ID | Method | Automated | Native | Scope |','|---|---|---|---|---|']
    lines+=['| '+' | '.join(v[k] for k in ('id','method','automated','native','scope'))+' |' for v in actions]
    lines+=['','Definition counts: '+json.dumps(result['counts']),'',*result['limitations']]
    (out/'ACTIONS.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({'actions':len(actions),**result['counts'],'folder':str(out)},indent=2))


if __name__=='__main__':main()
