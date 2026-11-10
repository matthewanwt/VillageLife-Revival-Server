"""Privacy-minimised telemetry for *unimplemented* original-client requests.

This deliberately records only operation names and coarse protocol shape, NEVER
request bodies, device IDs, villager names, auth headers, player IPs or messages.
It is separate from the legacy private full-traffic developer log.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import threading
import time
from urllib.parse import urlsplit

# A deliberately narrow syntax: a user-supplied free-text name is never accepted
# as an operation. Unknown / non-conforming services are represented by a hash.
_SERVICE = re.compile(r"^[A-Za-z][A-Za-z0-9_.]{0,63}/[A-Za-z][A-Za-z0-9_.]{0,63}$")
_MAX_FILE_BYTES = 1024 * 1024


def safe_operation(value: object) -> str:
    if isinstance(value, str) and _SERVICE.fullmatch(value):
        return value
    raw = str(value).encode('utf-8', 'replace')[:1024]
    return 'unrecognised-operation-sha256-' + hashlib.sha256(raw).hexdigest()[:16]


def safe_route(path: str) -> str:
    """Use static route names only; hash anything that might contain user data."""
    try:
        route = urlsplit(path).path.rstrip('/') or '/'
    except (TypeError, ValueError):
        route = '/'
    if route in ('/web/ClientService/Login', '/web/ClientService/Process',
                 '/Playdemic.Community.Web/Client/Home', '/health'):
        return route
    return 'unrecognised-route-sha256-' + hashlib.sha256(route.encode('utf-8', 'replace')[:4096]).hexdigest()[:16]


def _status(value: object) -> int:
    try:
        number = int(value)
        return number if number in (400, 404, 500, 501, 502, 503) else 0
    except (TypeError, ValueError):
        return 0


class MissingRequestRecorder:
    """Thread safe, bounded, opt-in exportable evidence (not a packet recorder)."""

    def __init__(self, destination: Path, *, clock=time.monotonic):
        self.destination = Path(destination)
        self.clock = clock
        self._lock = threading.Lock()
        self._counts: dict[tuple[str, str, str, int], int] = defaultdict(int)
        self._last_written: dict[tuple[str, str, str, int], float] = {}

    def record(self, *, method: str, route: str, operation: str = '', status: int = 501,
               category: str = 'not_implemented') -> None:
        if method not in ('GET', 'POST') or category not in ('not_implemented', 'known_rule_gap', 'server_failure'):
            return
        status = _status(status)
        if not status:
            return
        safe_path = safe_route(route)
        name = safe_operation(operation) if operation else None
        signature = (method, safe_path, name or '', status)
        with self._lock:
            self._counts[signature] += 1
            number = self._counts[signature]
            now = self.clock()
            # First hit immediately. Summarise repeats periodically (or every
            # 100 calls), avoiding runaway logs from a fast-retrying game.
            if number > 1 and number % 100 != 0 and now - self._last_written.get(signature, now) < 60:
                return
            self._last_written[signature] = now
            event = {
                'format': 'VillageLifeMissingRequestV1',
                'utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                'method': method, 'route': safe_path, 'operation': name,
                'status': status, 'category': category,
                'observed_this_session': number,
                'note': 'Counts are session-local; repeated entries are throttled.',
            }
            try:
                self.destination.parent.mkdir(parents=True, exist_ok=True)
                if self.destination.exists() and self.destination.stat().st_size >= _MAX_FILE_BYTES:
                    previous = self.destination.with_suffix('.previous.jsonl')
                    self.destination.replace(previous)
                with self.destination.open('a', encoding='utf-8') as output:
                    output.write(json.dumps(event, ensure_ascii=True, separators=(',', ':')) + '\n')
            except OSError:
                # Diagnostics are best-effort; NEVER fail a gameplay response.
                pass

    def rpc_failures(self, route: str, request: dict, response: dict, *, community: bool = False) -> None:
        """Match calls by ID, not by array position; capture only failures.

        The actual original game response is not modified.
        """
        source_data = request.get('data') if isinstance(request, dict) else {}
        response_data = response.get('data') if isinstance(response, dict) else {}
        calls = request.get('Calls', []) if community and isinstance(request, dict) else (source_data.get('calls', []) if isinstance(source_data, dict) else [])
        results = response_data if community else (response_data.get('calls', []) if isinstance(response_data, dict) else [])
        if not isinstance(calls, list) or not isinstance(results, list):
            return
        ids: dict[str, str] = {}
        for call in calls[:1000]:
            if isinstance(call, dict):
                call_id = str(call.get('Id', call.get('Id:', ''))) if community else str(call.get('id', ''))
                service = call.get('Service', '') if community else call.get('service', '')
                if call_id and call_id not in ids:
                    ids[call_id] = safe_operation(service)
        for result in results[:1000]:
            if not isinstance(result, dict):
                continue
            call_id = str(result.get('Id', '')) if community else str(result.get('id', ''))
            status = _status(result.get('code'))
            if status not in (500, 501, 502, 503, 400):
                continue
            message = str(result.get('message', ''))
            is_gap = status == 501 or (status == 400 and 'not implemented' in message.lower())
            if is_gap or status >= 500:
                self.record(method='POST', route=route, operation=ids.get(call_id, ''),
                            status=status, category='not_implemented' if status == 501 else
                            'known_rule_gap' if is_gap else 'server_failure')
