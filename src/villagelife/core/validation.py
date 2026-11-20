"""Boundary validation. Reject invalid state rather than silently repairing it."""
from __future__ import annotations
from typing import Any
import math
from .errors import InvalidAction


def validate_json_tree(value: Any, *, max_depth: int = 80, max_nodes: int | None = None) -> None:
    """Check JSON-serialisable data, including finite numbers and bounded nesting."""
    nodes = 0
    def visit(obj: Any, depth: int) -> None:
        nonlocal nodes
        nodes += 1
        if max_nodes is not None and nodes > max_nodes:
            raise InvalidAction('JSON contains too many values')
        if depth > max_depth:
            raise InvalidAction('Save exceeds nesting limit')
        if obj is None or isinstance(obj, (bool, str, int)):
            return
        if isinstance(obj, float):
            if not math.isfinite(obj):
                raise InvalidAction('Save contains a non-finite number')
            return
        if isinstance(obj, list):
            for child in obj:
                visit(child, depth + 1)
            return
        if isinstance(obj, dict):
            if not all(isinstance(k, str) for k in obj):
                raise InvalidAction('Save object keys must be strings')
            for child in obj.values():
                visit(child, depth + 1)
            return
        raise InvalidAction(f'Non-JSON state value: {type(obj).__name__}')
    visit(value, 0)


def require_native(snapshot) -> None:
    """Opaque imported legacy saves must not be processed as reconstructed rules."""
    if snapshot.format != 'native.v1' or snapshot.schema_version != 1:
        raise InvalidAction('This save requires an explicit verified format migration')
