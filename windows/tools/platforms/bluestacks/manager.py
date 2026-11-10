"""Guided, non-destructive BlueStacks 5 Pie64 instance management.

BlueStacks' documented GUI is used for VM creation. Undocumented disk and VM
file manipulation is deliberately avoided. Launch an existing *selected* VM
only after its stable ID has been chosen and validated elsewhere.
"""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import subprocess
from platforms.bluestacks.discovery import discover_bluestacks
from platforms.bluestacks.instances import available_instances, select_instance
from runtime_errors import VillageRuntimeError, report_error

FLAGS = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


def choose_for_setup(instances: list[dict], *, preferred: str | None = None) -> dict | None:
    """Use saved stable ID if valid; never guess when multiple candidates exist.

    Returns None when a user's selection is required. Does not mutate settings.
    """
    if preferred:
        return select_instance(instances, preferred)
    if len(instances) == 1:
        return select_instance(instances, instances[0]['id'])
    return None


def open_instance_manager(installation=None, *, popen=subprocess.Popen):
    """Opt-in: open BlueStacks' official manager UI, NOT create a VM silently."""
    if os.name != 'nt' and installation is None:
        raise VillageRuntimeError('VL-BS-WINDOWS-ONLY', 'BlueStacks is only available in this Windows workflow.')
    installation = installation or discover_bluestacks(require_manager=True)
    executable = installation.gui_manager
    if not Path(executable).is_file():
        raise VillageRuntimeError('VL-BS-MANAGER-MISSING', 'BlueStacks Multi-instance Manager was not found.',
                                  'Repair BlueStacks or open its Multi-instance Manager manually.')
    return popen([str(executable)], creationflags=FLAGS)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--open-manager', action='store_true', help='Open the BlueStacks GUI for guided manual creation')
    parser.add_argument('--list', action='store_true', help='Show discovered Pie64 instances')
    args = parser.parse_args()
    if args.open_manager:
        open_instance_manager()
        print('Opened BlueStacks Multi-instance Manager. Create a dedicated Pie64 instance, enable ADB, then return to setup.')
    elif args.list:
        import json
        print(json.dumps(available_instances(), ensure_ascii=False))
    else:
        parser.print_help()


if __name__ == '__main__':
    try: main()
    except Exception as exc:
        report_error(exc)
        raise SystemExit(1)
