"""Boundary types independent of an HTTP protocol, renderer or save database.

The new native schema is deliberately small. The old-format save is an
opaque, separately tagged format until original fields are mapped and proven.
"""
from dataclasses import dataclass
from typing import Any
import copy


@dataclass(frozen=True)
class VillageSnapshot:
    village_id: str
    account_id: str
    format: str
    schema_version: int
    revision: int
    payload: dict[str, Any]

    def mutable_payload(self) -> dict[str, Any]:
        return copy.deepcopy(self.payload)


def empty_native_village(initial_area_id: int = 1) -> dict[str, Any]:
    """Scaffold only: does not imply any particular original game starting state."""
    return {
        "schemaVersion": 1,
        "currentAreaId": initial_area_id,
        "unlockedAreas": [initial_area_id],
        "entities": {},
        "villagers": {},
        "inventory": {},
        "jobs": {},
        "extensions": {},
    }
