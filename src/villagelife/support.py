"""Privacy-minimised diagnostics: JSON key/type shapes only, no values or identifiers."""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from collections import Counter
import json
import os
import re
import tempfile
import uuid
import zipfile
import logging
from contextvars import ContextVar
from contextlib import contextmanager
from villagelife.persistence.sqlite_store import SqliteSaveRepository

_batch = ContextVar('diagnostic_batch', default=None)


@contextmanager
def batch_diagnostics(repo):
    """Keep diagnostic counters off the per-RPC durable commit path."""
    if _batch.get() is not None:
        yield
        return
    statements = []
    token = _batch.set((repo, statements))
    try:
        yield
    finally:
        _batch.reset(token)
        if statements:
            try:
                with repo.transaction() as db:
                    for sql, params in statements:
                        db.execute(sql, params)
                    if repo.diagnostic_run:
                        for phase, (count, total, maximum) in getattr(repo._local, 'timings', {}).items():
                            db.execute('INSERT INTO request_timings VALUES (?,?,?,?,?) '
                                'ON CONFLICT(run_id,phase) DO UPDATE SET count=count+excluded.count, '
                                'total_ms=total_ms+excluded.total_ms,max_ms=max(max_ms,excluded.max_ms)',
                                (repo.diagnostic_run, phase, count, total, maximum))
            except Exception:
                logging.getLogger(__name__).warning('Diagnostic batch could not be saved (%d statements)',
                                                    len(statements))


@contextmanager
def diagnostic_transaction(repo):
    current = _batch.get()
    if current is None or current[0] is not repo:
        with repo.transaction() as db:
            yield db
    else:
        class Buffer:
            def execute(self, sql, params=()):
                if len(current[1]) >= 2000:
                    raise ValueError('Diagnostic batch limit reached')
                current[1].append((sql, params))
        yield Buffer()

ALLOWED = {'/web/ClientService/Login', '/web/ClientService/Process', '/health',
           '/Playdemic.Community.Web/Client/Home', '/web/Playdemic.Community.Web/Client/Home',
           'CharacterRequest/Create', 'CharacterRequest/GetReceived', 'CharacterRequest/Delete',
           'ApplicationSetting/Get', 'User/Get', 'UserMessage/GetInbox', 'Friendship/GetByUser',
           'MaterialRequest/GetReceived', 'Group/GetTop', 'User/GetTop'}


def endpoint_shape(path: str) -> str:
    """Keep only a fixed allowlist or a structural count, never user-supplied text."""
    if path in ALLOWED:
        return path
    if re.fullmatch(r'(?:Client|Friend|Community)[A-Za-z0-9]{0,60}/[A-Za-z0-9]{1,90}',path):
        return path
    return '/unrecognised/' + str(min(10, len([p for p in path.split('/') if p])))


def begin_diagnostic_run(repo: SqliteSaveRepository) -> None:
    """Start fresh counters after the server has successfully bound its port."""
    run_id = uuid.uuid4().hex
    with repo.transaction() as db:
        db.execute("INSERT OR REPLACE INTO metadata VALUES ('latest_diagnostic_run', ?)", (run_id,))
        db.execute('DELETE FROM diagnostic_run_outcomes')
        db.execute('DELETE FROM request_timings')
    repo.diagnostic_run = run_id


def _record_run_outcome(db, run_id: str, method: str, endpoint: str, status: int,
                        request_shape: str = '', response_shape: str = '') -> None:
    now = int(datetime.now(timezone.utc).timestamp())
    db.execute("""INSERT INTO diagnostic_run_outcomes
                  (run_id, method, endpoint_shape, response_code, request_shape, response_shape, count, last_seen)
                  SELECT ?, ?, ?, ?, ?, ?, 1, ?
                  WHERE (SELECT value FROM metadata WHERE key='latest_diagnostic_run') = ?
                  ON CONFLICT DO UPDATE SET count=count+1, last_seen=excluded.last_seen""",
               (run_id, method, endpoint, status, request_shape, response_shape, now, run_id))


def record_missing(repo: SqliteSaveRepository, method: str, path: str, status: int) -> None:
    if method not in ('GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'RPC') or status not in (404, 501):
        return
    shape = endpoint_shape(path)
    with diagnostic_transaction(repo) as db:
        if repo.diagnostic_run:
            _record_run_outcome(db, repo.diagnostic_run, method, shape, status)
            return
        db.execute('''INSERT INTO missing_requests (method, endpoint_shape, response_status, count, last_seen)
                      VALUES (?,?,?,?,?)
                      ON CONFLICT(method, endpoint_shape, response_status) DO UPDATE SET
                      count=count+1, last_seen=excluded.last_seen''',
                   (method, shape, status, 1, int(datetime.now(timezone.utc).timestamp())))


def _response_shape(value, depth: int = 0) -> str:
    """Summarize JSON structure without retaining any response values."""
    if isinstance(value, dict):
        if depth >= 3:
            return 'object'
        fields = []
        for key in sorted(value)[:32]:
            name = str(key)
            if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,80}', name):
                name = 'other'
            fields.append(name + ':' + _response_shape(value[key], depth + 1))
        return 'object{' + ','.join(fields) + ('ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¦' if len(value) > 32 else '') + '}'
    if isinstance(value, list):
        if not value:
            return 'array'
        forms = sorted({_response_shape(item, depth + 1) for item in value[:4]})
        return 'array<' + '|'.join(forms[:4]) + ('|ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¦' if len(forms) > 4 else '') + '>'
    if value is None:
        return 'null'
    if isinstance(value, bool):
        return 'boolean'
    if isinstance(value, (int, float)):
        return 'number'
    if isinstance(value, str):
        return 'string'
    return 'other'


def _world_entity_summary(service: str, response: dict | None) -> str:
    """Summarize area/startup entity presence without exporting IDs or save values."""
    if not isinstance(response, dict):
        return ''
    if service == 'ClientStartupService/GetStartupInfo':
        world = response.get('world')
        entities = world.get('entities') if isinstance(world, dict) else None
    elif service == 'ClientStartupService/GetAreaContent':
        area = response.get('areaJson')
        entities = area.get('entities') if isinstance(area, dict) else None
    else:
        return ''
    if not isinstance(entities, list):
        return '|world_entities=missing_or_invalid'
    kinds = Counter()
    material_sources = Counter()
    villager_templates = Counter()
    shelter_beds = Counter()
    persisted = Counter()
    for entity in entities:
        if not isinstance(entity, dict):
            continue
        persisted[str(entity.get('serverPersisted')).lower()] += 1
        kind = entity.get('templateType')
        if isinstance(kind, str) and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,60}', kind):
            kinds[kind] += 1
        else:
            kinds['other'] += 1
        if kind == 'shelter':
            beds = entity.get('beds')
            if not isinstance(beds, list) or not beds:
                shelter_beds['none'] += 1
            else:
                for bed in beds:
                    if isinstance(bed, dict) and isinstance(bed.get('bed'), dict):
                        shelter_beds['wrapped'] += 1
                    elif isinstance(bed, dict) and 'shelterSlotID' in bed:
                        shelter_beds['flat'] += 1
                    else:
                        shelter_beds['invalid'] += 1
        if kind == 'villager_type':
            template_id = entity.get('templateId')
            key = str(template_id) if type(template_id) is int and 0 <= template_id <= 100 else 'other'
            villager_templates[key] += 1
        if kind == 'material_source':
            template_id = entity.get('templateId')
            if type(template_id) is int and 0 <= template_id <= 100000:
                material_sources[str(template_id)] += 1
            else:
                material_sources['other'] += 1
    kind_text = ','.join(f'{key}:{kinds[key]}' for key in sorted(kinds))[:1000]
    source_text = ','.join(f'{key}:{material_sources[key]}' for key in sorted(material_sources))[:500]
    persisted_text = ','.join(f'{key}:{persisted[key]}' for key in sorted(persisted))
    bed_text = ','.join(f'{key}:{shelter_beds[key]}' for key in sorted(shelter_beds))
    villager_text = ','.join(f'{key}:{villager_templates[key]}' for key in sorted(villager_templates))
    return (f'|world_entities={len(entities)};types={{{kind_text}}};'
            f'material_source_template_ids={{{source_text}}};server_persisted={{{persisted_text}}};'
            f'shelter_beds={{{bed_text}}};villager_templates={{{villager_text}}}')


WISH_CATEGORIES = {
    1: 'water', 2: 'food', 3: 'fun', 4: 'fire', 5: 'relationship',
    6: 'shelter', 8: 'caregiver', 9: 'retirement',
}


def _wish_summary(service: str, response: dict | None) -> str:
    if not isinstance(response, dict):
        return ''
    parts = []
    if service == 'ClientWant/AllWants' or service.startswith('ClientWant/Generate'):
        result = response.get('result')
        if isinstance(result, list):
            counts = Counter(
                WISH_CATEGORIES.get(want['wantableCategoryType'], 'other')
                for want in result if isinstance(want, dict)
                and type(want.get('wantableCategoryType')) is int
            )
            labels = ','.join(f'{name}:{counts[name]}' for name in sorted(counts))
            parts.append(f'|pending_wishes={{{labels}}}')
    cleared = response.get('SatisfiedWantModels')
    if isinstance(cleared, list):
        parts.append(f'|wishes_cleared={len(cleared)}')
    return ''.join(parts)


def _failure_category(service: str, message: str | None) -> str:
    """Map a failure to a fixed label; never persist raw exception text or values."""
    if not message:
        return 'unspecified'
    text = message.casefold()
    if 'not implemented' in text or 'not recovered' in text:
        return 'rule_not_recovered'
    groups = {
        'community_session_unavailable': ('community identity unavailable',),
        'npc_candidate_unavailable': ('unknown private npc candidate',),
        'task_family': ('task family mismatch',),
        'actor_missing_or_wrong_area': ('villager not found', 'villager in another village',
                                        'unknown villager', 'villager is in another area'),
        'actor_cannot_work': ('villager cannot work', 'villager is excluded', 'villager is lighting'),
        'actor_busy': ('villager is already working', 'villager already has unfinished work',
                       'collect existing villager work before transfer',
                       'finish lighting the fire before transferring'),
        'area_locked': ('unlock preceding village first', 'village level too low to unlock',
                        'area has not been unlocked'),
        'transfer_selection_invalid': ('owned villagerids array required', 'duplicate villager id'),
        'transfer_spawn_unavailable': ('destination workshop location is missing',),
        'foundation_missing': ('no matching construction foundation', 'no matching workshop or foundation'),
        'foundation_type_invalid': ('invalid foundation type',),
        'foundation_already_present': ('foundation type already placed', 'building type already exists',
                                       'building type is already under construction'),
        'decor_delete_missing': ('unknown saved decoration in active area',),
        'quest_objective_incomplete': ('quest objective has not been reached',),
        'placement_wrong_area': ('unknown placement area',),
        'upgrade_target_missing': ('no matching building available to upgrade',
                                   'no matching existing building to upgrade'),
        'wrong_area': ('task source must be in active area', 'wrong gathering area'),
        'position_invalid_or_out_of_range': ('invalid task position', 'invalid gathering position',
                                             'task position is not close', 'gathering position is not near'),
        'task_unlock_requirement': ('task unlock requirement is not met',),
        'task_material_requirement': ('task material requirements not met',
                                      'insufficient material for task',
                                      'insufficient gathering requirement', 'insufficient gathering materials'),
        'source_identifier_missing_or_invalid': ('source identifier required', 'source identifier must be a string'),
        'source_not_found': ('source not found',),
        'workshop_table_mismatch': ('recipe requires another workshop table',),
        'workshop_full': ('workshop is full',),
        'decor_definition_invalid': ('integer decor identifier required', 'unknown decor_item identifier'),
        'decor_scenery': ('scenery cannot be placed as decor',),
        'decor_area_invalid': ('unknown placement area',),
        'decor_position_invalid': ('both placement coordinates are required', 'invalid placement coordinates',
                                   'placement outside local world bounds'),
        'decor_already_placed': ('this decor item is already placed',),
        'learning_locked': ('learning requires a higher', 'learn the parent material',
                            'material belongs to an unavailable area', 'learning prerequisite'),
        'learning_slots_full': ('all learning slots',),
        'learning_not_ready': ('learning timer has not finished', 'start learning this material first'),
        'decor_locked': ('decor unlock requirement is not met',),
        'insufficient_gems': ('this action costs',),
        'decor_insufficient_currency': ('insufficient currency for decor',),
        'source_busy': ('resource source is already occupied',),
        'unknown_task_or_definition': ('unknown task', 'unknown building_task identifier',
                                       'unknown building_type identifier'),
        'shelter_bed_unknown': ('unknown bed in this village', 'bed identifier required'),
        'shelter_bed_occupied': ('bed is occupied',),
        'shelter_wrong_area': ('shelter is in another area',),
        'shelter_without_occupants': ('shelter has no occupants',),
    }
    for category, phrases in groups.items():
        if any(phrase in text for phrase in phrases):
            return category
    if service.startswith('ClientUserShelterService/'):
        return 'shelter_validation_rejected'
    if service == 'ClientVillagerService/PerformFunActivity':
        return 'fun_validation_rejected'
    return 'validation_rejected' if service.startswith('ClientTaskService/') else 'request_rejected'


def record_original_call(repo: SqliteSaveRepository, service: str, status: int,
                         response: dict | None = None, request: dict | None = None,
                         failure_message: str | None = None) -> None:
    """Aggregate RPC outcome and JSON structures, never IDs or values."""
    if not isinstance(status, int) or isinstance(status, bool) or not 100 <= status <= 599:
        return
    shape = endpoint_shape(service)
    result_shape = (_response_shape(response if response is not None else {}) +
                    _world_entity_summary(service, response) + _wish_summary(service, response))[:5500]
    if status >= 400:
        result_shape = (result_shape + '|failure=' + _failure_category(service, failure_message))[:5500]
    request_shape = _response_shape(request if request is not None else {})[:4000]
    with diagnostic_transaction(repo) as db:
        if repo.diagnostic_run:
            _record_run_outcome(db, repo.diagnostic_run, 'CALL', shape, status, request_shape, result_shape)
            if status == 200:
                db.execute("DELETE FROM diagnostic_run_outcomes WHERE run_id=? AND method='RPC' "
                           "AND endpoint_shape=? AND response_code=501", (repo.diagnostic_run, shape))
            return
        db.execute('''INSERT INTO original_call_outcomes
                      (service_shape, response_code, response_shape, count, last_seen)
                      VALUES (?,?,?,?,?)
                      ON CONFLICT(service_shape, response_code, response_shape) DO UPDATE SET
                      count=count+1, last_seen=excluded.last_seen''',
                   (shape, status, result_shape, 1, int(datetime.now(timezone.utc).timestamp())))
        db.execute('''INSERT INTO original_call_request_outcomes
                      (service_shape, response_code, request_shape, response_shape, count, last_seen)
                      VALUES (?,?,?,?,?,?)
                      ON CONFLICT(service_shape, response_code, request_shape, response_shape) DO UPDATE SET
                      count=count+1, last_seen=excluded.last_seen''',
                   (shape, status, request_shape, result_shape, 1, int(datetime.now(timezone.utc).timestamp())))
        if status == 200:
            # A later success resolves an older unsupported-operation marker;
            # leave the current response shape in call_outcomes for debugging.
            db.execute("DELETE FROM missing_requests WHERE method='RPC' AND endpoint_shape=? AND response_status=501",
                       (shape,))


def export_missing(repo: SqliteSaveRepository, target: Path | None = None,
                   *, current_run_only: bool = False) -> Path:
    if target is None:
        target = repo.path.parent / 'reports' / ('missing-requests-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '.zip')
    target = Path(target).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise FileExistsError(target)
    with repo.connect() as db:
        db.execute('BEGIN')
        timings = [dict(row) for row in db.execute('SELECT phase,count,total_ms,max_ms FROM request_timings '
                    "WHERE run_id=(SELECT value FROM metadata WHERE key='latest_diagnostic_run')")]
        run = db.execute("SELECT value FROM metadata WHERE key='latest_diagnostic_run'").fetchone()
        if run is not None:
            rows = [dict(row) for row in db.execute('''
                SELECT method, endpoint_shape, response_code AS response_status, count, last_seen
                FROM diagnostic_run_outcomes WHERE run_id=? AND method!='CALL'
                ORDER BY count DESC LIMIT 2000''', (run['value'],))]
            calls = [dict(row) for row in db.execute('''
                SELECT endpoint_shape AS service_shape, response_code, request_shape,
                       response_shape, count, last_seen
                FROM diagnostic_run_outcomes WHERE run_id=? AND method='CALL'
                ORDER BY last_seen DESC, count DESC LIMIT 2000''', (run['value'],))]
            scope = 'latest_server_run'
            note = 'Counts cover the latest server run. Stop and start the server to begin a fresh capture.'
        elif current_run_only:
            rows, calls = [], []
            scope = 'no_server_run'
            note = 'Start the updated server to record a new capture.'
        else:
            rows = [dict(r) for r in db.execute('SELECT method, endpoint_shape, response_status, count, last_seen FROM missing_requests ORDER BY count DESC LIMIT 2000')]
            calls = [dict(r) for r in db.execute('SELECT service_shape, response_code, request_shape, response_shape, count, last_seen FROM original_call_request_outcomes ORDER BY last_seen DESC, count DESC LIMIT 2000')]
            scope = 'legacy_history'
            note = 'Counts are cumulative across runs.'
    data = {'format': 'VillageLifeMissingRequestsV1', 'contains_saves': False, 'scope': scope,
            'performance_timings': timings,
            'note': (note + ' last_seen is UTC Unix time. Aggregated RPC request/response keys and JSON types; startup/area responses also include entity-type counts, material-source template-ID counts, and shelter bed layout counts. Wish outcomes include aggregate pending and cleared counts. No raw request/response values, entity IDs, call IDs, session tokens, save contents or player identifiers.'),
            'records': rows, 'call_outcomes': calls}
    with zipfile.ZipFile(target, 'x', compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr('missing-requests.json', json.dumps(data, indent=2))
    return target


def export_support(target: Path, binding: Path) -> Path:
    target = Path(target).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise FileExistsError(target)
    receipt = {'format': 'VillageLifeSupportV1', 'has_instance_binding': binding.is_file(),
               'os_family': os.name, 'no_save_contents': True,
               'warning': 'Read report before sending. A network policy has NOT been verified.'}
    if binding.is_file():
        try:
            data = json.loads(binding.read_text(encoding='utf-8'))
            receipt['instance_id'] = data.get('id')
            receipt['adb_port'] = data.get('adb_port')
            receipt['name_changed_hint'] = 'Compare against BlueStacks Manager if setup fails.'
        except (ValueError, OSError):
            receipt['binding_error'] = 'unreadable'
    with zipfile.ZipFile(target, 'x', compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr('diagnostics.json', json.dumps(receipt, indent=2))
    return target
