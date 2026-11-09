"""Inversion-of-control interfaces for infrastructure and verified game rules."""
from typing import Any, Callable, Protocol
from villagelife.core.model import VillageSnapshot


Mutation = Callable[[dict[str, Any]], dict[str, Any]]


class SavePort(Protocol):
    def read_village(self, village_id: str) -> VillageSnapshot: ...
    def mutate(
        self, village_id: str, *, operation_key: str, request: dict[str, Any],
        change: Mutation, expected_revision: int | None = None,
    ) -> tuple[VillageSnapshot, dict[str, Any], bool]: ...


class Clock(Protocol):
    def now(self) -> int: ...


class RulesCatalog(Protocol):
    def building(self, building_type: str) -> Any: ...
    def area(self, area_id: int) -> Any: ...
