"""Verified local economy rules for the original-client compatibility API.

All prices and prizes are read from the user's extracted game definitions.  No
commercial payment is performed: gem balances are part of the local save only.
"""
from __future__ import annotations

import copy
import math
import struct
from decimal import Decimal, ROUND_HALF_UP

from .catalog import OriginalDefinitions
from .inventory import OriginalInventoryRules
from .randomness import new_state, randbelow


class OriginalEconomyRules:
    def __init__(self, definitions: OriginalDefinitions, inventory: OriginalInventoryRules | None = None):
        self.defs = definitions
        self.inventory = inventory or OriginalInventoryRules(definitions)

    @staticmethod
    def _number(value) -> Decimal:
        number = Decimal(str(value))
        if not number.is_finite() or number < 0:
            raise ValueError('Invalid material amount')
        return number

    @staticmethod
    def _f32(value: float) -> float:
        return struct.unpack('<f', struct.pack('<f', value))[0]

    def _item(self, table: str, ident: int | str) -> dict:
        return self.defs.item(table, ident)

    def _inventory_response(self, state: dict) -> dict:
        items = self.inventory.list_items(state)
        return {'inventory': items, 'userMaterialTypes': items,
                'result': {'inventory': items, 'userMaterialTypes': items}}

    def _remember(self, state: dict, bucket: str, key: str, request: dict) -> bool:
        if not key:
            raise ValueError('Original call identifier required')
        previous = state.setdefault(bucket, {}).get(key)
        if previous is not None:
            if previous != request:
                raise ValueError('Original call identifier reused with different content')
            return False
        state[bucket][key] = copy.deepcopy(request)
        return True

    def buy_material(self, state: dict, data: dict, receipt: str) -> dict:
        material_id, amount = data.get('materialTypeId'), data.get('amount')
        if isinstance(material_id, bool) or not isinstance(material_id, int) or isinstance(amount, bool) or not isinstance(amount, int):
            raise ValueError('Integer material and quantity required')
        material = self._item('material_type', material_id)
        if not int(material['minPurchasable']) <= amount <= int(material['maxPurchasable']):
            raise ValueError('Quantity outside original purchase bounds')
        if int(material['unlockLevel']) > int(state['user']['userLevelID']):
            raise ValueError('Material not unlocked at this level')
        ratio = self._f32(float(material.get('gemsRatio') or 0))
        if not math.isfinite(ratio) or ratio <= 0:
            raise NotImplementedError('Material has no recovered direct gem price')
        epsilon = struct.unpack('<f', bytes.fromhex('a4707d3f'))[0]
        quantity = self._f32(math.floor(self._f32(self._f32(amount) + epsilon)))
        price = math.floor(self._f32(epsilon + self._f32(math.floor(self._f32(epsilon + self._f32(ratio * quantity))))))
        if price <= 0:
            raise NotImplementedError('Original calculation gives no positive direct gem price')
        request = {'materialTypeId': material_id, 'amount': amount, 'gemsSpent': price}
        if not self._remember(state, 'materialPurchaseReceipts', receipt, request):
            return self._inventory_response(state)
        gems = self._number(state['inventory'].get('323', 0))
        if gems < price:
            del state['materialPurchaseReceipts'][receipt]
            raise ValueError('Not enough gems')
        state['inventory']['323'] = float(gems - price)
        state['inventory'][str(material_id)] = float(self._number(state['inventory'].get(str(material_id), 0)) + amount)
        state['revision'] = int(state.get('revision', 0)) + 1
        return self._inventory_response(state)

    def buy_store_item(self, state: dict, data: dict, receipt: str) -> dict:
        item_id, multiples = data.get('storeItemId'), data.get('multiples')
        if isinstance(item_id, bool) or not isinstance(item_id, int) or isinstance(multiples, bool) or not isinstance(multiples, int) or not 1 <= multiples <= 100:
            raise ValueError('Store item and bounded positive multiples required')
        item = self._item('store_item', item_id)
        cost, amount = int(item['price_gems']) * multiples, int(item['qty']) * multiples
        if cost <= 0 or amount <= 0:
            raise ValueError('Invalid original store definition')
        request = {'storeItemId': item_id, 'multiples': multiples, 'gemsSpent': cost}
        if not self._remember(state, 'storePurchaseReceipts', receipt, request):
            return self._inventory_response(state)
        if self._number(state['inventory'].get('323', 0)) < cost:
            del state['storePurchaseReceipts'][receipt]
            raise ValueError('Not enough gems for this store item')
        state['inventory']['323'] = float(self._number(state['inventory']['323']) - cost)
        key = str(item['material_type'])
        state['inventory'][key] = float(self._number(state['inventory'].get(key, 0)) + amount)
        state['revision'] = int(state.get('revision', 0)) + 1
        return self._inventory_response(state)

    def sell_material(self, state: dict, data: dict, receipt: str) -> dict:
        material_id, amount = data.get('materialTypeId'), data.get('amount')
        if isinstance(material_id, bool) or not isinstance(material_id, int) or isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
            raise ValueError('Positive integer sale quantity required')
        material = self._item('material_type', material_id)
        ratio = int(material.get('coinsRatio') or 0)
        if ratio <= 0 or material_id in {323, 325}:
            raise ValueError('This original material cannot be sold for coins')
        request = {'materialTypeId': material_id, 'amount': amount, 'coinsGranted': ratio * amount}
        if not self._remember(state, 'materialSaleReceipts', receipt, request):
            return self._inventory_response(state)
        key = str(material_id)
        if self._number(state['inventory'].get(key, 0)) < amount:
            del state['materialSaleReceipts'][receipt]
            raise ValueError('Not enough material to sell')
        state['inventory'][key] = float(self._number(state['inventory'][key]) - amount)
        state['inventory']['325'] = float(self._number(state['inventory'].get('325', 0)) + ratio * amount)
        state['revision'] = int(state.get('revision', 0)) + 1
        return self._inventory_response(state)

    def _choose(self, rows: list[dict], field: str, rng: dict) -> dict:
        rows = [row for row in rows if Decimal(row[field]) > 0]
        weights = [int(Decimal(row[field]) * 1_000_000_000) for row in rows]
        total = sum(weights)
        if not total:
            raise ValueError('Original reward pool has no positive weights')
        ticket = randbelow(rng, total)
        for row, weight in zip(rows, weights):
            if ticket < weight:
                return row
            ticket -= weight
        raise AssertionError('Reward selection exhausted')

    def _draw_wheel(self, set_id: int, multiplier, rng: dict) -> dict:
        item = self._choose([row for row in self.defs.rows('WofSetItem') if row['WofSet'] == str(set_id)], 'Chance', rng)
        if item['MaterialType'] != '0':
            prizes = [{'materialType': item['MaterialType'], 'quantity': item['Quantity']}]
        else:
            prizes = [self._choose([row for row in self.defs.rows('reward_set_item') if row['setId'] == item['RewardSet']], 'chance', rng)]
        rewards = []
        for prize in prizes:
            amount = Decimal(prize['quantity']) * (Decimal(str(multiplier)) if item['ShouldMultiply'] == '1' else 1)
            amount = int(amount.to_integral_value(rounding=ROUND_HALF_UP))
            if amount > 0:
                rewards.append({'MaterialTypeId': int(prize['materialType']), 'Amount': amount})
        return {'ResultIndex': int(item['SlotIndex']), 'MaterialTypes': rewards}

    def daily_spin(self, state: dict, data: dict, at: int, receipt: str, rng: dict | None = None) -> dict:
        if isinstance(data.get('WheelOfFortuneTypeID'), bool) or data.get('WheelOfFortuneTypeID') != 1:
            raise ValueError('This path requires a daily spin')
        if not receipt:
            raise ValueError('Fortune request receipt required')
        prior = state.setdefault('fortuneReceipts', {}).get(receipt)
        if prior is not None:
            return copy.deepcopy(prior)
        if at < int(state['user'].get('NextDailySpinAt', 0)):
            raise ValueError('Daily spin is not ready')
        old = state.get('dailySpin', {})
        increment = (int(old.get('increment', 0)) % 7 + 1) if old and at - int(old['at']) < 172800 else 1
        definition = next((row for row in self.defs.rows('WofIncrement') if row['Increment'] == str(increment) and row['WofSet'] in {'2', '7'}), None)
        if definition is None:
            raise KeyError('Missing original daily wheel increment')
        model = self._draw_wheel(int(definition['WofSet']), definition['Multiplier'],
                                 new_state() if rng is None else rng)
        for reward in model['MaterialTypes']:
            key = str(reward['MaterialTypeId'])
            state['inventory'][key] = float(self._number(state['inventory'].get(key, 0)) + reward['Amount'])
        state['dailySpin'] = {'at': at, 'increment': increment}
        state['user'].update(NextDailySpinAt=at + 86400, NextDailySpinIncrement=increment % 7 + 1)
        response = {'result': {'WheelOfFortuneModel': model}, 'user': copy.deepcopy(state['user'])}
        state['fortuneReceipts'][receipt] = copy.deepcopy(response)
        state['revision'] = int(state.get('revision', 0)) + 1
        return response
