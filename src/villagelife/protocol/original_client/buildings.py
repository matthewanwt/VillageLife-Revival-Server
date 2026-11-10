"""Authored foundation placement and removal for the original client."""
from __future__ import annotations

import math
import uuid

from .catalog import OriginalDefinitions


class OriginalBuildingRules:
    def __init__(self, definitions: OriginalDefinitions):
        self.defs = definitions

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
        if not 0 <= result['x'] <= 10000 or not 0 <= result['y'] <= 10000:
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

    def place(self, state: dict, data: dict) -> dict:
        raw = data.get('buildingTaskTypeId')
        if isinstance(raw, bool) or not str(raw).isdigit():
            raise ValueError('Invalid foundation type')
        task_id = int(raw)
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
            capacity = sum(int(self._item('farm_building', entity['templateId'])['numPlots'])
                           for entity in entities if entity.get('templateType') == 'farm_building'
                           and entity.get('position', {}).get('areaId') == position['areaId'])
            used = sum(entity.get('templateType') == 'farming_plot' or
                       (entity.get('templateType') == 'building_task' and
                        self._item('building_type', self._item('building_task', entity['templateId'])['buildingType'])
                        .get('entityRef') == 'farming_plot')
                       for entity in entities if entity.get('position', {}).get('areaId') == position['areaId'])
            entity_ids = {entity['id'] for entity in entities}
            used += sum(job.get('family') == '2' and job.get('status') != 'harvested'
                        and job.get('sourceId') not in entity_ids
                        and job.get('sourceSnapshot', {}).get('position', {}).get('areaId') == position['areaId']
                        and self._item('building_type', self._item('building_task',
                            job['sourceSnapshot']['templateId'])['buildingType']).get('entityRef') == 'farming_plot'
                        for job in state.get('workAreas', {}).values())
            if used >= capacity:
                raise ValueError('Upgrade the farm house before adding another plot')

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
