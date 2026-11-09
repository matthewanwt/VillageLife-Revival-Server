"""Building domain boundary; no fabricated production or upgrade behaviour."""
from typing import Any, Protocol
from villagelife.core.errors import InvalidAction, NotImplementedRule


class BuildingRuleProvider(Protocol):
    def construct(self, world: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]: ...
    def start_work(self, world: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]: ...
    def collect(self, world: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]: ...


class UnverifiedBuildingRules:
    def construct(self, world, request):
        raise NotImplementedRule('Construction costs and prerequisites are not fully mapped')
    def start_work(self, world, request):
        raise NotImplementedRule('Building production rules are not yet verified')
    def collect(self, world, request):
        raise NotImplementedRule('Production reward/claim rules are not yet verified')


class BuildingService:
    def __init__(self, provider: BuildingRuleProvider):
        self.provider = provider

    def execute(self, world: dict[str, Any], action: str, data: dict[str, Any]) -> dict[str, Any]:
        if action == 'construct':
            return self.provider.construct(world, data)
        if action == 'work.start':
            return self.provider.start_work(world, data)
        if action == 'work.collect':
            return self.provider.collect(world, data)
        raise InvalidAction('Unsupported building action')
