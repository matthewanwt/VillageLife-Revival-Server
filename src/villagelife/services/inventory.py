"""Exact, nonnegative inventory arithmetic used only by verified rules.

This ledger is not exposed as an arbitrary player 'grant resource' endpoint.
"""
from __future__ import annotations
from decimal import Decimal, InvalidOperation
from typing import Any
from villagelife.core.errors import InvalidAction


class InventoryLedger:
    @staticmethod
    def apply(world: dict[str, Any], resource_id: str, amount: str) -> str:
        if not resource_id or len(resource_id) > 128:
            raise InvalidAction('Invalid resource identity')
        try:
            delta = Decimal(amount)
            current = Decimal(str(world.setdefault('inventory', {}).get(resource_id, '0')))
        except (InvalidOperation, TypeError, ValueError):
            raise InvalidAction('Invalid resource quantity') from None
        updated = current + delta
        if not updated.is_finite() or updated < 0:
            raise InvalidAction('Insufficient resource or invalid quantity')
        value = format(updated.normalize(), 'f')
        world['inventory'][resource_id] = value
        return value
