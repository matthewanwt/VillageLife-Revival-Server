"""Unit tests for BlueStacks installation detection (F-12).

All tests mock the registry and filesystem; no BlueStacks installation or
admin rights are required, and no sockets are bound.
"""
from pathlib import Path
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, call, patch

from villagelife.platforms.bluestacks import (
    InstanceError,
    _registry_install_dir,
    installation,
)


def _make_install(root: Path) -> Path:
    """Create a minimal fake BlueStacks directory with the two required EXEs."""
    root.mkdir(parents=True, exist_ok=True)
    (root / 'HD-Player.exe').touch()
    (root / 'HD-Adb.exe').touch()
    return root


# ---------------------------------------------------------------------------
# _registry_install_dir
# ---------------------------------------------------------------------------

class RegistryReadTests(unittest.TestCase):

    def _winreg_mock(self, side_effects: dict) -> MagicMock:
        """Return a minimal winreg module mock.

        side_effects: maps key path suffix (e.g. r'SOFTWARE\\BlueStacks_nxt')
        to either a string (InstallDir value) or an OSError subclass instance.
        """
        winreg = MagicMock()
        winreg.HKEY_LOCAL_MACHINE = 'HKLM'

        def open_key(hive, key_name):
            effect = side_effects.get(key_name)
            if effect is None or isinstance(effect, OSError):
                raise (effect or FileNotFoundError(key_name))
            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=ctx)
            ctx.__exit__ = MagicMock(return_value=False)
            ctx._value = effect
            return ctx

        def query_value_ex(key, name):
            if name != 'InstallDir':
                raise FileNotFoundError(name)
            return (key._value, 1)  # (data, type)

        winreg.OpenKey.side_effect = open_key
        winreg.QueryValueEx.side_effect = query_value_ex
        return winreg

    def test_returns_path_from_standard_key(self):
        winreg = self._winreg_mock({r'SOFTWARE\BlueStacks_nxt': r'C:\Program Files\BlueStacks_nxt'})
        with patch.dict(sys.modules, {'winreg': winreg}):
            result = _registry_install_dir()
        self.assertEqual(result, Path(r'C:\Program Files\BlueStacks_nxt'))

    def test_falls_through_to_cn_key_when_standard_absent(self):
        winreg = self._winreg_mock({r'SOFTWARE\BlueStacks_nxt_cn': r'D:\BlueStacks'})
        with patch.dict(sys.modules, {'winreg': winreg}):
            result = _registry_install_dir()
        self.assertEqual(result, Path(r'D:\BlueStacks'))

    def test_falls_through_to_msi5_key(self):
        winreg = self._winreg_mock({r'SOFTWARE\BlueStacks_msi5': r'E:\BST'})
        with patch.dict(sys.modules, {'winreg': winreg}):
            result = _registry_install_dir()
        self.assertEqual(result, Path(r'E:\BST'))

    def test_returns_none_when_no_key_present(self):
        winreg = self._winreg_mock({})
        with patch.dict(sys.modules, {'winreg': winreg}):
            result = _registry_install_dir()
        self.assertIsNone(result)

    def test_returns_none_on_non_windows_import_error(self):
        # Simulate a platform where winreg doesn't exist
        saved = sys.modules.pop('winreg', None)
        try:
            # Temporarily make winreg unimportable
            with patch.dict(sys.modules, {'winreg': None}):
                result = _registry_install_dir()
            self.assertIsNone(result)
        finally:
            if saved is not None:
                sys.modules['winreg'] = saved

    def test_ignores_permission_error_and_continues(self):
        """A key that raises PermissionError should be skipped, not propagated."""
        winreg = self._winreg_mock({
            r'SOFTWARE\BlueStacks_nxt': PermissionError('access denied'),
            r'SOFTWARE\BlueStacks_nxt_cn': r'C:\BlueStacks_cn',
        })
        with patch.dict(sys.modules, {'winreg': winreg}):
            result = _registry_install_dir()
        self.assertEqual(result, Path(r'C:\BlueStacks_cn'))

    def test_returns_none_for_empty_install_dir_value(self):
        """An empty string in the registry should not produce a Path."""
        winreg = self._winreg_mock({r'SOFTWARE\BlueStacks_nxt': ''})
        with patch.dict(sys.modules, {'winreg': winreg}):
            result = _registry_install_dir()
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# installation() – search order and env var
# ---------------------------------------------------------------------------

class InstallationSearchTests(unittest.TestCase):

    def test_registry_path_wins_over_programfiles_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            reg_root = _make_install(Path(folder) / 'reg_install')
            with patch('villagelife.platforms.bluestacks._registry_install_dir',
                       return_value=reg_root), \
                 patch.dict(os.environ, {'VILLAGELIFE_BLUESTACKS_HOME': ''}):
                result = installation()
            self.assertEqual(result, reg_root.resolve())

    def test_env_var_wins_over_registry_and_programfiles(self):
        with tempfile.TemporaryDirectory() as folder:
            env_root = Path(folder) / 'custom'
            env_root.mkdir()
            _make_install(env_root)
            reg_root = Path(folder) / 'reg'  # not created – should not be reached
            with patch('villagelife.platforms.bluestacks._registry_install_dir',
                       return_value=reg_root), \
                 patch.dict(os.environ, {'VILLAGELIFE_BLUESTACKS_HOME': str(env_root)}):
                result = installation()
            self.assertEqual(result, env_root.resolve())

    def test_falls_back_to_programfiles_when_registry_absent(self):
        with tempfile.TemporaryDirectory() as folder:
            pf_root = Path(folder) / 'PF' / 'BlueStacks_nxt'
            _make_install(pf_root)
            env_overrides = {
                'ProgramFiles': str(Path(folder) / 'PF'),
                'ProgramW6432': '',
                'ProgramFiles(x86)': '',
                'VILLAGELIFE_BLUESTACKS_HOME': '',
            }
            with patch('villagelife.platforms.bluestacks._registry_install_dir',
                       return_value=None), \
                 patch.dict(os.environ, env_overrides):
                result = installation()
            self.assertEqual(result, pf_root.resolve())

    def test_explicit_search_list_bypasses_registry(self):
        """When caller supplies search, _registry_install_dir must not be called."""
        with tempfile.TemporaryDirectory() as folder:
            custom = Path(folder) / 'explicit'
            custom.mkdir()
            _make_install(custom)
            with patch('villagelife.platforms.bluestacks._registry_install_dir') as reg:
                result = installation(search=[custom])
            reg.assert_not_called()
            self.assertEqual(result, custom.resolve())

    def test_requires_both_exes(self):
        """A directory with only HD-Player.exe should not be accepted."""
        with tempfile.TemporaryDirectory() as folder:
            partial = Path(folder) / 'partial'
            partial.mkdir()
            (partial / 'HD-Player.exe').touch()
            # HD-Adb.exe intentionally absent
            with patch('villagelife.platforms.bluestacks._registry_install_dir',
                       return_value=None):
                with self.assertRaises(InstanceError) as ctx:
                    installation(search=[partial])
            self.assertEqual(ctx.exception.code, 'VL-BS-NOT-FOUND')

    def test_not_found_error_lists_searched_paths(self):
        """VL-BS-NOT-FOUND message must include every path that was tried."""
        fake_paths = [Path('X:/nowhere'), Path('Y:/also_nowhere')]
        with self.assertRaises(InstanceError) as ctx:
            installation(search=fake_paths)
        msg = str(ctx.exception)
        self.assertIn('VL-BS-NOT-FOUND', msg)
        # Path() normalises separators; compare with os.sep
        self.assertIn(str(fake_paths[0]), msg)
        self.assertIn(str(fake_paths[1]), msg)
        self.assertIn('VILLAGELIFE_BLUESTACKS_HOME', msg)

    def test_not_found_with_empty_search_list(self):
        """An explicitly empty search list should produce a clear error, not a crash."""
        with self.assertRaises(InstanceError) as ctx:
            installation(search=[])
        self.assertEqual(ctx.exception.code, 'VL-BS-NOT-FOUND')
        self.assertIn('(none)', str(ctx.exception))

    def test_registry_path_missing_exes_falls_through_to_programfiles(self):
        """Registry key present but dir lacks EXEs → fall through to %ProgramFiles%."""
        with tempfile.TemporaryDirectory() as folder:
            reg_root = Path(folder) / 'reg_empty'
            reg_root.mkdir()
            # No EXEs in reg_root

            pf_root = Path(folder) / 'PF' / 'BlueStacks_nxt'
            _make_install(pf_root)
            env_overrides = {
                'ProgramFiles': str(Path(folder) / 'PF'),
                'ProgramW6432': '',
                'ProgramFiles(x86)': '',
                'VILLAGELIFE_BLUESTACKS_HOME': '',
            }

            with patch('villagelife.platforms.bluestacks._registry_install_dir',
                       return_value=reg_root), \
                 patch.dict(os.environ, env_overrides):
                result = installation()
            self.assertEqual(result, pf_root.resolve())
