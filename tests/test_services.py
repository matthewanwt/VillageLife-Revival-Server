import tempfile
import unittest
from pathlib import Path
from villagelife.core.model import empty_native_village
from villagelife.core.clock import FrozenClock
from villagelife.core.rules import VerifiedTaskRule
from villagelife.core.errors import NotImplementedRule
from villagelife.persistence.sqlite_store import SqliteSaveRepository
from villagelife.services.jobs import JobService, WorldTickCoordinator
from villagelife.services.areas import AreaService, UnverifiedAreaRules
from villagelife.services.buildings import BuildingService, UnverifiedBuildingRules


class TestOnlyRules:
    def task_rule(self, rule_id):
        return VerifiedTaskRule(rule_id, 120, 'collect', 'TEST FIXTURE - not an original game rule')


class DomainTests(unittest.TestCase):
    def test_offline_catch_up_and_idempotent_hosted_tick(self):
        with tempfile.TemporaryDirectory() as folder:
            repo = SqliteSaveRepository(Path(folder) / 'save.sqlite3')
            acct = repo.create_account('A')
            state = empty_native_village()
            JobService(TestOnlyRules()).schedule(state, job_id='job1', rule_id='fixture', started_at=1000)
            vid = repo.create_village(acct, state)
            time = FrozenClock(1119)
            coord = WorldTickCoordinator(repo, time)
            self.assertEqual(coord.advance_village(vid), [])
            time.advance(1)
            self.assertEqual(coord.advance_village(vid), ['job1'])
            self.assertEqual(coord.advance_village(vid), [])
            self.assertEqual(repo.read_village(vid).payload['jobs']['job1']['status'], 'ready')
            with self.assertRaises(NotImplementedRule):
                JobService(TestOnlyRules()).collect(repo.read_village(vid).mutable_payload(), 'job1')

    def test_unverified_original_rules_fail_closed(self):
        world = empty_native_village()
        with self.assertRaises(NotImplementedRule):
            AreaService(UnverifiedAreaRules()).unlock(world, 2)
        with self.assertRaises(NotImplementedRule):
            BuildingService(UnverifiedBuildingRules()).execute(world, 'work.start', {'buildingId': 'x'})
        self.assertEqual(world['currentAreaId'], 1)


if __name__ == '__main__':
    unittest.main()
