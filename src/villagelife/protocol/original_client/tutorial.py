"""Initial original-client FTUE records and deliberately limited RPC rules.

These shapes are derived from the 2.11 observed protocol and authored
seq_state_tablet_ftue/villager_starting_variation tables. Unknown operations
MUST fail, never award currency or claim a task succeeded.
"""
from __future__ import annotations
import json
import time
from villagelife.protocol.original_client.catalog import OriginalDefinitions
from villagelife.protocol.original_client.randomness import new_state, choice

STARTING_GEMS = 1000


class TutorialRules:
    def __init__(self, definitions: OriginalDefinitions):
        self.defs=definitions
        self._sequences=None

    def fresh(self) -> dict:
        steps=self.defs.rows('seq_state_tablet_ftue')
        required={json.loads(s['dataJSON'])['refId'] for s in steps if s['sequenceType']=='62'}
        villagers=[]
        rng=new_state()
        for source in self.defs.rows('villager_starting_variation'):
            ref=source['refId']
            if ref=='sister' and (source['villagerType']!='11' or not 5<=int(source['startAge'])<=12):
                continue
            if ref in required and not any(v['refId']==ref for v in villagers):
                villagers.append({'id':ref,'refId':ref,'name':source['name'],'variationId':int(source['id'])})
        # The authored table contains four distinct name, hair and appearance
        # variants for each of the two opening adults. Select once and persist
        # the seed and chosen variation with the account's first tutorial save.
        variations=self.defs.rows('villager_starting_variation')
        for ref in ('steve','jill'):
            candidates=[row for row in variations if row['refId']==ref]
            if candidates:
                selected=choice(rng,candidates)
                person=next((v for v in villagers if v['refId']==ref),None)
                if person is not None:
                    person.update(name=selected['name'],variationId=int(selected['id']))
        if {v['refId'] for v in villagers}!=required:
            raise ValueError('Original FTUE definitions inconsistent: missing villagers')
        return {'version':1,'rng':rng,'userHash':{'activeSequence':0,'segmentId':0,'data':{'villagers':villagers}},
                'gameSettings':{},'shelters':{},'startingGemGrant':STARTING_GEMS}

    def sequences(self) -> set[int]:
        if self._sequences is None:
            rows=self.defs.rows('seq_state_tablet_ftue')
            self._sequences={int(r['id']) for r in rows}|{int(r['persist']) for r in rows if int(r['persist'])>0}
        return self._sequences

    def run(self, save: dict, service: str, data: dict) -> tuple[dict,bool]:
        now=int(time.time()); user_hash=save['userHash']
        if service=='ClientUserHashService/GetUserHash':
            return {'userHash':user_hash},False
        if service=='ClientUserHashService/SetActiveSequence':
            value=data.get('activeSequence')
            if type(value) is not int or value not in self.sequences():
                raise ValueError('Unknown original tutorial checkpoint')
            user_hash['activeSequence']=value
            return {},True
        if service=='ClientUserHashService/SetVillagerName':
            ident=str(data.get('villagerId',''));name=data.get('name')
            if not isinstance(name,str) or not name.strip() or len(name.encode('utf-8'))>64 or any(ord(c)<32 for c in name):
                raise ValueError('Invalid villager name')
            villager=next((v for v in user_hash['data']['villagers'] if v['id']==ident or v['refId']==ident),None)
            if villager is None:raise ValueError('Unknown tutorial villager')
            villager['name']=name
            if save.get('normal'):
                for actor in save['normal']['world']['entities']:
                    if actor.get('id')==villager['id']:actor['name']=name
            return {},True
        if service=='ClientSettingService/GetUserGameSettings':
            values=dict(save.get('gameSettings') or {})
            if 'activeSequenceId' in values:values['activeSequence']=values['activeSequenceId']
            if isinstance(save.get('normal'), dict):
                values['lastViewedArea'] = str(save['normal']['areaId'])
            return {'gameSettings':[{'key':k,'value':v} for k,v in values.items()]},False
        if service=='ClientSettingService/SaveGameSetting':
            key=data.get('key');value=data.get('value')
            if not isinstance(key,str) or not key or len(key)>128 or not isinstance(value,(str,int,float,bool)) or len(str(value).encode())>65536:
                raise ValueError('Invalid game setting')
            value=str(value).lower() if isinstance(value,bool) else str(value)
            settings=save.setdefault('gameSettings',{});settings[key]=value
            if key in {'activeSequence','activeSequenceId'}:
                settings['activeSequence']=value;settings['activeSequenceId']=value
            return {},True
        if service=='ClientUserShelterService/ResetHappinessTimer':
            ident=data.get('userShelterId')
            if not isinstance(ident,str) or not ident or len(ident)>128 or any(ord(c)<32 for c in ident):
                raise ValueError('Invalid shelter identifier')
            record=save.setdefault('shelters',{}).setdefault(ident,{'id':ident})
            record['happinessCollectedAt']=now
            return {'userShelter':dict(record)},True
        if service=='ClientUser/KeepActive':
            save['lastActiveAt']=now
            return {},True
        raise NotImplementedError(service)
