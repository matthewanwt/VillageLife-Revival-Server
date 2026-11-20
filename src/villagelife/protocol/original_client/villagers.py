"""Original villager identity and naming actions."""
from __future__ import annotations
import hashlib
import json
from collections import Counter
from decimal import Decimal
from .catalog import OriginalDefinitions
from .inventory import OriginalInventoryRules, spend_gems
from .world import OriginalWorldRules
from .birth_skills import skill_type


class OriginalVillagerRules:
    def __init__(self, definitions: OriginalDefinitions | None = None):
        self.defs=definitions

    @staticmethod
    def set_name(state: dict, data: dict) -> tuple[str, str]:
        ident = data.get('villagerId')
        if not isinstance(ident, str) or not ident:
            raise ValueError('Villager identifier required')
        actor = next((entity for entity in state.get('world', {}).get('entities', [])
                      if entity.get('id') == ident and entity.get('templateType') == 'villager_type'), None)
        if actor is None:
            raise ValueError('Unknown villager in this village')
        name = data.get('name')
        if (not isinstance(name, str) or not name.strip() or len(name.strip().encode('utf-8')) > 64
                or any(ord(char) < 32 for char in name)):
            raise ValueError('Invalid villager name')
        normalized = name.strip()
        # The caller commits this normal-world mutation transactionally with
        # the matching tutorial/user-hash name below.
        actor['name'] = normalized
        return ident, normalized

    def _actors(self,state:dict)->list[dict]:
        return [p for p in state.get('world',{}).get('entities',[])
                if p.get('templateType')=='villager_type']

    def history(self,state:dict,data:dict,at:int,owner_id:str)->dict:
        requested=data.get('userId',owner_id)
        if str(requested)!=str(owner_id):
            raise PermissionError('Villager history is limited to this village')
        people = (self._actors(state) + list(state.get('externalVillagers', {}).values())
                  + list(state.get('retiredVillagers', {}).values()))
        by_id={p['id']:p for p in people}
        kinds={(int(row['Relationship']),int(row['genderTypeId'])):int(row['id'])
               for row in self.defs.rows('relation_type')}
        villagers=[];relations=[]
        world = OriginalWorldRules(self.defs)
        for person in people:
            current = world.current_villager_type(person, at)
            villagers.append({'id':person['id'],'name':person.get('name',''),
                'birthType':int(person.get('birthType',0)),'startAge':person['startAge'],
                'bornAt':person['bornAt'],'villagerTypeId':int(current['id']),
                'equipment':person.get('equipment',{}),'gender':int(person.get('gender',0)),
                'userId':str(person.get('ownerUserId',owner_id)),'neighborUserId':'','neighborVillagerId':''})
            for relation in person.get('relations',[]):
                relative=by_id.get(relation.get('villagerId'))
                if relative is None:continue
                group=int(relation['type']);group={0:1,1:0}.get(group,group)
                kind=kinds.get((group,int(person.get('gender',0))))
                if kind is None:continue
                digest=hashlib.sha256((person['id']+':'+relative['id']+':'+str(kind)).encode()).hexdigest()
                relations.append({'id':digest,'villagerId':person['id'],
                    'relativeVillagerId':relative['id'],'relationTypeId':kind,
                    'createdAt':max(int(person.get('bornAt',0)),int(relative.get('bornAt',0)))})
        return {'villagers':villagers,'villagerRelations':relations}

    def skills(self,state:dict,data:dict)->dict:
        value=data.get('villagerIds')
        if not isinstance(value,str) or len(value)>20000:
            raise ValueError('Encoded villagerIds object required')
        try:parsed=json.loads(value)
        except (ValueError,TypeError) as exc:raise ValueError('Invalid encoded villagerIds') from exc
        ids=parsed.get('villagerIds') if isinstance(parsed,dict) else None
        if not isinstance(ids,list) or not 1<=len(ids)<=100 or any(not isinstance(v,str) or not v for v in ids):
            raise ValueError('Invalid villagerIds list')
        actors={p['id']:p for p in self._actors(state)}
        actors.update({p['id']:p for p in state.get('npcDatingPool',[]) if p.get('ownerKind')=='npc'})
        if any(ident not in actors for ident in ids):raise ValueError('Unknown villager in this village')
        result=[]
        for ident in dict.fromkeys(ids):
            for skill in actors[ident].get('skills',[]):
                kind=skill_type(skill)
                self.defs.item('villager_skill',kind)
                result.append({'villagerId':ident,'skilltypeId':kind,
                               'skillOriginType':int(skill['skillOriginType'])})
        return {'villagerSkills':result}

    def buy_skills(self, state: dict, data: dict, at: int,
                   inventory: OriginalInventoryRules, *, bundle: bool) -> dict:
        ident = data.get('villagerId')
        actor = next((person for person in self._actors(state) if person['id'] == ident), None)
        if actor is None:
            raise ValueError('Unknown villager in this village')
        world = OriginalWorldRules(self.defs)
        if world.current_age(actor, at) < 13:
            raise ValueError('Villager is too young for skill training')
        maximum = int(state['user'].get('maxAreaId', state['areaId']))
        available = {int(row['id']) for row in self.defs.rows('villager_skill')
                     if int(row['id']) > 0 and int(row['area']) <= maximum}
        limit = int(world.global_value('skill_slots_max'))
        skills = actor.get('skills', [])
        ranks = Counter(map(skill_type, skills))
        if bundle:
            training = [skill for skill in sorted(available)
                        for _ in range(max(0, limit - ranks[skill]))]
        else:
            skill = data.get('skillTypeId')
            if type(skill) is not int or skill not in available:
                raise ValueError('Skill is unavailable in this village')
            if ranks[skill] >= limit:
                raise ValueError('Villager already has all ranks of this skill')
            training = [skill]
        if not training:
            return {'inventory': inventory.list_items(state)}
        price = Decimal(world.global_value('skill_gem_cost')) * len(training)
        if bundle:
            price *= Decimal(world.global_value('skill_gem_buyout_discount'))
        cost = int(price)
        spend_gems(state, cost)
        actor['skills'] = skills + [{'skilltypeId': skill, 'skillOriginType': 3}
                                    for skill in training]
        state['revision'] = int(state.get('revision', 0)) + 1
        return {'inventory': inventory.list_items(state)}
