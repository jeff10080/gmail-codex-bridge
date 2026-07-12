from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS routes (
  gmail_thread_id TEXT PRIMARY KEY,
  codex_thread_id TEXT NOT NULL UNIQUE,
  routing_code TEXT NOT NULL UNIQUE,
  subject TEXT NOT NULL,
  last_message_id_header TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS inbox (
  gmail_message_id TEXT PRIMARY KEY,
  gmail_thread_id TEXT NOT NULL,
  codex_thread_id TEXT,
  body TEXT NOT NULL,
  state TEXT NOT NULL CHECK(state IN ('queued','running','done','failed','quarantined')),
  attempts INTEGER NOT NULL DEFAULT 0,
  error TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS inbox_fifo ON inbox(codex_thread_id, state, created_at);
CREATE TABLE IF NOT EXISTS outbox (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  dedupe_key TEXT NOT NULL UNIQUE,
  codex_thread_id TEXT NOT NULL,
  state TEXT NOT NULL CHECK(state IN ('sending','sent','uncertain','failed')),
  gmail_message_id TEXT,
  gmail_thread_id TEXT,
  error TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS quarantine (
  gmail_message_id TEXT PRIMARY KEY,
  gmail_thread_id TEXT NOT NULL,
  reason TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


class Database:
    def __init__(self, path: Path):
        self.path = path
        self._local = threading.local()
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def add_route(
        self,
        gmail_thread_id: str,
        codex_thread_id: str,
        routing_code: str,
        subject: str,
        last_message_id_header: str | None = None,
    ) -> None:
        with self.connection() as c:
            c.execute(
                """INSERT INTO routes VALUES(?,?,?,?,?,CURRENT_TIMESTAMP)
              ON CONFLICT(gmail_thread_id) DO UPDATE SET
              codex_thread_id=excluded.codex_thread_id, subject=excluded.subject,
              last_message_id_header=COALESCE(excluded.last_message_id_header,routes.last_message_id_header)""",
                (gmail_thread_id, codex_thread_id, routing_code, subject, last_message_id_header),
            )

    def route_for_gmail(self, thread_id: str):
        with self.connection() as c:
            return c.execute(
                "SELECT * FROM routes WHERE gmail_thread_id=?", (thread_id,)
            ).fetchone()

    def route_for_codex(self, thread_id: str):
        with self.connection() as c:
            return c.execute(
                "SELECT * FROM routes WHERE codex_thread_id=?", (thread_id,)
            ).fetchone()

    def enqueue(self, message_id: str, gmail_thread_id: str, body: str) -> str:
        route = self.route_for_gmail(gmail_thread_id)
        with self.connection() as c:
            c.execute("BEGIN IMMEDIATE")
            exists = c.execute(
                "SELECT state FROM inbox WHERE gmail_message_id=?", (message_id,)
            ).fetchone()
            if exists:
                c.commit()
                return "duplicate"
            if not route:
                c.execute(
                    "INSERT INTO inbox VALUES(?,?,NULL,?,'quarantined',0,NULL,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)",
                    (message_id, gmail_thread_id, body),
                )
                c.execute(
                    "INSERT OR IGNORE INTO quarantine VALUES(?,?,?,CURRENT_TIMESTAMP)",
                    (message_id, gmail_thread_id, "route_not_found"),
                )
                c.commit()
                return "quarantined"
            c.execute(
                "INSERT INTO inbox VALUES(?,?,?,?,'queued',0,NULL,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)",
                (message_id, gmail_thread_id, route["codex_thread_id"], body),
            )
            c.commit()
            return "queued"

    def ready_threads(self) -> list[str]:
        with self.connection() as c:
            return [
                r[0]
                for r in c.execute(
                    "SELECT DISTINCT codex_thread_id FROM inbox WHERE state='queued' ORDER BY created_at"
                )
            ]

    def claim_next(self, codex_thread_id: str):
        with self.connection() as c:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute(
                "SELECT * FROM inbox WHERE codex_thread_id=? AND state='queued' ORDER BY created_at,rowid LIMIT 1",
                (codex_thread_id,),
            ).fetchone()
            if row:
                c.execute(
                    "UPDATE inbox SET state='running',attempts=attempts+1,updated_at=CURRENT_TIMESTAMP WHERE gmail_message_id=? AND state='queued'",
                    (row["gmail_message_id"],),
                )
            c.commit()
            return row

    def finish(self, message_id: str, error: str | None = None) -> None:
        with self.connection() as c:
            c.execute(
                "UPDATE inbox SET state=?,error=?,updated_at=CURRENT_TIMESTAMP WHERE gmail_message_id=?",
                ("failed" if error else "done", error, message_id),
            )

    def reset_interrupted(self) -> None:
        with self.connection() as c:
            c.execute(
                "UPDATE inbox SET state='queued',updated_at=CURRENT_TIMESTAMP WHERE state='running'"
            )
