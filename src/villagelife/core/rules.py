"""Rules must have provenance. Unknown original behaviours explicitly fail."""
from dataclasses import dataclass
from typing import Protocol
from .errors import NotImplementedRule


@dataclass(frozen=True)
class VerifiedTaskRule:
    rule_id: str
    duration_seconds: int
    completion_mode: str  # collect | automatic (verified by original behaviour)
    evidence: str

    def __post_init__(self) -> None:
        if not self.rule_id or not self.evidence or not 0 <= self.duration_seconds <= 365*86400:
            raise ValueError('Invalid or undocumented task rule')
        if self.completion_mode not in {'collect', 'automatic'}:
            raise ValueError('Unknown completion mode')


class TaskRuleProvider(Protocol):
    def task_rule(self, rule_id: str) -> VerifiedTaskRule: ...


class NoVerifiedRules:
    def task_rule(self, rule_id: str) -> VerifiedTaskRule:
        raise NotImplementedRule(f'Original task rules not verified: {rule_id}')

    def building_rule(self, building_id: str):
        raise NotImplementedRule(f'Building behaviour not recovered: {building_id}')

    def scenario(self, area_id: int):
        raise NotImplementedRule(f'Area scenario not imported: {area_id}')
