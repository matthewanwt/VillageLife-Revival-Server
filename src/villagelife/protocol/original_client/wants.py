"""Persistent daily wishes and original food/water consumption."""
from __future__ import annotations
import copy
import json
import math
from collections.abc import MutableMapping
from decimal import Decimal
from functools import cached_property, lru_cache
from .daily import DailyLife, satisfy_wants
from .interactive import OriginalInteractiveRules
from .catalog import OriginalDefinitions
from .inventory import OriginalInventoryRules
from .retirement import active_retirements

RETIREMENT_WANTS = 'GenerateRetirementWants'

class OriginalWantRules:
    BASIC={'ClientWant/GenerateWaterWants':(1,6,'thirstIntervalSec'),
           'ClientWant/GenerateFoodWants':(2,107,'hungerIntervalSec')}
    CATEGORIES = {'GenerateFunWants': 3, 'GenerateFireWants': 4,
                  'GenerateShelterWants': 6, 'GenerateInteractiveWants': 8,
                  RETIREMENT_WANTS: 9}

    def __init__(self, definitions: OriginalDefinitions,
                 inventory: OriginalInventoryRules | None = None):
        self.defs = definitions
        self.inventory = inventory or OriginalInventoryRules(definitions)
        self.daily = DailyLife(definitions)
        self.interactive = OriginalInteractiveRules(definitions, self.inventory, self.daily)

    @cached_property
    def globals(self) -> dict:
        return self.daily.world.global_values

    @cached_property
    def fun_buildings(self) -> dict:
        activities = {row['id']:row for row in self.defs.rows('fun_activity')}
        return {int(row['id']):activities[row['funActivity']]
                for row in self.defs.rows('fun_building') if row['funActivity'] in activities}

    def _fun_target(self, state: dict, actor: dict, area_entities: list[dict], at: int) -> int | None:
        delay = int(self.globals.get('funWantDelay', 6400))
        if at - int(state.get('createdAt', 0)) < delay:
            return None
        if at - state.get('needSatisfiedAt', {}).get(actor['id'] + ':3', -delay) < delay:
            return None
        owned = {item['templateId'] for item in area_entities if item.get('templateType') == 'fun_building'
                 and item.get('amount', 1) > 0}
        kind = self.daily.world.current_villager_type(actor, at)
        kind_id = str(kind.get('id', actor['templateId']))
        eligible = {ident:activity for ident,activity in self.fun_buildings.items()
                    if kind_id in self.daily.groups.get(activity['usedBy'], ())}
        # Owned and usable fun buildings let the native idle animation run.
        # Asking for those same buildings would prevent autonomous play.
        if not eligible or owned.intersection(eligible) or actor.get('xp', 0) >= self.daily.xp_cap(state):
            return None
        level = int(state['user']['userLevelID'])
        preferred = int(self.globals.get('startingFunWantMaterialTypeId', 132))
        choices = []
        for activity in eligible.values():
            material = self.defs.item('material_type', activity['materialType'])
            if (int(material['area']) in {0, state['areaId']} and not int(material['seasonal'])
                    and int(material['unlockLevel']) <= level
                    and material['categoryId'] == '35'):
                choices.append((int(material['id']) != preferred, int(material['unlockLevel']), int(material['id'])))
        return min(choices)[2] if choices else None

    def shelter_want_age(self) -> int:
        return max(5, int(self.globals.get('villager_wants_shelter_at_age', 5)))

    @cached_property
    def shelter_materials(self):
        return {int(row['materialType']): self.defs.item('material_type', row['materialType'])
                for row in self.defs.rows('building_type') if row.get('entityRef') == 'shelter'}

    def _default_shelter(self, state):
        level = int(state.get('user', {}).get('userLevelID', 1))
        choices = [ident for ident, row in self.shelter_materials.items()
                   if int(row.get('area', 0)) in {0, state['areaId']}
                   and int(row.get('unlockLevel', 0)) <= level
                   and int(row.get('seasonal', 0)) == 0]
        if choices:
            return min(choices, key=lambda ident:(
                int(self.shelter_materials[ident].get('area', 0)) != state['areaId'],
                int(self.shelter_materials[ident].get('unlockLevel', 0)), ident))
        return 131 if state['areaId'] == 1 else None

    def clear_ineligible_shelter_wants(self, state: dict, at: int) -> None:
        too_young = {person['id'] for person in self._actors(state)
                     if self.daily.world.current_age(person, at) < self.shelter_want_age()}
        wants = state.get('wants', [])
        wants[:] = [want for want in wants if want.get('wantableCategoryType') != 6
                    or want.get('VillagerStringID') not in too_young]

    def _target(self, state: dict, actor: dict, category: int,
                area_entities: list[dict], actors: list[dict], at: int) -> int | None:
        if category == 3:
            return self._fun_target(state, actor, area_entities, at)
        if category == 8:
            options = self.interactive.available(state, actor, actors, at)
            return int(options[0]['materialType']) if options else None
        if self.daily.world.current_age(actor, at) < int(self.globals.get('villager_wants_shelter_at_age', 4)):
            return None
        if category == 6:
            if self.daily.world.current_age(actor, at) < self.shelter_want_age():
                return None
            sheltered = any(bed.get('id') == actor.get('shelterBedId')
                            and bed.get('villagerId') == actor['id']
                            for home in area_entities if home.get('templateType') == 'shelter'
                            for bed in home.get('beds', []))
            return None if sheltered else self._default_shelter(state)
        fires = [entity for entity in area_entities if entity.get('templateType') == 'fire_type']
        if any(fire.get('isBurning') and fire.get('endsAt', 0) > at for fire in fires):
            return None
        if fires:
            return int(self.defs.item('fire_type', fires[0]['templateId'])['MaterialTypeID'])
        return 201

    def _append(self, state: dict, actor: dict, category: int, material: int, at: int) -> None:
        wants = state.setdefault('wants', [])
        ident = max(int(state.get('nextWantId', 1)),
                    max((int(row['WantId']) for row in wants), default=0) + 1)
        state['nextWantId'] = ident + 1
        wants.append({'WantId': ident, 'VillagerStringID': actor['id'], 'MaterialID': material,
                      'wantableCategoryType': category, 'updatedAt': at})

    @cached_property
    def food_definitions(self) -> dict[int, dict]:
        parents = {row['id']: row['parentId'] for row in self.defs.rows('material_category')}
        food_categories = {'41'}
        while True:
            children = {ident for ident, parent in parents.items() if parent in food_categories}
            if children <= food_categories:
                break
            food_categories.update(children)
        return {int(row['id']): row for row in self.defs.rows('material_type')
                if row.get('categoryId') in food_categories}

    def _food_choices(self, state: dict) -> list[int]:
        level = int(state.get('user', {}).get('userLevelID', 1))
        return sorted(ident for ident, row in self.food_definitions.items()
                      if state['inventory'].get(str(ident), 0) >= 1
                      and int(row.get('area', 0)) in {0, state['areaId']}
                      and int(row.get('unlockLevel', 0)) <= level
                      and int(row.get('seasonal', 0)) == 0)

    @cached_property
    def food_sources(self):
        rewards = {}
        for row in self.defs.rows('reward_set_item'):
            ident = int(row['materialType'])
            if (ident in self.food_definitions and float(row['quantity']) > 0
                    and float(row['chance']) > 0):
                rewards.setdefault(row['setId'], set()).add(ident)
        tasks = {row['id']: rewards.get(row['rewardSet'], set()) for row in self.defs.rows('task')}
        return {int(row['id']): tasks.get(row['task'], set()) for row in self.defs.rows('material_source')}

    def _default_food(self, state, stocked):
        if stocked:
            return 107 if 107 in stocked else stocked[0]
        level = int(state.get('user', {}).get('userLevelID', 1))
        sources = {ident for entity in state['world']['entities']
                   if entity.get('templateType') == 'material_source'
                   and self.daily.world._area(entity) == state['areaId']
                   for ident in self.food_sources.get(entity['templateId'], ())}
        choices = [ident for ident in sources
                   if int(self.food_definitions[ident].get('area', 0)) in {0, state['areaId']}
                   and int(self.food_definitions[ident].get('unlockLevel', 0)) <= level
                   and int(self.food_definitions[ident].get('seasonal', 0)) == 0]
        if choices:
            return min(choices, key=lambda ident:(int(self.food_definitions[ident].get('unlockLevel', 0)),ident))
        # Retain the normal opening default when tiny fixtures have no sources;
        # never request a Woodland-only food in another village.
        original = self.food_definitions.get(107)
        return 107 if original is not None and int(original.get('area', 1)) in {0,state['areaId']} else None

    def generate(self, state: dict, service: str, at: int) -> dict:
        wants = state.setdefault('wants', [])
        method = service.rsplit('/', 1)[-1]
        if method in {'GenerateBirthWants', 'GenerateChildWants'}:
            # These prompts open dating/conception workflows. Activate together
            # with the corresponding actions so the client cannot open a dead end.
            return {'result': copy.deepcopy(wants)}
        basic = self.BASIC.get(service)
        category = basic[0] if basic else self.CATEGORIES[method]
        actors = self._actors(state)
        people = [person for person in actors if self.daily.world._area(person) == state['areaId']]
        retirement = {}
        if method == RETIREMENT_WANTS:
            for person, event in active_retirements(state, self.defs, at):
                retirement[person['id']] = {'VillagerID': person['id'], 'RetireAt': int(person['retireAt']),
                                            'RetireEventID': int(event['id'])}
        area_entities = [entity for entity in state['world']['entities']
                         if self.daily.world._area(entity) == state['areaId']]
        existing = {want['VillagerStringID']: want for want in wants
                    if want.get('wantableCategoryType') == category}
        changed = False
        food = self._food_choices(state) if category == 2 else []
        default_food = self._default_food(state, food) if category == 2 else None
        for actor in people:
            ident = actor['id']
            previous = existing.get(ident)
            if basic:
                interval = int(self.globals[basic[2]])
                last = state.get('needSatisfiedAt', {}).get(f'{ident}:{category}', -interval)
                target = previous['MaterialID'] if previous is not None else basic[1]
                if category == 2:
                    definition = self.food_definitions.get(target)
                    if previous is None or (definition is not None
                            and int(definition.get('area', 0)) not in {0,state['areaId']}):
                        target = default_food
                if previous is None and food:
                    # Advance through foods already in stock at each new wish.
                    # Keep an outstanding wish stable until the player fulfils it.
                    last_food = state.get('lastFoodWish', {}).get(ident)
                    if last_food is None:
                        target = basic[1] if basic[1] in food else food[0]
                    else:
                        target = next((value for value in food if value > last_food), food[0])
                material = (target if at - last >= interval
                            and not self.daily.in_group(actor, '6', at) else None)
            elif method == RETIREMENT_WANTS:
                material = 1966 if ident in retirement else None
            else:
                material = self._target(state, actor, category, area_entities, actors, at)
            if previous is not None and (material is None or previous['MaterialID'] != material):
                wants.remove(previous)
                previous = None
                changed = True
            if previous is None and material is not None:
                self._append(state, actor, category, material, at)
                if category == 2:
                    state.setdefault('lastFoodWish', {})[ident] = material
                changed = True
        if changed:
            state['revision'] = int(state.get('revision', 0)) + 1
        if method == RETIREMENT_WANTS:
            # ServerSyncUpdate expects the schedule and wants under separate
            # keys in this response. Other want families use a plain list.
            return {'result': {'RetireVillagers': list(retirement.values()),
                               'RetireWantModels': [dict(want) for want in wants
                                                    if want.get('wantableCategoryType') == 9
                                                    and want['VillagerStringID'] in retirement]}}
        return {'result': copy.deepcopy(wants)}

    def on_login(self, state: dict, at: int) -> None:
        previous = state.get('lastDailyActivityAt')
        state['lastDailyActivityAt'] = at
        if previous is None:
            return
        if at - previous < max(int(self.globals.get(rule[2], 600)) for rule in self.BASIC.values()):
            return
        if 'userLevelID' not in state.get('user', {}):
            return
        stock = state['inventory']
        actors = self._actors(state)
        if not actors or not any(stock.get(str(rule[1]), 0) >= 1 for rule in self.BASIC.values()):
            return
        totals = {'FoodQuantity': 0, 'DrinksQuantity': 0, 'TotalXp': 0}
        cap = self.daily.xp_cap(state)
        for actor in actors:
            if self.daily.in_group(actor, '6', at):
                continue
            ident = actor['id']
            for category, material, interval_key in self.BASIC.values():
                key = str(material)
                last = state.get('needSatisfiedAt', {}).get(f'{ident}:{category}', previous)
                if at - last < int(self.globals[interval_key]) or stock.get(key, 0) < 1:
                    continue
                old_xp = actor.get('xp', 0)
                if old_xp >= cap:
                    continue
                gain = float(self.defs.item('material_type', material)['xpRewardPerUnitConsumed'])
                actor['xp'] = min(cap, old_xp + gain)
                stock[key] -= 1
                satisfy_wants(state, {ident}, category, at, material)
                state.setdefault('needSatisfiedAt', {})[f'{ident}:{category}'] = at
                totals['DrinksQuantity' if category == 1 else 'FoodQuantity'] += 1
                totals['TotalXp'] += actor['xp'] - old_xp
        if totals['FoodQuantity'] or totals['DrinksQuantity']:
            pending = state.setdefault('offlineConsumption', {})
            for key, amount in totals.items():
                pending[key] = pending.get(key, 0) + amount
            state['revision'] = int(state.get('revision', 0)) + 1

    @lru_cache(maxsize=512)
    def _consume_category(self,material:int)->int:
        category=self.defs.item('material_type',material)['categoryId'];seen=set()
        while category not in seen and category!='-1':
            if category=='5':return 1
            if category=='41':return 2
            seen.add(category)
            category=self.defs.item('material_category',category)['parentId']
        raise ValueError('Direct consumption requires original food or drink')

    @staticmethod
    def compact_consumption_history(state: dict) -> int:
        """Drop inventory snapshots that _current_receipt always reconstructs.

        Keep every receipt, timestamp, want ID and happiness field so retries
        remain safe. Unknown fields and other history collections are untouched.
        """
        removed = 0
        for name in ('consumptionReceipts', 'directConsumptionReceipts'):
            records = state.get(name, {})
            if not isinstance(records, MutableMapping):
                continue
            load_all = getattr(records, 'load_all', None)
            if load_all is not None:
                load_all()
            for record in records.values():
                response = record.get('response') if isinstance(record, dict) else None
                if not isinstance(response, dict):
                    continue
                for target in (response, response.get('result')):
                    if isinstance(target, dict) and 'inventory' in target:
                        del target['inventory']
                        removed += 1
        return removed

    def _current_receipt(self,state:dict,record:dict)->dict:
        response=copy.deepcopy(record['response'])
        person=next((p for p in self._actors(state) if p['id']==record['villagerId']),None)
        if person is None:raise ValueError('Consumed villager is no longer in this village')
        xp=person.get('xp',0)
        response.setdefault('result',{}).update(VillagerStringID=person['id'],Xp=xp)
        satisfied=response.get('SatisfiedWantModels',[])
        want_id=next((v.get('WantId',v.get('WantID')) for v in satisfied),None)
        if want_id is not None:response.setdefault('result',{}).update(WantID=want_id,wantID=want_id)
        happy={'VillagerStringID':person['id'],'VillagerStringId':person['id'],'Xp':xp}
        for target in (response.get('HappinessModel',{}),response.get('result',{}).get('HappinessModel',{})):
            target.update(happy)
        values=self.inventory.list_items(state)
        response['inventory']=values
        response.setdefault('result',{})['inventory']=values
        for want in response.get('SatisfiedWantModels',[]):
            if 'WantID' in want:want['WantId']=want.pop('WantID')
        return response

    @staticmethod
    def _consumption_key(ident, material):
        return json.dumps([ident, material], separators=(',', ':'))

    def _consumption_index(self, state):
        """Index legacy receipts once; ordinary feeding must not load cold history."""
        if 'latestConsumptionReceipts' in state:
            return state['latestConsumptionReceipts']
        index = {}
        clock = state.get('needSatisfiedAt', {})
        for name in ('consumptionReceipts', 'directConsumptionReceipts'):
            for key, record in state.get(name, {}).items():
                if not isinstance(record, dict):
                    continue
                ident, material = record.get('villagerId'), record.get('materialId')
                if not isinstance(ident, str) or type(material) is not int:
                    continue
                try:
                    category = self._consume_category(material)
                except (KeyError, ValueError):
                    # Preserve unknown legacy records without letting one stop
                    # ordinary feeding. Exact receipt-ID replays still work.
                    continue
                stamp = record.get('consumedAt', clock.get(ident + ':' + str(category), 0))
                if type(stamp) not in (int, float) or not math.isfinite(stamp):
                    continue
                pair = self._consumption_key(ident, material)
                if pair not in index or stamp > index[pair]['consumedAt']:
                    index[pair] = {'collection': name, 'key': key, 'consumedAt': stamp}
        state['latestConsumptionReceipts'] = index
        return index

    def consume(self,state:dict,data:dict,at:int,receipt_key:str)->dict:
        ident=data.get('VillagerStringID');material=data.get('MaterialTypeID')
        if not isinstance(ident,str) or isinstance(material,bool) or not isinstance(material,int):
            raise ValueError('Villager and material identifiers required')
        actor=next((p for p in self._actors(state) if p.get('id')==ident),None)
        if actor is None:raise ValueError('Unknown villager')
        if self.daily.world._area(actor) != state['areaId']:
            raise ValueError('Villager is in another area')
        category=self._consume_category(material)
        recent = self._consumption_index(state)
        requested=data.get('WantID')
        direct=state.setdefault('directConsumptionReceipts',{})
        if receipt_key in direct:
            prior=direct[receipt_key]
            if prior['villagerId']!=ident or prior['materialId']!=material:
                raise ValueError('Consumption receipt mismatch')
            return self._current_receipt(state,prior)
        if requested is not None:
            if not str(requested).isdigit():raise ValueError('Invalid want identifier')
            prior=state.get('consumptionReceipts',{}).get(str(int(requested)))
            if prior:
                if prior['villagerId']!=ident or prior['materialId']!=material:
                    raise ValueError('Consumption receipt mismatch')
                return self._current_receipt(state,prior)
        if self.daily.in_group(actor, '6', at):
            raise ValueError('This villager needs a caregiver to feed them')
        want=next((w for w in state.get('wants',[]) if w.get('VillagerStringID')==ident
                   and w.get('MaterialID')==material and
                   (requested is None or str(w.get('WantId'))==str(requested))),None)
        if want is None:
            if requested is not None:raise ValueError('Matching saved want required')
            if category not in {1,2}:raise ValueError('Only original food or drink can be directly consumed')
            interval_key='thirstIntervalSec' if category==1 else 'hungerIntervalSec'
            globals_={row['label']:row['value'] for row in self.defs.rows('global')}
            interval=int(globals_[interval_key]);clock=state.setdefault('needSatisfiedAt',{})
            entry = recent.get(self._consumption_key(ident, material))
            if entry is not None and at - entry['consumedAt'] <= interval:
                previous = state.get(entry['collection'], {}).get(entry['key'])
                if previous is not None:
                    return self._current_receipt(state,previous)
            want={'wantableCategoryType':category,'WantId':None}
        if want['wantableCategoryType'] != category:
            raise NotImplementedError('Fun, housing and equipment consumption need their interaction rules')
        key=str(material)
        if state.get('inventory',{}).get(key,0)<1:raise ValueError('Not enough material to satisfy want')
        level=next((row for row in self.defs.rows('user_level')
                    if int(row['levelNumber'])==int(state['user']['userLevelID'])),None)
        if level is None:raise ValueError('Unknown original user level')
        definition=self.defs.item('material_type',material)
        state['inventory'][key]=float(Decimal(str(state['inventory'][key]))-1)
        actor['xp']=min(int(level['villagerXPCapacity']),
                        actor.get('xp',0)+float(definition['xpRewardPerUnitConsumed']))
        want_id=want['WantId']
        state['wants']=[w for w in state.get('wants',[]) if w.get('WantId')!=want_id]
        state.setdefault('needSatisfiedAt',{})[ident+':'+str(want['wantableCategoryType'])]=at
        happy={'VillagerStringID':ident,'VillagerStringId':ident,'Xp':actor['xp']}
        values=self.inventory.list_items(state)
        satisfied=[{'WantId':want_id,'VillagerStringID':ident}] if want_id is not None else []
        result={'VillagerStringID':ident,'Xp':actor['xp'],'inventory':values,
                'HappinessModel':happy,'HappinessModels':[happy],
                'SatisfiedWantModels':satisfied}
        if want_id is not None:result.update(WantID=want_id,wantID=want_id)
        response={**result,'result':copy.deepcopy(result)}
        record={'villagerId':ident,'materialId':material,'response':copy.deepcopy(response),'consumedAt':at}
        # Replay uses current inventory, never this historical snapshot.
        record['response'].pop('inventory', None)
        record['response']['result'].pop('inventory', None)
        if want_id is None:direct[receipt_key]=copy.deepcopy(record)
        else:state.setdefault('consumptionReceipts',{})[str(want_id)]=copy.deepcopy(record)
        recent[self._consumption_key(ident, material)] = {
            'collection': 'directConsumptionReceipts' if want_id is None else 'consumptionReceipts',
            'key': receipt_key if want_id is None else str(want_id), 'consumedAt': at}
        state['revision']=int(state.get('revision',0))+1
        return response

    def release_xp(self, state: dict, data: dict) -> dict:
        ident = data.get('VillagerStringID')
        actor = next((person for person in self._actors(state)
                      if person['id'] == ident and
                      person.get('position', {}).get('areaId', 1) == state['areaId']), None)
        if actor is None:
            raise ValueError('Unknown villager in the active area')
        amount = actor.get('xp', 0)
        user = state['user']
        if amount:
            user['xp'] = user.get('xp', 0) + amount
            actor['xp'] = 0
            state['revision'] = int(state.get('revision', 0)) + 1
        return {'result': {'UserXp': user.get('xp', 0)}, 'user': dict(user),
                'villager': {'id': actor['id'], 'xp': 0}, 'Xp': 0}

    @staticmethod
    def _actors(state:dict)->list[dict]:
        return [p for p in state.get('world',{}).get('entities',[])
                if p.get('templateType')=='villager_type']
