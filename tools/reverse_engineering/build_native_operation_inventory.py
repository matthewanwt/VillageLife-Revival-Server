"""Join Ghidra's native route and string-reference exports into a CSV inventory.

The APK and Ghidra exports are user-provided/private inputs. This tool only
reads those TSV/TXT files and project source; it does not extract assets.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--routes", type=Path, required=True,
                        help="native_routes_strict.txt")
    parser.add_argument("--references", type=Path, required=True,
                        help="Ghidra route_references.tsv")
    parser.add_argument("--string-xrefs", type=Path, required=True,
                        help="Ghidra script_string_xrefs.tsv")
    parser.add_argument("--source", type=Path, required=True,
                        help="Repository src/villagelife/protocol/original_client")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    routes = [line.strip() for line in args.routes.read_text(encoding="utf-8").splitlines()
              if line.strip()]
    refs = read_tsv(args.references)
    xrefs = read_tsv(args.string_xrefs)
    source_text = "\n".join(p.read_text(encoding="utf-8", errors="replace")
                             for p in args.source.glob("*.py"))
    xrefs_by_function: dict[str, set[str]] = {}
    for row in xrefs:
        xrefs_by_function.setdefault(row["function_name"], set()).add(row["string_value"])

    transport = {"ClientService/Login", "ClientService/Process"}
    columns = ("route", "operation_kind", "route_function", "function_entry",
               "request_or_format_strings", "literal_in_current_backend")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for route in routes:
            matches = [row for row in refs if row["route"] == route]
            # Keep every wrapper: one network operation may have more than one
            # native call site (for example, different call-data variants).
            if not matches:
                matches = [{"function_name": "", "function_entry": ""}]
            for match in matches:
                function = match["function_name"]
                fragments = sorted(value for value in xrefs_by_function.get(function, set())
                                   if any(mark in value for mark in (":", "{", "}"))
                                   and value != route)
                writer.writerow({
                    "route": route,
                    "operation_kind": ("client_transport" if route in transport else
                                       "client_rpc" if route.startswith("Client") else
                                       "platform_service"),
                    "route_function": function,
                    "function_entry": match["function_entry"],
                    "request_or_format_strings": " | ".join(fragments),
                    "literal_in_current_backend": "yes" if route in source_text else "no",
                })


if __name__ == "__main__":
    main()
