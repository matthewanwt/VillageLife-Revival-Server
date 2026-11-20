"""Authoritative world time, without guessing unverified game production rules.

Completing a timer is distinct from claiming a reward. The latter is guarded by
an original-game rule provider and is not implemented until verified.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
import hashlib
from villagelife.core.errors import InvalidAction, NotImplementedRule
from villagelife.core.rules import NoVerifiedRules, TaskRuleProvider


@dataclass
class JobService:
    rules: TaskRuleProvider

    def schedule(self, world: dict[str, Any], *, job_id: str, rule_id: str,
                 started_at: int, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if not job_id or not isinstance(started_at, int):
            raise InvalidAction('Job ID and integer start time required')
        jobs = world.setdefault('jobs', {})
        if job_id in jobs:
            raise InvalidAction('Job ID already exists')
        definition = self.rules.task_rule(rule_id)
        job = {'id': job_id, 'ruleId': definition.rule_id,
               'startedAt': started_at,
               'dueAt': started_at + definition.duration_seconds,
               'status': 'working', 'completionMode': definition.completion_mode,
               'payload': payload or {}, 'evidence': definition.evidence}
        jobs[job_id] = job
        return dict(job)

    @staticmethod
    def advance(world: dict[str, Any], now: int) -> list[str]:
        """Deterministically transition due jobs to ready. Does NOT invent rewards."""
        if not isinstance(now, int):
            raise InvalidAction('Clock must be an integer Unix timestamp')
        ready: list[str] = []
        for key in sorted(world.get('jobs', {})):
            job = world['jobs'][key]
            if job.get('status') != 'working':
                continue
            due = job.get('dueAt')
            if not isinstance(due, int):
                raise InvalidAction(f'Missing verified due time for job {key}')
            if due <= now:
                job['status'] = 'ready'
                job['readyAt'] = due
                ready.append(key)
        return ready

    @staticmethod
    def advance_one(world: dict[str, Any], job_id: str, now: int) -> bool:
        """Atomic idempotent transition for one specific job."""
        job = world.get('jobs', {}).get(job_id)
        if not job or job.get('status') != 'working':
            return False
        due = job.get('dueAt')
        if not isinstance(due, int):
            raise InvalidAction(f'Invalid due time for job {job_id}')
        if due > now:
            return False
        job['status'] = 'ready'
        job['readyAt'] = due
        return True

    def collect(self, world: dict[str, Any], job_id: str) -> dict[str, Any]:
        job = world.get('jobs', {}).get(job_id)
        if not job:
            raise InvalidAction('Unknown job')
        if job.get('status') != 'ready':
            raise InvalidAction('Job is not ready')
        raise NotImplementedRule('Reward calculation and collection require verified original rules')


class WorldTickCoordinator:
    """Hosted tick and offline catch-up use the SAME deterministic transition.

    Full scans are a starting point; a due-job index will be needed at scale.
    No game-specific timers or rewards are invented by this coordinator.
    """
    def __init__(self, store, clock):
        self.store = store
        self.clock = clock

    def advance_village(self, village_id: str) -> list[str]:
        snapshot = self.store.read_village(village_id)
        if snapshot.format != 'native.v1':
            return []  # Do not mutate opaque imported legacy saves.
        due_ids = [key for key, job in snapshot.payload.get('jobs', {}).items()
                   if job.get('status') == 'working' and isinstance(job.get('dueAt'), int)
                   and job['dueAt'] <= self.clock.now()]
        if not due_ids:
            return []
        due_ids = sorted(due_ids)
        def transition(state):
            return {'readyJobIds': [key for key in due_ids
                    if JobService.advance_one(state, key, self.clock.now())]}
        key = hashlib.sha256(repr(due_ids).encode()).hexdigest()
        _, response, repeated = self.store.mutate(village_id, operation_key='system:due-batch:' + key,
            request={'action': 'jobs.ready', 'jobIds': due_ids}, change=transition)
        return [] if repeated else response['readyJobIds']

    def advance_all(self) -> dict[str, list[str]]:
        result = {}
        for village_id in self.store.due_villages(self.clock.now()):
            due = self.advance_village(village_id)
            if due:
                result[village_id] = due
        return result
