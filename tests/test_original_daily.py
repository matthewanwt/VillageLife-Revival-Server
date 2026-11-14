import copy
import unittest

from villagelife.protocol.original_client.habitats import OriginalHabitatRules
from villagelife.protocol.original_client.wants import OriginalWantRules


class Definitions:
    def rows(self, table):
        return {
            'global': [{'label': key, 'value': value} for key,value in {
                'hours_per_year': '24', 'hungerIntervalSec': '600', 'thirstIntervalSec': '600',
                'energyReplenishDelaySec': '180', 'funWantDelay': '60',
            }.items()],
            'villager_type': [
                {'id':'1','name':'Adult','minAge':'18','maxAge':'39','genderType':'0','maxEnergy':'30','canWork':'1'},
                {'id':'3','name':'Baby','minAge':'0','maxAge':'1','genderType':'0','maxEnergy':'0','canWork':'0'},
                {'id':'10','name':'Child','minAge':'5','maxAge':'12','genderType':'0','maxEnergy':'15','canWork':'0'},
                {'id':'16','name':'Toddler','minAge':'2','maxAge':'4','genderType':'0','maxEnergy':'0','canWork':'0'},
            ],
            'villager_set_item': [
                {'villagerSet':'6','villagerType':'3'}, {'villagerSet':'6','villagerType':'16'},
                {'villagerSet':'12','villagerType':'1'},
            ],
            'interactive_activity': [
                {'id':'1','isActive':'1','buildingType':'0','relationSet':'0',
                 'requesterVillagerSet':'6','supplierVillagerSet':'12','repeatDelaySecs':'20000',
                 'durationSecs':'30','materialType':'494','requirementSet':'291','rewardSet':'0',
                 'xpReward':'50','requesterEnergyUsed':'0','supplierEnergyUsed':'0'},
            ],
            'requirement_set_item': [
                {'requirementSet':'291','materialType':'487','quantity':'4','quantityUsed':'4'},
            ],
            'material_category': [{'id':'8','parentId':'41'}],
            'material_type': [
                {'id':'6','xpRewardPerUnitConsumed':'2'}, {'id':'107','xpRewardPerUnitConsumed':'4','categoryId':'8'},
                {'id':'16','categoryId':'8','unlockLevel':'3'},
                {'id':'487'}, {'id':'231'},
            ],
            'user_level': [{'levelNumber':'3','villagerXPCapacity':'28'}],
        }.get(table, [])

    def item(self, table, ident):
        return next(row for row in self.rows(table) if row['id'] == str(ident))


class DailyLifeTests(unittest.TestCase):
    def setUp(self):
        self.defs = Definitions()
        self.rules = OriginalWantRules(self.defs)
        self.adult = {'id':'caregiver','templateType':'villager_type','templateId':1,
                      'startAge':21,'bornAt':1000,'energyLevel':10,'energyTimeStamp':1000,
                      'position':{'areaId':1},'xp':0}
        self.baby = {'id':'baby','templateType':'villager_type','templateId':3,
                     'startAge':1,'bornAt':1000,'position':{'areaId':1},'xp':0}
        self.state = {'areaId':1,'world':{'entities':[self.adult,self.baby]},
                      'user':{'userLevelID':3},'inventory':{'6':5,'107':5,'487':8}}

    def generate(self, name, at=1000):
        return self.rules.generate(self.state, f'ClientWant/Generate{name}Wants', at)['result']

    def test_food_varies_after_fulfilment_and_four_year_old_has_no_shelter_wish(self):
        from villagelife.protocol.original_client.daily import satisfy_wants

        self.state['inventory']['16'] = 4
        self.baby.update(startAge=4, templateId=16)
        first, = self.generate('Food')
        self.assertEqual(first['MaterialID'], 107)
        self.assertEqual(self.generate('Food', 1100), [first])
        satisfy_wants(self.state, {'caregiver'}, 2, 1100)
        second, = self.generate('Food', 1700)
        self.assertEqual(second['MaterialID'], 16)
        shelter = [wish for wish in self.generate('Shelter') if wish['wantableCategoryType'] == 6]
        self.assertEqual([wish['VillagerStringID'] for wish in shelter], ['caregiver'])
        later = self.generate('Shelter', 1000+86400)
        self.assertTrue(any(w['VillagerStringID']=='baby' and w['wantableCategoryType']==6 for w in later))

    def test_infant_uses_caregiver_wish_and_replay_spends_once(self):
        self.assertEqual([w['VillagerStringID'] for w in self.generate('Food')], ['caregiver'])
        wishes = self.generate('Interactive')
        bottle, = [w for w in wishes if w['MaterialID']==494]
        self.assertEqual(bottle['VillagerStringID'], 'baby')
        self.assertEqual(self.generate('Interactive'), wishes)
        data = {'requesterVillagerId':'baby','supplierVillagerId':'caregiver','activityId':1}
        reply = self.rules.interactive.perform(self.state,data,1000)
        self.assertEqual(reply['SatisfiedWantModels'][0]['WantId'], bottle['WantId'])
        self.assertEqual(self.state['inventory']['487'], 4)
        self.assertEqual(self.baby['xp'], 28)
        self.assertEqual(self.rules.interactive.perform(self.state,data,1001),reply)
        self.assertFalse(any(w['MaterialID']==494 for w in self.generate('Interactive',1002)))
        self.assertTrue(any(w['VillagerStringID']=='baby' and w['MaterialID']==107
                            for w in self.generate('Food',1000+4*86400)))

    def test_housing_assignment_clears_wish_and_offline_login_is_bounded(self):
        wish, = self.generate('Shelter')
        home = {'id':'home','templateType':'shelter','templateId':0,'localCreated':True,
                'position':{'areaId':1},'beds':[{'id':'bed','villagerId':'','shelterSlotID':12}]}
        self.state['world']['entities'].append(home)
        habitats = OriginalHabitatRules(self.defs)
        result,_ = habitats.operate(self.state,'ClientUserShelterService/AssignBedToVillager',
                                    {'villagerId':'caregiver','shelterBedId':'bed'},1000)
        self.assertEqual(result['SatisfiedWantModels'][0]['WantId'],wish['WantId'])
        self.rules.on_login(self.state,1000)
        self.rules.on_login(self.state,1800)
        self.assertEqual(self.state['offlineConsumption'],
                         {'FoodQuantity':1,'DrinksQuantity':1,'TotalXp':6})
        self.rules.on_login(self.state,1801)
        self.assertEqual((self.state['inventory']['6'],self.state['inventory']['107']),(4,4))
        view = copy.deepcopy(self.adult)
        self.rules.daily.recover_energy(view,1360)
        self.assertEqual(view['energyLevel'],12)
        self.assertEqual(self.adult['energyLevel'],10)

    def test_food_and_water_cooldowns_repeat_independently_after_reopen(self):
        from villagelife.protocol.original_client.daily import satisfy_wants
        import json

        food, = self.generate('Food')
        water = next(w for w in self.generate('Water') if w['wantableCategoryType'] == 1)
        satisfy_wants(self.state, {'caregiver'}, 2, 1100)
        satisfy_wants(self.state, {'caregiver'}, 1, 1150)
        self.state = json.loads(json.dumps(self.state))
        self.assertEqual(self.generate('Food', 1699), [])
        next_food, = self.generate('Food', 1700)
        self.assertNotEqual(next_food['WantId'], food['WantId'])
        self.assertEqual(self.generate('Water', 1749), [next_food])
        next_water = next(w for w in self.generate('Water', 1750)
                          if w['wantableCategoryType'] == 1)
        self.assertNotEqual(next_water['WantId'], water['WantId'])
        self.assertEqual(self.generate('Water', 1751), [next_food, next_water])
