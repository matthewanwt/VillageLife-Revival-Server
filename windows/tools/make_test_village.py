"""Create explicit disposable diagnostic villages; never overwrite a live save."""
from pathlib import Path
import argparse,copy,datetime,json,shutil,sys,time
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
import family,habitats,session,world,relationships,native_identity,marriage

def create(source,scenario,at=None):
 source=Path(source).resolve();at=int(time.time()) if at is None else at
 if not source.is_dir():raise ValueError('Source save directory does not exist')
 stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
 out=ROOT/'experiments'/('fixture-'+scenario+'-'+stamp);state_dir=out/'state';state_dir.mkdir(parents=True,exist_ok=False)
 profiles=list(source.glob('*.tutorial.json'))
 if len(profiles)!=1:raise ValueError('Select a source containing exactly one tutorial/profile save')
 saved=json.loads(profiles[0].read_text(encoding='utf-8'));normal=saved.get('normal')
 if not normal:raise ValueError('Source must have reached its normal village')
 profile_file=profiles[0].with_name(profiles[0].name.replace('.tutorial.json','.json'))
 if not profile_file.exists():raise ValueError('Matching local profile missing')
 profile=json.loads(profile_file.read_text(encoding='utf-8'))
 changes=[]
 if scenario in {'family-ready','birth-ready','dating-ready','marriage-ready','wedding-ready','family-flow-ready'}:
  keep={'steve','jill'} if scenario not in {'dating-ready','marriage-ready','wedding-ready'} else {'steve'}
  normal['world']['entities']=[e for e in normal['world']['entities'] if e['templateType']!='villager_type' or e['id'] in keep]
  for person in family.actors(normal):
   person['relations']=[r for r in person.get('relations',[]) if r['villagerId'] in keep]
   person.update(startAge=25,bornAt=at,updatedAt=at,pregnant='false',pregnancyStartTime=0,pregnancyTryCount=0,lastChildBornAt=0,marriedAt=at-int(world.global_value('childWantDelayAfterMarriage')),xp=0,shelterBedId='',templateId=5 if person['gender'] else 1)
  for building in normal['world']['entities']:
   for bed in building.get('beds',[]):bed['villagerId']=''
  normal['wants']=[];normal['workAreas']={};normal['pregnancies']={};normal['birthHistory']=[];normal['familyReceipts']={}
  for key in ['npcDatingPool','npcDateRequests','externalVillagers','nextNpcSerial','nextNpcDateRequestId','relationshipWantSatisfiedAt','npcMarriageRequests','nextNpcMarriageRequestId','childWantGeneratedAt']:normal.pop(key,None)
  home={'id':'fixture-family-home','templateType':'shelter','templateId':0,'serverPersisted':True,'localCreated':True,'position':{'x':2200,'y':3400,'areaId':normal['areaId'],'rotation':0}}
  habitats.initialize(home,at);normal['world']['entities']=[e for e in normal['world']['entities'] if e['id']!=home['id']]+[home]
  for index,person in enumerate(family.actors(normal)):
   person['position']={**home['position'],'x':2140+index*80,'y':3540}
   habitats.assign(normal,{'villagerId':person['id'],'shelterBedId':home['beds'][index]['id']},at)
   for category in [1,2,3]:normal.setdefault('needSatisfiedAt',{})[person['id']+':'+str(category)]=at+3600
  normal['world']['camera']={'x':2200,'y':3400,'zoom':1}
  normal['inventory']['323']=500
  if scenario in {'birth-ready','family-flow-ready'}:
   began=at-int(world.global_value('pregnancySkipDuration'))-180
   with patch.object(family,'roll',side_effect=[0,99,0]):family.operate(normal,'ClientVillager/CanConcievePregnancy',{'villagerId':'jill'},began,profile['pId'],'fixture:conceive')
   family.operate(normal,'ClientVillager/DesignPregnancy',{'villagerId':'jill','pregnancyType':'1'},began+1,profile['pId'],'fixture:design')
  if scenario=='family-flow-ready':
   seed=next(v for v in world.rows('villager_starting_variation') if v.get('SpecialType','0')=='0' and v['Gender']=='0' and 18<=int(v['startAge'])<=39)
   typ=world.by_id('villager_type',1)
   person={'id':'fixture-single-adult','refId':'','name':'Oliver','templateType':'villager_type','templateId':1,'serverPersisted':True,'villagerBaseId':int(seed['id']),'startingArea':normal['areaId'],'birthType':0,'specialType':0,'energyLevel':int(typ['maxEnergy']),'energyTimeStamp':at,'startAge':25,'bornAt':at,'updatedAt':at,'pregnant':'false','pregnancyTryCount':0,'pregnancyStartTime':0,'gender':0,'xp':0,'rarity':0,'shelterBedId':'','position':{**home['position'],'x':2380,'y':3540},'equipment':seed['equipment'],'genetics':seed['genetics'],'relations':[],'skills':[],'wants':[],'clothing':[],'isCommunityVillager':'false','retireAt':0,'retireEventID':0}
   normal['world']['entities'].append(person)
   for category in [1,2,3]:normal.setdefault('needSatisfiedAt',{})[person['id']+':'+str(category)]=at+3600
   second={'id':'fixture-second-home','templateType':'shelter','templateId':0,'serverPersisted':True,'localCreated':True,'position':{**home['position'],'x':2600}}
   habitats.initialize(second,at);normal['world']['entities'].append(second)
  if scenario in {'marriage-ready','wedding-ready','family-flow-ready'}:
   person=family.actor(normal,'fixture-single-adult' if scenario=='family-flow-ready' else 'steve');person['communityOptIn']=True
   relationships.catalogue(normal,{'Gender':1},at-20,profile['pId'])
   target=next(p for p in normal['npcDatingPool'] if p['gender']==1)
   raw=next(raw for raw,ident in native_identity.mappings(normal,profile['pId'])[2].items() if ident==person['id'])
   relationships.community(normal,'CharacterRequest/Create',{'ForUserIds':[int(target['ownerUserId'])],'CharacterIds':[int(target['id'].split('_')[-1])],'FriendCharacterId':int(raw)},at-20,profile['pId'])
   relationships.accept_date(normal,{'RequestID':normal['npcDateRequests'][0]['id']},at)
   normal['npcDateRequests'][0]['acceptedAt']=at-int(world.global_value('marriage_want_delay'))
   normal['relationshipWantSatisfiedAt'][person['id']]=at-int(world.global_value('marriageWantRefreshDelay'))
   relationships.generate(normal,at)
   if scenario=='wedding-ready':marriage.operate(normal,'ClientRequestService/SendMarriageRequest',{'senderVillagerId':person['id'],'recipientUserId':target['ownerUserId'],'recipientVillagerId':target['id'],'stars':'0'},at-21,profile['pId'])
  single=scenario in {'dating-ready','marriage-ready','wedding-ready'}
  changes=[('kept one authored adult' if single else 'kept the authored adult couple'),'cleared test work, wishes and prior family/dating requests','owned adults set to25 years with original IDs and appearance','owned adults assigned valid beds in a dedicated basic shelter','500 in-game gems for tests only','food/water wishes suppressed for one hour']
  if scenario in {'birth-ready','family-flow-ready'}:changes+=['starts the original24-hour pregnancy just beyond its due time']
  if scenario in {'marriage-ready','wedding-ready'}:changes+=['one owned adult dating an external private NPC through the tested request/accept handlers; test-only dating clock advanced to expose the original marriage wish; marriage and move-in are not simulated']
  if scenario=='family-flow-ready':changes+=['pregnant married couple in the first hut; one separate adult Oliver ready to propose through his ring wish; an empty second hut for the next couple']
  if scenario=='wedding-ready':changes+=['accepted private NPC marriage proposal is ready in the Relationships inbox; wedding and move-in have not happened']
 elif scenario=='resource-rich':
  for req in world.rows('requirement_set_item'):
   material=req['materialType'];normal['inventory'][material]=max(normal['inventory'].get(material,0),float(req['quantity'])+float(req['quantityUsed'])+100)
  normal['inventory']['323']=500;changes=['funded original table requirements and500 in-game gems in disposable copy']
 else:raise ValueError('Unknown fixture scenario')
 world.validate_world(normal)
 for path,value in [(state_dir/profile_file.name,profile),(state_dir/profiles[0].name,saved)]:session.atomic_json(path,value)
 meta={'scenario':scenario,'createdAt':at,'state':str(state_dir),'source_save_modified':False,'changes':changes,'run':'python tools/play_local.py --test-state "'+str(state_dir)+'" --smoke-test 600','safety':'local-only test state; do not copy fixture balances into normal play or publish this private state'}
 (out/'fixture.json').write_text(json.dumps(meta,indent=2)+'\n',encoding='utf-8');return meta

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--scenario',required=True,choices=['family-ready','birth-ready','dating-ready','marriage-ready','wedding-ready','family-flow-ready','resource-rich']);parser.add_argument('--source',type=Path,default=ROOT/'backend/private_state');args=parser.parse_args();print(json.dumps(create(args.source,args.scenario),indent=2))
if __name__=='__main__':main()
