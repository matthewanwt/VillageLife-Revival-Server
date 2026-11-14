"""Authored foundation placement and removal for the original client."""
from __future__ import annotations

import math
import uuid
import copy

from .catalog import OriginalDefinitions
from .habitats import OriginalHabitatRules
from .inventory import OriginalInventoryRules, spend_gems


class OriginalBuildingRules:
    SUPPORTED_KINDS={'fun_building','container_type','workshop','fire_type','decor_item',
                     'material_source','shelter','farm_building','farming_plot','HuntingLodgeType','fishing_hut'}
    AREA_EQUIPMENT = {
        'ClientFishingService/PlaceFishingBoat':
            (2, 'fishing_hut', 'numBoats', 'fishing_boat', 0, 'userFishingBoat'),
        'ClientHuntingService/PlaceHuntingSled':
            (3, 'HuntingLodgeType', 'HuntingSledCount', 'HuntingSledType', 1, 'userHuntingSled'),
    }

    def __init__(self, definitions: OriginalDefinitions, inventory: OriginalInventoryRules | None = None):
        self.defs = definitions
        self.inventory = inventory or OriginalInventoryRules(definitions)
        self.habitats = OriginalHabitatRules(definitions, self.inventory)

    def _item(self, table: str, ident) -> dict:
        try:
            return self.defs.item(table, ident)
        except KeyError as exc:
            raise ValueError(f'Unknown {table} identifier') from exc

    def _position(self, state: dict, data: dict) -> dict:
        area = data.get('areaId')
        if isinstance(area, bool) or area != state['areaId']:
            raise ValueError('Unknown placement area')
        if 'x' not in data or 'y' not in data:
            raise ValueError('Both placement coordinates are required')
        result = {key: data.get(key, 0) for key in ('x', 'y', 'rotation')}
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
               for value in result.values()):
            raise ValueError('Invalid placement coordinates')
        if not -10000 <= result['x'] <= 10000 or not 0 <= result['y'] <= 10000:
            raise ValueError('Placement outside local world bounds')
        return {**result, 'areaId': state['areaId']}

    @staticmethod
    def _position_id(entity: dict) -> str:
        return str(entity.get('positionId') or entity.get('position', {}).get('id') or entity['id'] + '-position')

    def _placement(self, entity: dict) -> dict:
        return {'userBuildingTaskId': entity['id'],
                'buildingTaskTypeId': entity['templateId'],
                'position': {**entity['position'], 'id': self._position_id(entity)}}

    def list_foundations(self, state: dict) -> dict:
        return {'userBuildingTasks': [self._placement(entity)
                for entity in state['world']['entities'] if entity.get('templateType') == 'building_task']}

    def place_decor(self, state: dict, data: dict) -> dict:
        decor_id = data.get('decorItemId')
        if type(decor_id) is not int:
            raise ValueError('Integer decor identifier required')
        definition = self._item('decor_item', decor_id)
        if definition['isScenery'] == '1':
            raise ValueError('Scenery cannot be placed as decor')
        position = self._position(state, data)
        entities = state['world']['entities']
        if definition['multiPlacement'] == '0' and any(
            entity.get('templateType') == 'decor_item' and entity.get('templateId') == decor_id
            for entity in entities
        ):
            raise ValueError('This decor item is already placed')

        inventory = state['inventory']
        milestones = self.inventory.milestones(state)
        for requirement in self.defs.rows('requirement_set_item'):
            if definition['requirement_set'] == '0' or requirement['requirementSet'] != definition['requirement_set']:
                continue
            material = requirement['materialType']
            if self.inventory.requirement_quantity(state, material, milestones) < float(requirement['quantity']):
                raise ValueError('Decor unlock requirement is not met')

        prices = {'325': int(definition['price_coins']), '323': int(definition['price_gems'])}
        if all(prices.values()):
            raise NotImplementedError('Decor with both coin and gem prices needs a verified purchase rule')
        coins = prices['325']
        if coins and inventory.get('325', 0) < coins:
            raise ValueError('Insufficient currency for decor')
        material = definition['material_type']
        self._item('material_type', material)
        spend_gems(state, prices['323'])
        if coins:
            inventory['325'] -= coins
        inventory[material] = inventory.get(material, 0) + 1
        entity = {'id': 'local-decor-' + uuid.uuid4().hex,
                  'templateType': 'decor_item', 'templateId': decor_id,
                  'serverPersisted': True, 'localCreated': True, 'position': position}
        entity['positionId'] = self._position_id(entity)
        entities.append(entity)
        state['revision'] = int(state.get('revision', 0)) + 1
        values = self.inventory.list_items(state)
        return {'userDecorItem': {'userDecorItemId': entity['id'], 'decorItemId': decor_id,
                                  'position': {**position, 'id': entity['positionId']}},
                'inventory': values, 'userMaterialTypes': values}

    def update_position(self, state: dict, data: dict) -> dict:
        ident = data.get('positionId')
        position = self._position(state, data)
        matches = [entity for entity in state['world']['entities']
                   if entity.get('templateType') in self.SUPPORTED_KINDS | {'building_task', 'fishing_boat', 'HuntingSledType'}
                   and entity.get('position', {}).get('areaId') == state['areaId']
                   and self._position_id(entity) == ident]
        if len(matches) != 1:
            raise ValueError('Unknown editable position in active area')
        entity = matches[0]
        if any(job.get('status') != 'harvested' and job.get('sourceId') == entity['id']
               for job in state.get('workAreas', {}).values()):
            raise ValueError('Object has unfinished work')
        entity.update(position=position, positionId=ident)
        state['revision'] = int(state.get('revision', 0)) + 1
        return {}

    def delete_decor(self, state: dict, data: dict) -> dict:
        ident = data.get('userDecorItemId')
        deleted = state.setdefault('deletedDecorItems', [])
        if ident in deleted:
            return {}
        entities = state['world']['entities']
        entity = next((value for value in entities if value.get('id') == ident
                       and value.get('templateType') == 'decor_item'
                       and value.get('localCreated')
                       and value.get('position', {}).get('areaId') == state['areaId']), None)
        if entity is None:
            raise ValueError('Unknown saved decoration in active area')
        material = self._item('decor_item', entity['templateId'])['material_type']
        entities.remove(entity)
        # These hidden story objects are cleared from the scene by the client.
        # Their harvested rewards also represent durable story progress.
        work = state.get('workAreas', {}).get(entity.get('sourceWorkAreaId'), {})
        if work.get('taskTypeId') not in {888, 889} or work.get('status') != 'harvested':
            state['inventory'][material] = max(0, state['inventory'].get(material, 0) - 1)
        deleted.append(ident)
        state['revision'] = int(state.get('revision', 0)) + 1
        return {}

    def reconcile_farm_foundations(self, state: dict) -> bool:
        """Remove completed farm markers left by older saves or by scene backfill."""
        entities = state['world']['entities']
        farms = [entity for entity in entities if entity.get('templateType') == 'farm_building'
                 and (entity.get('localCreated') or entity.get('sourceWorkAreaId'))]
        if not farms:
            return False
        # Build Mud Farm House uses the authored site. Placement can round
        # the site position by one unit, as in the original client's request.
        def same_site(foundation: dict, farm: dict) -> bool:
            left, right = foundation.get('position', {}), farm.get('position', {})
            return (left.get('areaId') == right.get('areaId')
                    and all(axis in left and axis in right
                            and abs(left[axis] - right[axis]) <= 1 for axis in ('x', 'y')))

        active = {job.get('sourceId') for job in state.get('workAreas', {}).values()
                  if job.get('status') != 'harvested'}
        stale = {entity['id'] for entity in entities
                 if entity.get('templateType') == 'building_task'
                 and not entity.get('localCreated')
                 and entity['id'] not in active
                 and any(same_site(entity, farm) for farm in farms)
                 and self._item('building_type',
                     self._item('building_task', entity['templateId'])['buildingType']
                 )['entityRef'] == 'farm_building'}
        if not stale:
            return False
        entities[:] = [entity for entity in entities if entity['id'] not in stale]
        state['revision'] = int(state.get('revision', 0)) + 1
        return True

    def completion_definition(self, foundation: dict) -> dict:
        definition=self._item('building_task',foundation['templateId'])
        building=self._item('building_type',definition['buildingType'])
        if building.get('entityRef') not in self.SUPPORTED_KINDS:
            raise NotImplementedError('Building completion schema not recovered: '+str(building.get('entityRef')))
        self._item(building['entityRef'],building['entityID'])
        return building

    def complete(self, state: dict, job: dict) -> list[dict]:
        """Create the authored result object for any supported construction row."""
        entities=state['world']['entities']
        foundation=next((v for v in entities if v.get('id')==job['sourceId']),None) or job.get('sourceSnapshot')
        if foundation is None:raise ValueError('Missing saved construction foundation')
        upgrading=bool(job.get('upgradeDefinitionId'))
        old=copy.deepcopy(foundation) if upgrading else None
        if upgrading:foundation={**foundation,'templateId':int(job['upgradeDefinitionId'])}
        definition=self.completion_definition(foundation)
        kind=definition['entityRef'];template_id=int(definition['entityID'])
        result={'id':'local-building-'+uuid.uuid4().hex,'templateType':kind,
                'templateId':template_id,'position':copy.deepcopy(foundation['position']),
                'serverPersisted':True,'localCreated':True,'sourceWorkAreaId':job['id']}
        if upgrading:
            result.update(id=old['id'],position=copy.deepcopy(old['position']))
            previous_task=self._item('building_task',self._item('building_task',job['upgradeDefinitionId'])['parentId'])
            previous=self._item('building_type',previous_task['buildingType'])
            if str(previous.get('materialType'))!=str(definition.get('materialType')):
                key=str(previous['materialType'])
                state['inventory'][key]=max(0,state['inventory'].get(key,0)-1)
        elif kind in {'container_type','workshop'}:
            construction=self._item('building_task',foundation['templateId'])
            parent=construction.get('parentId','-1')
            previous=definition if parent=='-1' else self._item(
                'building_type',self._item('building_task',parent)['buildingType'])
            matches=[v for v in entities if v.get('templateType')==kind
                     and v.get('templateId')==int(previous['entityID'])
                     and v.get('position', {}).get('areaId')==result['position']['areaId']]
            if len(matches)>1:raise ValueError('Ambiguous storage upgrade target')
            if matches:
                old=matches[0]
                result.update(id=old['id'],position=copy.deepcopy(old['position']))
                entities[:]=[v for v in entities if v.get('id')!=old['id']]
                if str(previous.get('materialType'))!=str(definition.get('materialType')):
                    key=str(previous['materialType'])
                    state['inventory'][key]=max(0,state['inventory'].get(key,0)-1)
        result['positionId']=str(old.get('positionId') or old.get('position',{}).get('id') or
                                 old['id']+'-position') if old else foundation['id']+'-position'
        if kind=='fun_building':
            fun=self._item('fun_building',template_id)
            activity=self._item('fun_activity',fun['funActivity'])
            uses=int(activity['itemWear'])
            if uses==-1 and activity.get('unbreakable')=='1':uses=1_000_000_000
            if uses<=0:raise NotImplementedError('Nonpositive fun-building use counter is not recovered')
            result['amount']=uses
        elif kind=='fire_type':
            result.update(isBurning=0,startsAt=0,endsAt=0,oilAppliedAt=0)
        elif kind=='shelter':
            if upgrading:
                result['beds'] = copy.deepcopy(old.get('beds', []))
                result['happinessCollectedAt'] = old.get('happinessCollectedAt', 0)
            capacity = self.habitats.capacities.get(template_id)
            if capacity is None and not result.get('beds'):
                raise NotImplementedError('Shelter bed capacity is not recovered for this template')
            if capacity is not None and sum(bool(bed.get('villagerId'))
                                           for bed in result.get('beds', [])) > capacity:
                raise ValueError('Upgraded shelter cannot hold its saved occupants')
            self.habitats.initialize(result)
        entities[:]=[v for v in entities if v.get('id')!=foundation['id']]+[result]
        if kind == 'farm_building':
            self.reconcile_farm_foundations(state)
        response={'id':result['id'],'entityId':result['templateId']}
        if kind=='shelter':
            response.update(beds=copy.deepcopy(result['beds']),
                            happinessCollectedAt=result['happinessCollectedAt'],
                            position={**result['position'],'id':self._position_id(result)})
        return [response]

    def _require_plot_capacity(self, state: dict, area_id: int) -> None:
        entities = state['world']['entities']
        area_entities = [entity for entity in entities
                         if entity.get('position', {}).get('areaId') == area_id]
        capacity = sum(int(self._item('farm_building', entity['templateId'])['numPlots'])
                       for entity in area_entities if entity.get('templateType') == 'farm_building')

        def is_plot_foundation(entity: dict) -> bool:
            if entity.get('templateType') != 'building_task':
                return False
            task = self._item('building_task', entity['templateId'])
            return self._item('building_type', task['buildingType'])['entityRef'] == 'farming_plot'

        used = sum(entity.get('templateType') == 'farming_plot' or is_plot_foundation(entity)
                   for entity in area_entities)
        # Older saves can still have a paid build whose visual foundation was removed.
        entity_ids = {entity['id'] for entity in entities}
        used += sum(job.get('family') == '2' and job.get('status') != 'harvested'
                    and job.get('sourceId') not in entity_ids
                    and job.get('sourceSnapshot', {}).get('position', {}).get('areaId') == area_id
                    and is_plot_foundation(job.get('sourceSnapshot', {}))
                    for job in state.get('workAreas', {}).values())
        if used >= capacity:
            raise ValueError('Upgrade the farm house before adding another plot')

    def place_farm_plot(self, state: dict, data: dict) -> dict:
        position = self._position(state, data)
        entities = state['world']['entities']
        # Script 2732 creates template 0, then the listener attaches saved IDs.
        self._item('farming_plot', 0)
        plot = next((entity for entity in entities if entity.get('templateType') == 'farming_plot'
                     and all(entity.get('position', {}).get(key) == value
                             for key, value in position.items())), None)
        if plot is None:
            self._require_plot_capacity(state, position['areaId'])
            ident = 'local-plot-' + uuid.uuid4().hex
            plot = {'id': ident, 'templateType': 'farming_plot', 'templateId': 0,
                    'serverPersisted': True, 'localCreated': True,
                    'position': position, 'positionId': ident + '-position'}
            entities.append(plot)
            state['revision'] = int(state.get('revision', 0)) + 1
        return {'userFarmPlot': {'userFarmPlotId': plot['id'],
                                 'position': {**plot['position'], 'id': self._position_id(plot)}}}

    def place_area_equipment(self, state: dict, service: str, data: dict) -> dict:
        area, building, slots, kind, template_id, response_key = self.AREA_EQUIPMENT[service]
        position = self._position(state, data)
        if position['areaId'] != area:
            raise ValueError('This equipment belongs in a different village')
        self._item(kind, template_id)
        entities = state['world']['entities']
        area_entities = [entity for entity in entities if entity.get('position', {}).get('areaId') == area]
        equipment = [entity for entity in area_entities if entity.get('templateType') == kind]
        placed = next((entity for entity in equipment
                       if all(entity['position'].get(key) == value for key, value in position.items())), None)
        if placed is None:
            capacity = max((int(self._item(building, entity['templateId'])[slots])
                            for entity in area_entities if entity.get('templateType') == building), default=0)
            if len(equipment) >= capacity:
                raise ValueError('A restored building with a free equipment slot is required')
            ident = 'local-equipment-' + uuid.uuid4().hex
            placed = {'id': ident, 'templateType': kind, 'templateId': template_id,
                      'serverPersisted': True, 'localCreated': True, 'position': position,
                      'positionId': ident + '-position'}
            entities.append(placed)
            state['revision'] = int(state.get('revision', 0)) + 1
        return {response_key: {response_key + 'Id': placed['id'],
                               'position': {**placed['position'], 'id': self._position_id(placed)}}}

    def reconcile_boulder_foundation(self, state: dict) -> None:
        if int(state.get('user', {}).get('maxAreaId', 1)) < 2:
            return
        entities = state['world']['entities']
        obsolete = {entity['id'] for entity in entities
                    if entity.get('templateType') == 'building_task' and entity.get('templateId') == 137}
        if obsolete:
            entities[:] = [entity for entity in entities if entity['id'] not in obsolete]
            deleted = state.setdefault('deletedFoundations', [])
            deleted.extend(sorted(obsolete - set(deleted)))
            state['revision'] = int(state.get('revision', 0)) + 1

    def place(self, state: dict, data: dict) -> dict:
        raw = data.get('buildingTaskTypeId')
        if isinstance(raw, bool) or not str(raw).isdigit():
            raise ValueError('Invalid foundation type')
        task_id = int(raw)
        if task_id == 137 and int(state.get('user', {}).get('maxAreaId', 1)) >= 2:
            raise ValueError('Breaking Boulder has already been completed')
        definition = self._item('building_task', task_id)
        position = self._position(state, data)
        if definition.get('allowMultiple') == '0' and any(
            job.get('status') != 'harvested' and job.get('sourceSnapshot', {}).get('templateId') == task_id
            for job in state.get('workAreas', {}).values()
        ):
            raise ValueError('Building type is already under construction')
        entities = state['world']['entities']
        for entity in entities:
            if entity.get('templateType') == 'building_task' and entity.get('templateId') == task_id:
                if entity.get('position') == position:
                    return {'userBuildingTask': self._placement(entity)}
                if definition.get('allowMultiple') == '0':
                    raise ValueError('Foundation type already placed')

        building = self._item('building_type', definition['buildingType'])
        if building.get('entityRef') == 'farming_plot':
            self._require_plot_capacity(state, position['areaId'])

        existing = [entity for entity in entities
                    if entity.get('templateType') == building['entityRef']
                    and entity.get('templateId') == int(building['entityID'])]
        if definition.get('allowMultiple') == '0' and existing:
            placeholder = (building['entityRef'] in {'container_type', 'workshop'} and len(existing) == 1
                           and not existing[0].get('localCreated')
                           and state.get('inventory', {}).get(str(building.get('materialType')), 0) == 0)
            if not placeholder:
                raise ValueError('Building type already exists')

        entity = {'id': 'local-foundation-' + uuid.uuid4().hex,
                  'templateType': 'building_task', 'templateId': task_id,
                  'serverPersisted': True, 'localCreated': True, 'position': position}
        entities.append(entity)
        state['revision'] = int(state.get('revision', 0)) + 1
        return {'userBuildingTask': self._placement(entity)}

    def delete(self, state: dict, data: dict) -> dict:
        ident = data.get('userBuildingTaskId')
        if not isinstance(ident, str) or not ident:
            raise ValueError('Foundation identifier required')
        deleted = state.setdefault('deletedFoundations', [])
        if ident in deleted:
            return {}
        entities = state['world']['entities']
        foundation = next((entity for entity in entities if entity.get('id') == ident
                           and entity.get('templateType') == 'building_task'), None)
        if foundation is None:
            if any(job.get('sourceId') == ident and job.get('family') == '2'
                   and job.get('status') == 'harvested' for job in state.get('workAreas', {}).values()):
                deleted.append(ident)
                state['revision'] = int(state.get('revision', 0)) + 1
                return {}
            raise ValueError('Unknown foundation')
        for job in state.get('workAreas', {}).values():
            if job.get('status') != 'harvested' and job.get('sourceId') == ident:
                job['sourceSnapshot'] = dict(foundation)
        state['world']['entities'] = [entity for entity in entities if entity.get('id') != ident]
        deleted.append(ident)
        state['revision'] = int(state.get('revision', 0)) + 1
        return {}

    def delete_fun(self, state: dict, data: dict) -> dict:
        ident = data.get('userFunBuildingTypeId')
        if not isinstance(ident, str) or not ident:
            raise ValueError('Fun building identifier required')
        deleted = state.setdefault('deletedFunBuildings', [])
        if ident in deleted:
            return {}
        entities = state['world']['entities']
        entity = next((value for value in entities if value.get('id') == ident
                       and value.get('templateType') == 'fun_building'), None)
        if entity is None:
            raise ValueError('Unknown fun building')
        if any(job.get('status') != 'harvested' and job.get('sourceId') == ident
               for job in state.get('workAreas', {}).values()):
            raise ValueError('Building is in use')
        definition = self._item('fun_building', entity['templateId'])
        material = str(definition['materialType'])
        state['world']['entities'] = [value for value in entities if value.get('id') != ident]
        state['inventory'][material] = max(0, state['inventory'].get(material, 0) - 1)
        if not state['inventory'][material]:
            state['wants'] = [want for want in state.get('wants', [])
                              if str(want.get('MaterialID')) != material]
        deleted.append(ident)
        state['revision'] = int(state.get('revision', 0)) + 1
        return {}
