"""Export a small, privacy-conscious support bundle for community bug reports.

No saves, databases, APKs, tokens, full HTTP traces or raw Android logs.
Opt-in log excerpts should be sent privately and reviewed before sharing.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import socket
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SAFE_REPORTS = ("latest-runtime-error.json", "setup-network-check.json", "SETUP DIAGNOSTICS.json", "network-topology-report.json")
SAFE_SESSION_REPORTS = ("network-check.json", "environment.json", "result.json")


def redact(text: str) -> str:
    text = re.sub(r'(?i)(authorization\s*[:=]\s*)Bearer\s+[A-Za-z0-9_\-.+/=]+', r'\1Bearer [REDACTED]', text)
    text = re.sub(r'(?im)("?(?:join_code|access_token|password|secret|api_key)"?\s*[:=]\s*)(?:"[^"]*"|\S+)', r'\1[REDACTED]', text)
    text = re.sub(r'(?i)Bearer\s+[A-Za-z0-9_\-.+/=]+', 'Bearer [REDACTED]', text)
    text = re.sub(r'(?i)https?://[^\s"<>]+', lambda m: _scrub_url(m.group()), text)
    text = re.sub(r'(?i)([A-Z]:\\Users\\)[^\\\s"/]+', r'\1[USER]', text)
    text = re.sub(r'/home/[^/\s"\\]+', '/home/[USER]', text)
    text = re.sub(r'([A-Za-z0-9._%+-]+)@([A-Za-z0-9.-]+\.[A-Za-z]{2,})', '[EMAIL]', text)
    return text


def _scrub_url(url: str) -> str:
    from urllib.parse import urlsplit
    try:
        p = urlsplit(url)
        host = p.hostname or '[HOST]'
        if p.username or p.password or p.query or p.fragment:
            return f'{p.scheme}://{host}/[REDACTED]'
    except ValueError:
        return '[URL REDACTED]'
    return url


def _scrub_json(data):
    sensitive = {'join_code', 'authorization', 'access_token', 'password', 'secret', 'api_key', 'private_key', 'token'}
    if isinstance(data, dict):
        return {key: '[REDACTED]' if key.casefold() in sensitive else _scrub_json(value)
                for key, value in data.items()}
    if isinstance(data, list):
        return [_scrub_json(value) for value in data]
    if isinstance(data, str):
        return redact(data)
    return data


def _read_safe(path: Path, max_bytes=100_000):
    if not path.is_file() or path.stat().st_size > max_bytes:
        return None
    raw = path.read_text(encoding='utf-8', errors='replace')
    if path.suffix.lower() == '.json':
        try:
            return json.dumps(_scrub_json(json.loads(raw)), indent=2, ensure_ascii=False)
        except (ValueError, TypeError):
            pass
    return redact(raw)


def export_bundle(root: Path = ROOT, *, output_dir: Path | None = None, include_log_excerpts=False) -> Path:
    root = Path(root).resolve()
    out = output_dir or root / 'support'
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    target = out / f'VillageLife-Support-{stamp}.zip'
    session_root = root / 'experiments'
    sessions = sorted((p for p in session_root.glob('play-session-*') if p.is_dir()), reverse=True) if session_root.is_dir() else []
    latest = sessions[0] if sessions else None
    report = {
        'format': 'VillageLifeSupportV1', 'created_utc': datetime.now(timezone.utc).isoformat(),
        'platform': sys.platform, 'python_version': sys.version.split()[0],
        'includes_private_player_saves': False, 'includes_android_log': False,
        'note': 'Review the ZIP contents before sharing with a developer; diagnostics may reveal instance identifiers or machine configuration.',
        'session_found': bool(latest),
    }
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('support-summary.json', json.dumps(report, ensure_ascii=False, indent=2))
        for name in SAFE_REPORTS:
            content = _read_safe(root / name)
            if content is not None:
                z.writestr('reports/' + name, content)
        if latest:
            for name in SAFE_SESSION_REPORTS:
                content = _read_safe(latest / name)
                if content is not None:
                    z.writestr('session/' + name, content)
            if include_log_excerpts:
                for name in ('backend.log',):
                    log = latest / name
                    if log.is_file():
                        # Only lines mentioning failures, bounded to avoid copying
                        # huge gameplay payloads. Still review privately.
                        lines = log.read_text(encoding='utf-8', errors='replace')[-150_000:].splitlines()
                        excerpt = '\n'.join(x[:300] for x in lines if any(k in x.lower() for k in ('error', 'exception', 'traceback', 'warning')))[-15_000:]
                        z.writestr('optional/' + name + '.excerpt.txt', redact(excerpt))
    return target


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--include-log-excerpts', action='store_true', help='OPTIONAL: excerpts may contain sensitive information; review before sending')
    args = parser.parse_args()
    path = export_bundle(include_log_excerpts=args.include_log_excerpts)
    print('Support bundle saved: ' + str(path), flush=True)
    print('No saves, database, original game files or raw Android logs included.', flush=True)
    print('Please inspect the ZIP and share it only with trusted maintainers.', flush=True)


if __name__ == '__main__':
    main()
