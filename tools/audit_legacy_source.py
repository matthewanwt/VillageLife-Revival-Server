"""Static index for the preserved 0.2.6 backend; does not execute old code."""
import ast
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEGACY = ROOT / 'legacy_reference' / 'backend'
OUT = ROOT / 'docs' / 'legacy_function_inventory.csv'


def main():
    entries = []
    for source in sorted(LEGACY.glob('*.py')):
        tree = ast.parse(source.read_text(encoding='utf-8'), filename=str(source))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                entries.append({'module': source.stem, 'kind': type(node).__name__,
                                'name': node.name, 'line': node.lineno})
    with OUT.open('w', newline='', encoding='utf-8') as fh:
        writer = csv.DictWriter(fh, ['module', 'kind', 'name', 'line'])
        writer.writeheader()
        writer.writerows(entries)
    print(f'Indexed {len(entries)} definitions across {len(list(LEGACY.glob("*.py")))} preserved source modules.')
    print(f'Index: {OUT}')


if __name__ == '__main__':
    main()
