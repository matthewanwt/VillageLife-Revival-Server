"""Lazy, lossless completed-action history, separate from the hot world JSON."""
from collections.abc import MutableMapping
import copy
import json
import zlib
from villagelife.core.limits import MAX_SAVE_BYTES

COLLECTIONS = frozenset({
    'workAreas', 'completedQuests', 'consumptionReceipts', 'directConsumptionReceipts',
    'habitatReceipts', 'funReceipts', 'interactiveReceipts', 'materialPurchaseReceipts',
    'storePurchaseReceipts', 'materialSaleReceipts', 'fortuneReceipts', 'levelCallReceipts',
    'levelReceipts',
})


def pack_record(raw):
    encoded = raw.encode('utf-8')
    if len(encoded) > MAX_SAVE_BYTES:
        raise ValueError('One archived action exceeds the supported size')
    if len(encoded) < 1024:
        return raw
    compressed = zlib.compress(encoded, 1)
    return b'VLH1' + len(encoded).to_bytes(4, 'little') + compressed if len(compressed) + 8 < len(encoded) else raw


def unpack_record(value):
    if isinstance(value, str):
        return value
    if not isinstance(value, bytes) or len(value) < 8 or value[:4] != b'VLH1':
        raise ValueError('Unsupported archived history encoding')
    size = int.from_bytes(value[4:8], 'little')
    if not 0 < size <= MAX_SAVE_BYTES:
        raise ValueError('Archived history exceeds the supported size')
    decoder = zlib.decompressobj()
    try:
        raw = decoder.decompress(value[8:], size + 1)
    except zlib.error as error:
        raise ValueError('Archived history is damaged') from error
    if len(raw) != size or not decoder.eof or decoder.unused_data:
        raise ValueError('Archived history integrity check failed')
    return raw.decode('utf-8')


class History(MutableMapping):
    def __init__(self, repo, village, name, active):
        self.repo, self.village, self.name = repo, village, name
        self.active = active
        self.loaded = {}
        self.original = {}
        self.deleted = set()

    def __getitem__(self, key):
        if key in self.deleted:
            raise KeyError(key)
        if key in self.active:
            return self.active[key]
        if key not in self.loaded:
            with self.repo.connect() as db:
                row = db.execute('SELECT payload_json FROM action_history WHERE village_id=? '
                                 'AND collection=? AND item_key=?', (self.village, self.name, key)).fetchone()
            if row is None:
                raise KeyError(key)
            self.original[key] = unpack_record(row[0])
            self.loaded[key] = json.loads(self.original[key])
        return self.loaded[key]

    def __setitem__(self, key, value):
        self.deleted.discard(key)
        self.active[key] = value

    def __delitem__(self, key):
        self[key]
        self.active.pop(key, None)
        self.loaded.pop(key, None)
        self.deleted.add(key)

    def __iter__(self):
        with self.repo.connect() as db:
            keys = [row[0] for row in db.execute('SELECT item_key FROM action_history '
                    'WHERE village_id=? AND collection=? ORDER BY item_key', (self.village, self.name))]
        return iter(dict.fromkeys(key for key in [*keys, *self.active] if key not in self.deleted))

    def __len__(self):
        return sum(1 for _ in self)

    def __deepcopy__(self, memo):
        return {key: copy.deepcopy(self[key], memo) for key in self}

    def active_values(self):
        return self.active.values()

    def persist(self, db, encode, validate):
        hot = {}
        for key in self.deleted:
            db.execute('DELETE FROM action_history WHERE village_id=? AND collection=? AND item_key=?',
                       (self.village, self.name, key))
        for key, value in {**self.loaded, **self.active}.items():
            validate(value)
            raw = encode(value)
            if self.name == 'workAreas' and not isinstance(value, dict):
                raise ValueError('Unsupported work history record')
            if self.name == 'workAreas' and value.get('status') not in {'harvested', 'cancelled'}:
                hot[key] = value
                if key in self.original:
                    db.execute('DELETE FROM action_history WHERE village_id=? AND collection=? AND item_key=?',
                               (self.village, self.name, key))
            elif raw != self.original.get(key):
                db.execute('INSERT INTO action_history VALUES (?,?,?,?) '
                           'ON CONFLICT(village_id,collection,item_key) DO UPDATE SET payload_json=excluded.payload_json',
                           (self.village, self.name, key, pack_record(raw)))
        return hot


def active_work(state):
    jobs = state.get('workAreas', {})
    return jobs.active_values() if isinstance(jobs, History) else jobs.values()


def json_default(value):
    if isinstance(value, History):
        return dict(value.items())
    raise TypeError('Unsupported JSON value: ' + type(value).__name__)
