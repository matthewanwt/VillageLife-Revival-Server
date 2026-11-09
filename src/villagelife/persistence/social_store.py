"""Future social graph: mutual consent, stable account IDs, transactional changes.

This is NOT wired to the original APK's social protocol yet.
"""
from __future__ import annotations
import time
from villagelife.core.errors import InvalidAction, NotFound
from villagelife.core.identity import pair_ids
from .sqlite_store import SqliteSaveRepository

SCHEMA = '''
CREATE TABLE IF NOT EXISTS friend_requests (
 requester TEXT NOT NULL REFERENCES accounts(account_id),
 recipient TEXT NOT NULL REFERENCES accounts(account_id),
 created_at INTEGER NOT NULL,
 PRIMARY KEY(requester,recipient),
 CHECK(requester<>recipient)
);
CREATE INDEX IF NOT EXISTS idx_pending_recipient ON friend_requests(recipient);
'''


class SocialRepository:
    def __init__(self, repo: SqliteSaveRepository):
        self.repo = repo
        with repo.connect() as db:
            db.executescript(SCHEMA)

    @staticmethod
    def _require_accounts(db, *ids):
        for ident in ids:
            if not db.execute('SELECT 1 FROM accounts WHERE account_id=?', (ident,)).fetchone():
                raise NotFound('Account not found')

    def request_friend(self, requester: str, recipient: str) -> bool:
        if requester == recipient:
            raise InvalidAction('Cannot friend your own account')
        left, right = pair_ids(requester, recipient)
        with self.repo.transaction() as db:
            self._require_accounts(db, requester, recipient)
            if db.execute('SELECT 1 FROM friendships WHERE left_account=? AND right_account=?',
                          (left, right)).fetchone():
                return False
            row = db.execute('SELECT 1 FROM friend_requests WHERE requester=? AND recipient=?',
                             (requester, recipient)).fetchone()
            if row:
                return False
            db.execute('INSERT INTO friend_requests VALUES (?,?,?)',
                       (requester, recipient, int(time.time())))
            return True

    def accept_friend(self, recipient: str, requester: str) -> bool:
        left, right = pair_ids(recipient, requester)
        with self.repo.transaction() as db:
            self._require_accounts(db, recipient, requester)
            pending = db.execute('SELECT 1 FROM friend_requests WHERE requester=? AND recipient=?',
                                 (requester, recipient)).fetchone()
            if not pending:
                return False
            db.execute('DELETE FROM friend_requests WHERE (requester=? AND recipient=?) OR (requester=? AND recipient=?)',
                       (requester, recipient, recipient, requester))
            db.execute('INSERT OR IGNORE INTO friendships VALUES (?,?,?)',
                       (left, right, int(time.time())))
            return True

    def friends(self, account_id: str) -> list[str]:
        with self.repo.connect() as db:
            rows = db.execute('SELECT left_account,right_account FROM friendships '
                              'WHERE left_account=? OR right_account=?', (account_id, account_id)).fetchall()
        return sorted([r['right_account'] if r['left_account'] == account_id else r['left_account']
                       for r in rows])

    def pending(self, recipient: str) -> list[str]:
        with self.repo.connect() as db:
            rows = db.execute('SELECT requester FROM friend_requests WHERE recipient=? ORDER BY created_at',
                              (recipient,)).fetchall()
        return [r['requester'] for r in rows]

    def remove_friend(self, account_id: str, other: str) -> bool:
        left, right = pair_ids(account_id, other)
        with self.repo.transaction() as db:
            cur = db.execute('DELETE FROM friendships WHERE left_account=? AND right_account=?', (left, right))
            db.execute('DELETE FROM friend_requests WHERE (requester=? AND recipient=?) OR (requester=? AND recipient=?)',
                       (account_id, other, other, account_id))
            return cur.rowcount > 0
