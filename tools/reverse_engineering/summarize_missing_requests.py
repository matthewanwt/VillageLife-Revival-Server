"""Write a value-free operation summary from a launcher diagnostics JSON."""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("capture", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    document = json.loads(args.capture.read_text(encoding="utf-8"))
    grouped: dict[str, dict] = defaultdict(
        lambda: {"count": 0, "codes": Counter(), "requests": set(), "responses": set(),
                 "missing_records": 0, "missing_record_calls": 0,
                 "missing_statuses": Counter()})
    for outcome in document.get("call_outcomes", []):
        if not isinstance(outcome, dict):
            continue
        route = str(outcome.get("service_shape", ""))
        if not route:
            continue
        item = grouped[route]
        count = int(outcome.get("count", 1))
        code = str(outcome.get("response_code", "unknown"))
        item["count"] += count
        item["codes"][code] += count
        item["requests"].add(str(outcome.get("request_shape", "")))
        item["responses"].add(str(outcome.get("response_shape", "")))
    for record in document.get("records", []):
        if not isinstance(record, dict):
            continue
        route = str(record.get("endpoint_shape", ""))
        if route:
            item = grouped[route]
            item["missing_records"] += 1
            item["missing_record_calls"] += int(record.get("count", 1))
            item["missing_statuses"][str(record.get("response_status", "unknown"))] += int(
                record.get("count", 1))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as stream:
        fields = ("service", "outcome_count", "response_code_counts", "request_shapes",
                  "response_shapes", "missing_record_count", "missing_record_calls",
                  "missing_record_status_counts")
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for route, item in sorted(grouped.items()):
            writer.writerow({
                "service": route,
                "outcome_count": item["count"],
                "response_code_counts": "; ".join(
                    f"{code}:{count}" for code, count in sorted(item["codes"].items())),
                "request_shapes": " | ".join(sorted(filter(None, item["requests"]))),
                "response_shapes": " | ".join(sorted(filter(None, item["responses"]))),
                "missing_record_count": item["missing_records"],
                "missing_record_calls": item["missing_record_calls"],
                "missing_record_status_counts": "; ".join(
                    f"{status}:{count}" for status, count in
                    sorted(item["missing_statuses"].items())),
            })


if __name__ == "__main__":
    main()
