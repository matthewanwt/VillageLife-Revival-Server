import sqlite3
import tempfile
import unittest
from pathlib import Path
from villagelife.catalog.sqlite_catalog import OriginalGameCatalog
from villagelife.services.world import WorldService
from villagelife.services.inventory import InventoryLedger
from villagelife.core.model import empty_native_village
from villagelife.core.errors import InvalidAction, NotFound


class WorldCatalogTests(unittest.TestCase):
    def test_catalog_is_read_only_and_validated(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'fake_game_tables.sqlite'
            with sqlite3.connect(path) as db:
                db.execute('CREATE TABLE area(id INTEGER PRIMARY KEY, name TEXT)')
                db.execute("INSERT INTO area VALUES (1, 'Woodland')")
            catalog = OriginalGameCatalog(path)
            self.assertEqual(catalog.row_by_id('area', 1)['name'], 'Woodland')
            self.assertEqual(catalog.rows('area')[0]['id'], 1)
            with self.assertRaises(NotFound):
                catalog.rows('area; DROP TABLE area')
            self.assertEqual(len(catalog.file_sha256()), 64)

    def test_entity_identity_and_exact_inventory(self):
        world = empty_native_village()
        service = WorldService()
        service.add_entity(world, 'tree-1', {'type': 'scenery'})
        self.assertEqual(service.get_entity(world, 'tree-1')['type'], 'scenery')
        with self.assertRaises(InvalidAction):
            service.add_entity(world, 'tree-1', {})
        InventoryLedger.apply(world, 'example', '0.1')
        self.assertEqual(InventoryLedger.apply(world, 'example', '0.2'), '0.3')
        with self.assertRaises(InvalidAction):
            InventoryLedger.apply(world, 'example', '-1')


if __name__ == '__main__':
    unittest.main()
