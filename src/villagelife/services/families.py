"""Family relation interfaces preserve stable villager IDs and multi-owner boundaries."""
from typing import Any, Protocol
from villagelife.core.errors import NotImplementedRule


class FamilyRuleProvider(Protocol):
    def apply_relationship(self, world: dict[str, Any], command: dict[str, Any]) -> dict[str, Any]: ...
    def lifecycle(self, world: dict[str, Any], command: dict[str, Any]) -> dict[str, Any]: ...


class UnverifiedFamilyRules:
    def apply_relationship(self, world, command):
        raise NotImplementedRule('Original family-tree/relationship validation not yet ported')
    def lifecycle(self, world, command):
        raise NotImplementedRule('Age/pregnancy/child lifecycle must follow original rules')


class FamilyService:
    def __init__(self, rules: FamilyRuleProvider):
        self.rules = rules

    def relationship(self, world, data):
        return self.rules.apply_relationship(world, data)

    def lifecycle(self, world, data):
        return self.rules.lifecycle(world, data)
