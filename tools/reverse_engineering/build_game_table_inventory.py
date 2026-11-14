"""Export names, row counts and field names from the user's parsed game tables."""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("database", type=Path, help="Parsed game_tables.sqlite")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    uri = f"file:{args.database.resolve().as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as db:
        tables = db.execute(
            "SELECT id, name, declared_rows, actual_rows FROM game_tables ORDER BY name"
        ).fetchall()
        rows = []
        for ident, name, declared, actual in tables:
            fields: set[str] = set()
            for (payload,) in db.execute(
                    "SELECT fields_json FROM game_rows WHERE table_id=?", (ident,)):
                value = json.loads(payload)
                if isinstance(value, dict):
                    fields.update(map(str, value))
            rows.append({"table": name, "declared_rows": declared,
                         "actual_rows": actual, "field_names": " | ".join(sorted(fields))})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=("table", "declared_rows",
                                                    "actual_rows", "field_names"))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
