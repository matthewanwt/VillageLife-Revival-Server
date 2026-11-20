"""Request-owned entity indexes; never persisted or shared between players."""
from contextlib import contextmanager
from contextvars import ContextVar

_indexes = ContextVar('world_entity_indexes', default=None)


@contextmanager
def entity_scope():
    if _indexes.get() is not None:
        yield
        return
    token = _indexes.set({})
    try:
        yield
    finally:
        _indexes.reset(token)


def entities_for_id(state, ident, kind=None):
    if not isinstance(ident, str):
        return []
    entities = state.get('world', {}).get('entities', [])
    cache = _indexes.get()
    key = (id(entities), len(entities))
    stored = cache.get(key) if cache is not None else None
    if stored is None:
        index = {}
        for entity in entities:
            index.setdefault(entity.get('id'), []).append(entity)
        stored = (entities, index)
        if cache is not None:
            if len(cache) >= 8:
                cache.clear()
            cache[key] = stored
    return [value for value in stored[1].get(ident, ()) if kind is None or value.get('templateType') == kind]


def find_entity(state, ident, kind=None):
    return next(iter(entities_for_id(state, ident, kind)), None)
