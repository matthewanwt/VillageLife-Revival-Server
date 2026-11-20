"""Unit tests for BlueStacks installation and configuration discovery.

All tests mock the registry and filesystem where appropriate; no BlueStacks
installation or administrator rights are required, and no sockets are bound.
"""
from pathlib import Path
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from villagelife.platforms.bluestacks import (
    InstanceError,
    _registry_data_dir,
    _registry_install_dir,
    config_path,
    installation,
    list_instances,
)


def _make_install(root: Path) -> Path:
    """Create a minimal fake BlueStacks directory with the two required EXEs."""
    root.mkdir(parents=True, exist_ok=True)
    (root / 'HD-Player.exe').touch()
    (root / 'HD-Adb.exe').touch()
    return root


# ---------------------------------------------------------------------------
# Registry discovery
# ---------------------------------------------------------------------------

class RegistryReadTests(unittest.TestCase):

    def _winreg_mock(self, side_effects: dict) -> MagicMock:
        """Return a minimal winreg module mock.

        ``side_effects`` maps a registry key to one of:
        - a string, interpreted as its legacy ``InstallDir`` value;
        - a dictionary of named registry values, such as ``InstallDir`` and
          ``DataDir``;
        - an OSError instance, used to simulate a registry access failure.
        """
        winreg = MagicMock()
        winreg.HKEY_LOCAL_MACHINE = 'HKLM'

        def open_key(hive, key_name):
            effect = side_effects.get(key_name)
            if effect is None or isinstance(effect, OSError):
                raise effect or FileNotFoundError(key_name)

            context = MagicMock()
            context.__enter__ = MagicMock(return_value=context)
            context.__exit__ = MagicMock(return_value=False)
            context._value = effect
            return context

        def query_value_ex(key, name):
            stored = key._value
            if isinstance(stored, dict):
                if name not in stored:
                    raise FileNotFoundError(name)
                return stored[name], 1

            if name != 'InstallDir':
                raise FileNotFoundError(name)
            return stored, 1

        winreg.OpenKey.side_effect = open_key
        winreg.QueryValueEx.side_effect = query_value_ex
        return winreg

    # InstallDir tests

    def test_returns_install_dir_from_standard_key(self):
        winreg = self._winreg_mock({
            r'SOFTWARE\BlueStacks_nxt': r'C:\Program Files\BlueStacks_nxt',
        })
        with patch.dict(sys.modules, {'winreg': winreg}):
            result = _registry_install_dir()
        self.assertEqual(result, Path(r'C:\Program Files\BlueStacks_nxt'))

    def test_install_dir_falls_through_to_cn_key(self):
        winreg = self._winreg_mock({
            r'SOFTWARE\BlueStacks_nxt_cn': r'D:\BlueStacks',
        })
        with patch.dict(sys.modules, {'winreg': winreg}):
            result = _registry_install_dir()
        self.assertEqual(result, Path(r'D:\BlueStacks'))

    def test_install_dir_falls_through_to_msi5_key(self):
        winreg = self._winreg_mock({
            r'SOFTWARE\BlueStacks_msi5': r'E:\BST',
        })
        with patch.dict(sys.modules, {'winreg': winreg}):
            result = _registry_install_dir()
        self.assertEqual(result, Path(r'E:\BST'))

    def test_install_dir_returns_none_when_no_key_is_present(self):
        winreg = self._winreg_mock({})
        with patch.dict(sys.modules, {'winreg': winreg}):
            result = _registry_install_dir()
        self.assertIsNone(result)

    def test_install_dir_returns_none_when_winreg_is_unavailable(self):
        saved = sys.modules.pop('winreg', None)
        try:
            with patch.dict(sys.modules, {'winreg': None}):
                result = _registry_install_dir()
            self.assertIsNone(result)
        finally:
            if saved is not None:
                sys.modules['winreg'] = saved

    def test_install_dir_skips_permission_error_and_continues(self):
        winreg = self._winreg_mock({
            r'SOFTWARE\BlueStacks_nxt': PermissionError('access denied'),
            r'SOFTWARE\BlueStacks_nxt_cn': r'C:\BlueStacks_cn',
        })
        with patch.dict(sys.modules, {'winreg': winreg}):
            result = _registry_install_dir()
        self.assertEqual(result, Path(r'C:\BlueStacks_cn'))

    def test_install_dir_ignores_empty_value(self):
        winreg = self._winreg_mock({
            r'SOFTWARE\BlueStacks_nxt': '',
        })
        with patch.dict(sys.modules, {'winreg': winreg}):
            result = _registry_install_dir()
        self.assertIsNone(result)

    # DataDir tests

    def test_returns_data_dir_from_standard_key(self):
        winreg = self._winreg_mock({
            r'SOFTWARE\BlueStacks_nxt': {
                'InstallDir': r'C:\Program Files\BlueStacks_nxt',
                'DataDir': r'D:\BlueStacks\BlueStacks_nxt\Engine',
            },
        })
        with patch.dict(sys.modules, {'winreg': winreg}):
            result = _registry_data_dir()
        self.assertEqual(
            result,
            Path(r'D:\BlueStacks\BlueStacks_nxt\Engine'),
        )

    def test_data_dir_continues_to_cn_key_when_standard_value_is_missing(self):
        winreg = self._winreg_mock({
            r'SOFTWARE\BlueStacks_nxt': {
                'InstallDir': r'C:\Program Files\BlueStacks_nxt',
            },
            r'SOFTWARE\BlueStacks_nxt_cn': {
                'DataDir': r'D:\BlueStacks\Engine',
            },
        })
        with patch.dict(sys.modules, {'winreg': winreg}):
            result = _registry_data_dir()
        self.assertEqual(result, Path(r'D:\BlueStacks\Engine'))

    def test_data_dir_falls_through_to_msi5_key(self):
        winreg = self._winreg_mock({
            r'SOFTWARE\BlueStacks_msi5': {
                'DataDir': r'E:\BlueStacksData\Engine',
            },
        })
        with patch.dict(sys.modules, {'winreg': winreg}):
            result = _registry_data_dir()
        self.assertEqual(result, Path(r'E:\BlueStacksData\Engine'))

    def test_data_dir_skips_permission_error_and_continues(self):
        winreg = self._winreg_mock({
            r'SOFTWARE\BlueStacks_nxt': PermissionError('access denied'),
            r'SOFTWARE\BlueStacks_nxt_cn': {
                'DataDir': r'D:\BlueStacks\Engine',
            },
        })
        with patch.dict(sys.modules, {'winreg': winreg}):
            result = _registry_data_dir()
        self.assertEqual(result, Path(r'D:\BlueStacks\Engine'))

    def test_data_dir_ignores_empty_value(self):
        winreg = self._winreg_mock({
            r'SOFTWARE\BlueStacks_nxt': {'DataDir': '   '},
        })
        with patch.dict(sys.modules, {'winreg': winreg}):
            result = _registry_data_dir()
        self.assertIsNone(result)

    def test_data_dir_returns_none_when_no_key_has_value(self):
        winreg = self._winreg_mock({
            r'SOFTWARE\BlueStacks_nxt': {
                'InstallDir': r'C:\Program Files\BlueStacks_nxt',
            },
        })
        with patch.dict(sys.modules, {'winreg': winreg}):
            result = _registry_data_dir()
        self.assertIsNone(result)

    def test_data_dir_returns_none_when_winreg_is_unavailable(self):
        saved = sys.modules.pop('winreg', None)
        try:
            with patch.dict(sys.modules, {'winreg': None}):
                result = _registry_data_dir()
            self.assertIsNone(result)
        finally:
            if saved is not None:
                sys.modules['winreg'] = saved


# ---------------------------------------------------------------------------
# Configuration path discovery
# ---------------------------------------------------------------------------

class ConfigPathTests(unittest.TestCase):

    def test_prefers_registered_data_dir_parent_over_programdata(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            data_dir = root / 'BlueStacks_nxt' / 'Engine'
            data_dir.mkdir(parents=True)

            registered_config = data_dir.parent / 'bluestacks.conf'
            registered_config.touch()

            programdata = root / 'ProgramData'
            fallback = programdata / 'BlueStacks_nxt' / 'bluestacks.conf'
            fallback.parent.mkdir(parents=True)
            fallback.touch()

            with patch.dict(os.environ, {'ProgramData': str(programdata)}), \
                 patch(
                     'villagelife.platforms.bluestacks._registry_data_dir',
                     return_value=data_dir,
                 ):
                result = config_path()

            self.assertEqual(result, registered_config)

    def test_accepts_config_inside_registered_data_dir(self):
        with tempfile.TemporaryDirectory() as folder:
            data_dir = Path(folder) / 'Engine'
            data_dir.mkdir()
            registered_config = data_dir / 'bluestacks.conf'
            registered_config.touch()

            with patch(
                'villagelife.platforms.bluestacks._registry_data_dir',
                return_value=data_dir,
            ):
                result = config_path()

            self.assertEqual(result, registered_config)

    def test_falls_back_to_programdata_when_registered_config_is_missing(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            data_dir = root / 'Custom' / 'Engine'
            data_dir.mkdir(parents=True)

            programdata = root / 'ProgramData'
            fallback = programdata / 'BlueStacks_nxt' / 'bluestacks.conf'
            fallback.parent.mkdir(parents=True)
            fallback.touch()

            with patch.dict(os.environ, {'ProgramData': str(programdata)}), \
                 patch(
                     'villagelife.platforms.bluestacks._registry_data_dir',
                     return_value=data_dir,
                 ):
                result = config_path()

            self.assertEqual(result, fallback)

    def test_uses_programdata_when_registry_data_dir_is_unavailable(self):
        with tempfile.TemporaryDirectory() as folder:
            programdata = Path(folder) / 'ProgramData'
            fallback = programdata / 'BlueStacks_nxt' / 'bluestacks.conf'
            fallback.parent.mkdir(parents=True)
            fallback.touch()

            with patch.dict(os.environ, {'ProgramData': str(programdata)}), \
                 patch(
                     'villagelife.platforms.bluestacks._registry_data_dir',
                     return_value=None,
                 ):
                result = config_path()

            self.assertEqual(result, fallback)

    def test_explicit_data_dir_bypasses_registry_lookup(self):
        with tempfile.TemporaryDirectory() as folder:
            data_dir = Path(folder) / 'Engine'
            data_dir.mkdir()
            registered_config = data_dir.parent / 'bluestacks.conf'
            registered_config.touch()

            with patch(
                'villagelife.platforms.bluestacks._registry_data_dir'
            ) as registry_lookup:
                result = config_path(data_dir=data_dir)

            registry_lookup.assert_not_called()
            self.assertEqual(result, registered_config)

    def test_returns_programdata_fallback_path_when_no_config_exists(self):
        with tempfile.TemporaryDirectory() as folder:
            programdata = Path(folder) / 'ProgramData'
            expected = programdata / 'BlueStacks_nxt' / 'bluestacks.conf'

            with patch(
                'villagelife.platforms.bluestacks._registry_data_dir',
                return_value=None,
            ):
                result = config_path(programdata=programdata)

            self.assertEqual(result, expected)
            self.assertFalse(result.exists())

    def test_list_instances_reads_config_from_registered_data_dir(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            data_dir = root / 'BlueStacks_nxt' / 'Engine'
            data_dir.mkdir(parents=True)
            config = data_dir.parent / 'bluestacks.conf'
            config.write_text(
                'bst.instance.Pie64.display_name="BlueStacks App Player"\n'
                'bst.instance.Pie64.adb_port="5555"\n',
                encoding='utf-8',
            )
            programdata = root / 'ProgramData'

            with patch.dict(os.environ, {'ProgramData': str(programdata)}), \
                 patch(
                     'villagelife.platforms.bluestacks._registry_data_dir',
                     return_value=data_dir,
                 ):
                rows = list_instances()

            self.assertEqual([row.id for row in rows], ['Pie64'])
            self.assertEqual(rows[0].adb_port, 5555)


# ---------------------------------------------------------------------------
# installation() – search order and environment variable
# ---------------------------------------------------------------------------

class InstallationSearchTests(unittest.TestCase):

    def test_registry_path_wins_over_programfiles_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            reg_root = _make_install(Path(folder) / 'reg_install')
            with patch(
                'villagelife.platforms.bluestacks._registry_install_dir',
                return_value=reg_root,
            ), patch.dict(os.environ, {'VILLAGELIFE_BLUESTACKS_HOME': ''}):
                result = installation()
            self.assertEqual(result, reg_root.resolve())

    def test_env_var_wins_over_registry_and_programfiles(self):
        with tempfile.TemporaryDirectory() as folder:
            env_root = Path(folder) / 'custom'
            _make_install(env_root)
            reg_root = Path(folder) / 'reg'  # Not created; should not be reached.
            with patch(
                'villagelife.platforms.bluestacks._registry_install_dir',
                return_value=reg_root,
            ), patch.dict(os.environ, {'VILLAGELIFE_BLUESTACKS_HOME': str(env_root)}):
                result = installation()
            self.assertEqual(result, env_root.resolve())

    def test_falls_back_to_programfiles_when_registry_is_absent(self):
        with tempfile.TemporaryDirectory() as folder:
            pf_root = Path(folder) / 'PF' / 'BlueStacks_nxt'
            _make_install(pf_root)
            env_overrides = {
                'ProgramFiles': str(Path(folder) / 'PF'),
                'ProgramW6432': '',
                'ProgramFiles(x86)': '',
                'VILLAGELIFE_BLUESTACKS_HOME': '',
            }
            with patch(
                'villagelife.platforms.bluestacks._registry_install_dir',
                return_value=None,
            ), patch.dict(os.environ, env_overrides):
                result = installation()
            self.assertEqual(result, pf_root.resolve())

    def test_explicit_search_list_bypasses_registry(self):
        with tempfile.TemporaryDirectory() as folder:
            custom = Path(folder) / 'explicit'
            _make_install(custom)
            with patch(
                'villagelife.platforms.bluestacks._registry_install_dir'
            ) as registry_lookup:
                result = installation(search=[custom])
            registry_lookup.assert_not_called()
            self.assertEqual(result, custom.resolve())

    def test_requires_both_executables(self):
        with tempfile.TemporaryDirectory() as folder:
            partial = Path(folder) / 'partial'
            partial.mkdir()
            (partial / 'HD-Player.exe').touch()

            with patch(
                'villagelife.platforms.bluestacks._registry_install_dir',
                return_value=None,
            ):
                with self.assertRaises(InstanceError) as context:
                    installation(search=[partial])

            self.assertEqual(context.exception.code, 'VL-BS-NOT-FOUND')

    def test_not_found_error_lists_searched_paths(self):
        fake_paths = [Path('X:/nowhere'), Path('Y:/also_nowhere')]
        with self.assertRaises(InstanceError) as context:
            installation(search=fake_paths)

        message = str(context.exception)
        self.assertIn('VL-BS-NOT-FOUND', message)
        self.assertIn(str(fake_paths[0]), message)
        self.assertIn(str(fake_paths[1]), message)
        self.assertIn('VILLAGELIFE_BLUESTACKS_HOME', message)

    def test_not_found_with_empty_search_list(self):
        with self.assertRaises(InstanceError) as context:
            installation(search=[])

        self.assertEqual(context.exception.code, 'VL-BS-NOT-FOUND')
        self.assertIn('(none)', str(context.exception))

    def test_registry_path_missing_executables_falls_through_to_programfiles(self):
        with tempfile.TemporaryDirectory() as folder:
            reg_root = Path(folder) / 'reg_empty'
            reg_root.mkdir()

            pf_root = Path(folder) / 'PF' / 'BlueStacks_nxt'
            _make_install(pf_root)
            env_overrides = {
                'ProgramFiles': str(Path(folder) / 'PF'),
                'ProgramW6432': '',
                'ProgramFiles(x86)': '',
                'VILLAGELIFE_BLUESTACKS_HOME': '',
            }

            with patch(
                'villagelife.platforms.bluestacks._registry_install_dir',
                return_value=reg_root,
            ), patch.dict(os.environ, env_overrides):
                result = installation()

            self.assertEqual(result, pf_root.resolve())


if __name__ == '__main__':
    unittest.main()