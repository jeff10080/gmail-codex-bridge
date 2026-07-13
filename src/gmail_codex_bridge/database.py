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
  project_key TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS inbox (
  gmail_message_id TEXT PRIMARY KEY,
  gmail_thread_id TEXT NOT NULL,
  codex_thread_id TEXT,
  project_key TEXT,
  subject TEXT,
  message_id_header TEXT,
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
            self._migrate(conn)

    @staticmethod
    def _migrate(conn: sqlite3.Connection) -> None:
        route_columns = {row[1] for row in conn.execute("PRAGMA table_info(routes)")}
        if "project_key" not in route_columns:
            conn.execute("ALTER TABLE routes ADD COLUMN project_key TEXT")
        inbox_columns = {row[1] for row in conn.execute("PRAGMA table_info(inbox)")}
        for name in ("project_key", "subject", "message_id_header"):
            if name not in inbox_columns:
                conn.execute(f"ALTER TABLE inbox ADD COLUMN {name} TEXT")

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
        project_key: str | None = None,
    ) -> None:
        with self.connection() as c:
            c.execute(
                """INSERT INTO routes(
                     gmail_thread_id,codex_thread_id,routing_code,subject,
                     last_message_id_header,project_key
                   ) VALUES(?,?,?,?,?,?)
              ON CONFLICT(gmail_thread_id) DO UPDATE SET
              codex_thread_id=excluded.codex_thread_id, subject=excluded.subject,
              last_message_id_header=COALESCE(
                excluded.last_message_id_header,routes.last_message_id_header
              ),
              project_key=COALESCE(excluded.project_key,routes.project_key)""",
                (
                    gmail_thread_id,
                    codex_thread_id,
                    routing_code,
                    subject,
                    last_message_id_header,
                    project_key,
                ),
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

    def route_for_code(self, routing_code: str):
        with self.connection() as c:
            return c.execute(
                "SELECT * FROM routes WHERE routing_code=?", (routing_code.upper(),)
            ).fetchone()

    def enqueue(
        self,
        message_id: str,
        gmail_thread_id: str,
        body: str,
        routing_code: str | None = None,
        *,
        project_key: str | None = None,
        subject: str = "",
        message_id_header: str | None = None,
    ) -> str:
        route = self.route_for_gmail(gmail_thread_id)
        if not route and routing_code:
            route = self.route_for_code(routing_code)
        with self.connection() as c:
            c.execute("BEGIN IMMEDIATE")
            exists = c.execute(
                "SELECT state FROM inbox WHERE gmail_message_id=?", (message_id,)
            ).fetchone()
            if exists:
                if exists["state"] == "quarantined" and route:
                    c.execute(
                        """UPDATE inbox SET codex_thread_id=?,state='queued',updated_at=CURRENT_TIMESTAMP
                           WHERE gmail_message_id=?""",
                        (route["codex_thread_id"], message_id),
                    )
                    c.execute("DELETE FROM quarantine WHERE gmail_message_id=?", (message_id,))
                    c.commit()
                    return "queued"
                c.commit()
                return "duplicate"
            if not route and not project_key:
                c.execute(
                    """INSERT INTO inbox(
                         gmail_message_id,gmail_thread_id,codex_thread_id,project_key,
                         subject,message_id_header,body,state
                       ) VALUES(?,?,NULL,NULL,?,?,?,'quarantined')""",
                    (message_id, gmail_thread_id, subject, message_id_header, body),
                )
                c.execute(
                    "INSERT OR IGNORE INTO quarantine VALUES(?,?,?,CURRENT_TIMESTAMP)",
                    (message_id, gmail_thread_id, "route_not_found"),
                )
                c.commit()
                return "quarantined"
            c.execute(
                """INSERT INTO inbox(
                     gmail_message_id,gmail_thread_id,codex_thread_id,project_key,
                     subject,message_id_header,body,state
                   ) VALUES(?,?,?,?,?,?,?,'queued')""",
                (
                    message_id,
                    gmail_thread_id,
                    route["codex_thread_id"] if route else None,
                    route["project_key"] if route else project_key,
                    subject,
                    message_id_header,
                    body,
                ),
            )
            c.commit()
            return "queued"

    def ready_threads(self) -> list[str]:
        with self.connection() as c:
            return [
                r[0]
                for r in c.execute(
                    """SELECT DISTINCT COALESCE(codex_thread_id,'gmail:' || gmail_thread_id)
                       FROM inbox WHERE state='queued' ORDER BY created_at"""
                )
            ]

    def claim_next(self, codex_thread_id: str):
        with self.connection() as c:
            c.execute("BEGIN IMMEDIATE")
            if codex_thread_id.startswith("gmail:"):
                row = c.execute(
                    """SELECT * FROM inbox
                       WHERE gmail_thread_id=? AND codex_thread_id IS NULL AND state='queued'
                       ORDER BY created_at,rowid LIMIT 1""",
                    (codex_thread_id.removeprefix("gmail:"),),
                ).fetchone()
            else:
                row = c.execute(
                    """SELECT * FROM inbox WHERE codex_thread_id=? AND state='queued'
                       ORDER BY created_at,rowid LIMIT 1""",
                    (codex_thread_id,),
                ).fetchone()
            if row:
                c.execute(
                    "UPDATE inbox SET state='running',attempts=attempts+1,updated_at=CURRENT_TIMESTAMP WHERE gmail_message_id=? AND state='queued'",
                    (row["gmail_message_id"],),
                )
            c.commit()
            return row

    def bind_gmail_thread(self, gmail_thread_id: str, codex_thread_id: str) -> None:
        with self.connection() as c:
            c.execute(
                """UPDATE inbox SET codex_thread_id=?,updated_at=CURRENT_TIMESTAMP
                   WHERE gmail_thread_id=? AND codex_thread_id IS NULL AND state='queued'""",
                (codex_thread_id, gmail_thread_id),
            )

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
