"""Launcher entry point for the official BlueStacks Multi-instance Manager GUI."""
from platforms.bluestacks.manager import main
from runtime_errors import initialize_utf8, report_error

if __name__ == '__main__':
    initialize_utf8()
    try:
        main()
    except Exception as error:
        report_error(error)
        raise SystemExit(1)
