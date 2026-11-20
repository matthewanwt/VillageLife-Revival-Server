"""Storage progression is local even when an imported inventory is global."""
import copy
import unittest

from villagelife.protocol.original_client.buildings import OriginalBuildingRules
from villagelife.protocol.original_client.inventory import OriginalInventoryRules


class Definitions:
    def rows(self, table):
        return {
            'building_task': [
                {'id':'1','buildingType':'1','parentId':'-1','allowMultiple':'0'},
                {'id':'2','buildingType':'2','parentId':'1','allowMultiple':'0'},
            ],
            'building_type': [
                {'id':'1','entityRef':'container_type','entityID':'1','materialType':'100'},
                {'id':'2','entityRef':'container_type','entityID':'2','materialType':'101'},
            ],
            'material_type': [
                {'id':str(key),'learnDurationSec':'0'} for key in (100,101,231,232,1536)
            ],
        }.get(table, [])

    def item(self, table, ident):
        return next(row for row in self.rows(table) if row['id'] == str(ident))


class AreaStorageTests(unittest.TestCase):
    def setUp(self):
        self.defs = Definitions()
        self.inventory = OriginalInventoryRules(self.defs)
        self.state = {
            'areaId':3,'user':{'maxAreaId':3},'inventory':{'100':1,'101':1},
            'world':{'entities':[
                {'id':'woodland','templateType':'container_type','templateId':2,
                 'localCreated':True,'position':{'areaId':1}},
                {'id':'riverside','templateType':'container_type','templateId':1,
                 'localCreated':True,'position':{'areaId':2}},
            ]},
        }

    def quantities(self):
        return {str(row['materialTypeId']):row['amount']
                for row in self.inventory.list_items(self.state)}

    def test_travel_projects_local_tiers_without_rewriting_imported_stock(self):
        before = copy.deepcopy(self.state['inventory'])
        self.assertEqual((self.quantities()['100'],self.quantities()['101']), (0,0))
        self.state['areaId'] = 2
        self.assertEqual((self.quantities()['100'],self.quantities()['101']), (1,0))
        self.assertEqual(self.inventory.requirement_quantity(
            self.state,'101',self.inventory.milestones(self.state)), 0)
        self.state['areaId'] = 1
        self.assertEqual((self.quantities()['100'],self.quantities()['101']), (1,1))
        self.assertEqual(self.state['inventory'], before)

    def test_absent_global_marker_is_explicitly_cleared_after_travel(self):
        self.state['inventory'] = {}
        self.state['areaId'] = 1
        self.assertEqual(self.quantities()['101'], 1)
        self.state['areaId'] = 3
        self.assertEqual((self.quantities()['100'],self.quantities()['101']), (0,0))

    def test_foundation_and_construction_in_other_areas_do_not_block_placement(self):
        self.state['world']['entities'].append(
            {'id':'other-foundation','templateType':'building_task','templateId':1,
             'position':{'areaId':2,'x':10,'y':20,'rotation':0}})
        self.state['workAreas'] = {'old': {
            'status':'working','sourceSnapshot':{'templateId':1},'position':{'areaId':1}}}
        buildings = OriginalBuildingRules(self.defs, self.inventory)
        request = {'buildingTaskTypeId':1,'areaId':3,'x':10,'y':20,'rotation':0}
        reply = buildings.place(self.state, request)
        self.assertEqual(buildings.place(self.state, request), reply)
        with self.assertRaisesRegex(ValueError, 'already placed'):
            buildings.place(self.state, {**request,'x':30})
