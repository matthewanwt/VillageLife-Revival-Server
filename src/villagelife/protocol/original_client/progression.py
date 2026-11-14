"""Replay authored FTUE inventory and XP assignments at saved checkpoints."""
from __future__ import annotations

from .inventory import spend_gems
import json
import math
import struct
import copy
from decimal import Decimal
from .catalog import OriginalDefinitions


class OriginalProgressionRules:
    def __init__(self, definitions: OriginalDefinitions):
        self.defs = definitions

    def sync_script_assignments(self, save: dict) -> bool:
        state = save.get('normal')
        if not isinstance(state, dict):
            return False
        settings = save.get('gameSettings') or {}
        checkpoint = str(settings.get('activeSequenceId', '410'))
        steps = self.defs.rows('seq_state_tablet_ftue')
        targets = [row for row in steps if str(row.get('persist')) == checkpoint]
        complete = str(settings.get('isFtueComplete', '')).lower() in {'1', 'true'}
        if checkpoint == '-1' and complete:
            limit = max(Decimal(row['order']) for row in steps)
        elif targets:
            limit = max(Decimal(row['order']) for row in targets)
        else:
            return False
        effects = state.setdefault('scriptEffects', {})
        inventory_done = effects.setdefault('inventoryAssignments', [])
        xp_done = effects.setdefault('shrineXp', [])
        pending_inventory = [row for row in steps if row['sequenceType'] == '64'
                             and Decimal('3') <= Decimal(row['order']) <= limit
                             and row['id'] not in inventory_done]
        pending_xp = [row for row in steps if row['sequenceType'] == '114'
                      and Decimal('3') <= Decimal(row['order']) <= limit
                      and row['id'] not in xp_done]
        if not pending_inventory and not pending_xp:
            return False
        preserve_xp = complete and (int(state['user']['userLevelID']) > 1
                                    or state['user']['xp'] != 0)
        # Before FTUE completion the authored sequence writes exact inventory
        # snapshots. After completion, retire any missing old grants without
        # resetting earned stock, purchases, or currency.
        for row in sorted(pending_inventory, key=lambda item: Decimal(item['order'])):
            if not complete:
                values = json.loads(row['dataJSON']).get('inventory', {})
                state['inventory'].update({str(key): int(value) for key, value in values.items()
                                           if str(key) != '323' or not state.get('startingGemsGranted')})
            inventory_done.append(row['id'])
        for row in sorted(pending_xp, key=lambda item: Decimal(item['order'])):
            amount = int(Decimal(json.loads(row['dataJSON'])['xp']))
            if not preserve_xp:
                state['user']['xp'] = max(0, int(state['user'].get('xp', 0)) + amount)
            xp_done.append(row['id'])
        state['revision'] = int(state.get('revision', 0)) + 1
        return True

    @staticmethod
    def _f32(value: float) -> float:
        return struct.unpack('<f', struct.pack('<f', value))[0]

    def _paid_price(self, state: dict) -> int:
        f=self._f32
        current=int(state['user']['userLevelID'])
        levels={int(row['levelNumber']):row for row in self.defs.rows('user_level')}
        level=levels[current]
        threshold=f(float(level['experienceRequired']))
        previous=f(float(levels[current-1]['experienceRequired'])) if current>1 else 0.0
        xp=f(float(state['user'].get('xp',0)))
        globals_={row['label']:row['value'] for row in self.defs.rows('global')}
        minimum=f(float(globals_['LevelupMinGemCost']))
        if xp>=threshold:return 0
        span=f(threshold-previous)
        if span<=0:raise ValueError('Invalid original level XP interval')
        fraction=f(f(float(level['fillCost'])-minimum)/span)
        remaining=f(span-f(xp-previous))
        return max(0,math.ceil(f(minimum+f(fraction*remaining))))

    def increase_level(self, state: dict, data: dict, receipt: str,
                       economy, rng: dict) -> dict:
        paid_value=str(data.get('IsPaid','false')).lower()
        if paid_value not in {'true','false'}:raise ValueError('Invalid paid level-up flag')
        paid=paid_value=='true'
        if paid and not receipt:raise ValueError('Paid level-up requires a request receipt')
        receipts=state.setdefault('levelCallReceipts',{})
        if receipt in receipts:
            prior=receipts[receipt]
            if prior['paid']!=paid:raise ValueError('Level-up request identifier reused')
            return copy.deepcopy(prior['response'])
        current=int(state['user']['userLevelID'])
        levels={int(row['levelNumber']):row for row in self.defs.rows('user_level')}
        level=levels.get(current);target=levels.get(current+1)
        if level is None or target is None:raise ValueError('No next level in original table')
        cost=self._paid_price(state) if paid else 0
        spend_gems(state,cost)
        if not paid and state['user'].get('xp',0)<int(level['experienceRequired']):
            previous=state.get('levelReceipts',{}).get(str(current))
            if previous:return copy.deepcopy(previous)
            raise ValueError('Not enough shrine XP')
        rewards=[]
        if target.get('rewardSetId1','0')!='0':
            for item in self.defs.rows('reward_set_item'):
                if item['setId']!=target['rewardSetId1']:continue
                if Decimal(item['chance'])!=1:
                    raise NotImplementedError('Level reward probability rule not recovered')
                key=str(item['materialType']);amount=float(item['quantity'])
                state['inventory'][key]=state['inventory'].get(key,0)+amount
                rewards.append({'MaterialTypeId':int(key),'Amount':amount})
        if paid:state['user']['xp']=max(state['user'].get('xp',0),int(level['experienceRequired']))
        cap=int(target['populationCap'])
        state['user'].update(userLevel=current+1,userLevelID=current+1,populationCap=cap)
        model=economy._draw_wheel(6 if current+1==2 else 3,'1',rng)
        for reward in model['MaterialTypes']:
            key=str(reward['MaterialTypeId'])
            state['inventory'][key]=state['inventory'].get(key,0)+reward['Amount']
        response={'result':{'Rewards':rewards,'PopulationCap':cap,
                            'WheelOfFortuneModel':model}}
        state.setdefault('levelReceipts',{})[str(current+1)]=copy.deepcopy(response)
        receipts[receipt]={'paid':paid,'gemsSpent':cost,'response':copy.deepcopy(response)}
        state.setdefault('rules',{})['level_up']={
            'evidence':'authored user_level thresholds, populationCap, rewardSetId1 and WofSet level prizes',
            'status':'authored table rule'}
        state['revision']=int(state.get('revision',0))+1
        return response
