"""Launcher source contracts for the Phase 1 appearance and village UI.

The WinForms launcher has no .NET test harness in this repository, so these
tests guard the wiring that makes the user-visible behavior work: persisted
theme selection, themed dialogs, and the local-village lifecycle commands.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / 'windows' / 'launcher'


def source(name: str) -> str:
    return (LAUNCHER / name).read_text(encoding='utf-8')


class LauncherPhase1Tests(unittest.TestCase):
    def test_theme_preference_is_persisted_and_applied_on_startup(self):
        program = source('Program.cs')
        dashboard = source('Dashboard.cs')
        theme = source('Theme.cs')
        self.assertIn('public string Theme { get; set; }', program)
        self.assertIn('ThemeManager.SetDark(string.Equals(appearance.Theme,"dark"',
                      dashboard)
        self.assertIn('settings.Theme=dark?"dark":"light";Write(settings);', dashboard)
        self.assertIn('RenderChecklist();ShowPage("Play");ApplyTheme();', dashboard)
        self.assertIn('DarkPalette', theme)
        self.assertIn('LightPalette', theme)
        self.assertIn('public static void Apply(Control root)', theme)

    def test_theme_switch_applies_without_restart(self):
        dashboard = source('Dashboard.cs')
        self.assertIn('themeChoice.SelectedIndexChanged+=(_,_)=>ChangeTheme('
                      'themeChoice.SelectedIndex==1);', dashboard)
        self.assertIn('ThemeManager.SetDark(dark);ApplyTheme();', dashboard)
        self.assertIn('void ApplyTheme() {\n        ThemeManager.Apply(this);', dashboard)

    def test_every_custom_dialog_applies_the_theme_before_showing(self):
        self.assertIn('ThemeManager.Apply(dialog);\n        return dialog.ShowDialog(this)'
                      '==DialogResult.OK ? items.SelectedIndex : -1;', source('Program.cs'))
        self.assertIn('ThemeManager.Apply(dialog);\n        if (dialog.ShowDialog(this)'
                      '!=DialogResult.OK) return;', source('Gems.cs'))
        self.assertIn('ThemeManager.Apply(guide);\n            var result=guide.ShowDialog(this);',
                      source('GuidedSetup.cs'))
        self.assertIn('ThemeManager.Apply(dialog);\n        var result=dialog.ShowDialog(this);',
                      source('Dashboard.cs'))

    def test_launcher_uses_the_local_village_lifecycle_commands(self):
        dashboard = source('Dashboard.cs')
        for command in ('list-local-villages', 'create-local-village',
                        'delete-local-village', 'delete-imported-village',
                        'restore-portable'):
            self.assertIn('"' + command + '"', dashboard)
        self.assertIn('async Task CreateNewVillage() {\n        RequireStopped();', dashboard)
        self.assertIn('async Task DeleteSelectedVillage() {\n        RequireStopped();', dashboard)
        self.assertIn('async Task RestoreFromBackup() {\n        RequireStopped();', dashboard)

    def test_delete_confirmation_names_the_village_and_offers_a_backup(self):
        dashboard = source('Dashboard.cs')
        self.assertIn('if(!ConfirmDelete(choice.Label,out bool backup))return;', dashboard)
        self.assertIn('Delete “"+label+"”?', dashboard)
        self.assertIn('Create a recovery backup before deleting', dashboard)
        self.assertIn('if(backupPath!=null) { args.Add("--backup");args.Add(backupPath); }',
                      dashboard)

    def test_deleting_the_selected_village_clears_only_that_selection(self):
        dashboard = source('Dashboard.cs')
        self.assertIn('if(choice.Local==settings.LocalVillage) { settings.LocalVillage="";'
                      'changed=true; }', dashboard)
        self.assertIn('if(choice.Imported==settings.ImportedVillage) { settings.ImportedVillage="";'
                      'changed=true; }', dashboard)
        self.assertIn('if(changed)Write(settings);', dashboard)

    def test_play_tab_village_picker_lists_new_villages_before_the_tutorial(self):
        program = source('Program.cs')
        self.assertIn('await ReadVillageList("--db",defaultDatabase,"list-local-villages")',
                      program)
        self.assertNotIn('await ReadVillageList("--db",defaultDatabase,"list-gem-villages")',
                         program)
        self.assertIn('int PickVillage(', program)
        self.assertIn('LocalVillageLabel(row)', program)

    def test_tutorial_villages_are_listed_before_the_first_login(self):
        dashboard = source('Dashboard.cs')
        self.assertIn('"list-local-villages"', dashboard)
        self.assertIn('village.TryGetProperty("stage",out var stage)&&stage.GetString()'
                      '=="tutorial"', dashboard)


if __name__ == '__main__':
    unittest.main()
