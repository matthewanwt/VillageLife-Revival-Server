"""Reject any accidental packaging of the historical server into this project."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]

class IsolationTests(unittest.TestCase):
    def test_no_legacy_reference_or_old_server(self):
        self.assertFalse((ROOT/'legacy_reference').exists())
        self.assertFalse((ROOT/'backend').exists())
        self.assertFalse((ROOT/'windows/tools/play_local.py').exists())
        scripts='\n'.join(x.read_text(encoding='utf-8') for x in (ROOT/'windows/installer').glob('*.ps1'))
        self.assertNotIn('Copy-Item -LiteralPath (Join-Path $repo "legacy_reference',scripts)
        self.assertIn('src',str(ROOT/'src'))
        self.assertIn('PyInstaller',scripts)
