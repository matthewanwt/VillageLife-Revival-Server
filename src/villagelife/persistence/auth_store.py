"""Hashed account tokens for the *new* API, not the original game protocol."""
from __future__ import annotations
import hashlib
import secrets
import time
from villagelife.core.errors import NotFound
from .sqlite_store import SqliteSaveRepository

SCHEMA = '''
CREATE TABLE IF NOT EXISTS api_tokens (
 token_digest TEXT PRIMARY KEY,
 account_id TEXT NOT NULL REFERENCES accounts(account_id),
 created_at INTEGER NOT NULL,
 revoked_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_api_tokens_account ON api_tokens(account_id);
'''


class AccountTokens:
    def __init__(self, repo: SqliteSaveRepository):
        self.repo = repo
        with repo.connect() as db:
            db.executescript(SCHEMA)

    def issue(self, account_id: str) -> str:
        token = secrets.token_urlsafe(40)
        digest = hashlib.sha256(token.encode('ascii')).hexdigest()
        with self.repo.transaction() as db:
            exists = db.execute('SELECT 1 FROM accounts WHERE account_id=?', (account_id,)).fetchone()
            if not exists:
                raise NotFound('Unknown account')
            db.execute('INSERT INTO api_tokens VALUES (?,?,?,NULL)',
                       (digest, account_id, int(time.time())))
        return token

    def authenticate(self, authorization: str | None) -> str | None:
        scheme, _, token = (authorization or '').partition(' ')
        if scheme.lower() != 'bearer' or not 32 <= len(token) <= 256:
            return None
        digest = hashlib.sha256(token.encode('utf-8')).hexdigest()
        with self.repo.connect() as db:
            row = db.execute('SELECT account_id FROM api_tokens WHERE token_digest=? AND revoked_at IS NULL',
                             (digest,)).fetchone()
        return row['account_id'] if row else None

    def revoke(self, token: str) -> None:
        digest = hashlib.sha256(token.encode('utf-8')).hexdigest()
        with self.repo.transaction() as db:
            db.execute('UPDATE api_tokens SET revoked_at=? WHERE token_digest=? AND revoked_at IS NULL',
                       (int(time.time()), digest))
