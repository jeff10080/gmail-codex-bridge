from __future__ import annotations

import asyncio
import sqlite3

import pytest

from gmail_codex_bridge.database import Database
from gmail_codex_bridge.models import CodexResult, IncomingMessage, OutgoingReport, SendResult
from gmail_codex_bridge.service import BridgeService


class FakeGmail:
    def __init__(self, messages=()):
        self.messages = {m.id: m for m in messages}
        self.sent = []
        self.fail_send = False

    def list_candidate_ids(self, query):
        return list(self.messages)

    def get_message(self, message_id):
        return self.messages[message_id]

    def send(self, **kwargs):
        if self.fail_send:
            raise TimeoutError("unknown outcome")
        self.sent.append(kwargs)
        number = len(self.sent)
        return SendResult(
            f"sent-{number}", kwargs.get("thread_id") or f"gmail-{number}", f"<sent-{number}@local>"
        )


class FakeCodex:
    def __init__(self, delay=0):
        self.calls = []
        self.delay = delay
        self.active = 0
        self.max_active = 0
        self.started = []
        self.working_directories = []

    async def start(self, prompt, working_directory=None):
        self.started.append(prompt)
        await self._record("created-1", prompt, working_directory)
        return CodexResult(f"answer:{prompt}", thread_id="created-1")

    async def resume(self, thread_id, prompt, working_directory=None):
        await self._record(thread_id, prompt, working_directory)
        return CodexResult(f"answer:{prompt}", thread_id=thread_id)

    async def _record(self, thread_id, prompt, working_directory):
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        await asyncio.sleep(self.delay)
        self.calls.append((thread_id, prompt))
        self.working_directories.append(working_directory)
        self.active -= 1


def make_service(tmp_path, gmail=None, codex=None, **kwargs):
    return BridgeService(
        Database(tmp_path / "db.sqlite3"),
        gmail or FakeGmail(),
        codex or FakeCodex(),
        allowed_sender="user@example.com",
        recipient="user@example.com",
        gmail_query="from:user@example.com",
        max_parallel_threads=4,
        **kwargs,
    )


def incoming(mid, thread, body="hello", sender="user@example.com", recipient=""):
    return IncomingMessage(
        mid, thread, sender, "Re: report", body, f"<{mid}@gmail>", recipient=recipient
    )


def test_first_report_creates_route_and_successive_report_replies(tmp_path):
    gmail = FakeGmail()
    service = make_service(tmp_path, gmail=gmail)
    first = service.publish(OutgoingReport("codex-1", "Report", "one"), "first")
    service.publish(OutgoingReport("codex-1", "ignored", "two"), "second")
    assert first.thread_id == "gmail-1"
    assert gmail.sent[1]["thread_id"] == "gmail-1"
    assert gmail.sent[1]["subject"] == "Report"
    assert gmail.sent[1]["in_reply_to"] == "<sent-1@local>"


def test_scan_is_idempotent_and_rejects_wrong_sender(tmp_path):
    gmail = FakeGmail([incoming("m1", "g1"), incoming("evil", "g1", sender="other@example.com")])
    service = make_service(tmp_path, gmail=gmail)
    service.db.add_route("g1", "c1", "CX-111111", "Report")
    assert service.scan_once() == {"queued": 1, "duplicate": 0, "quarantined": 0, "rejected": 1}
    assert service.scan_once() == {"queued": 0, "duplicate": 1, "quarantined": 0, "rejected": 1}


def test_unknown_route_is_quarantined_without_codex(tmp_path):
    gmail = FakeGmail([incoming("m1", "unknown")])
    codex = FakeCodex()
    service = make_service(tmp_path, gmail, codex)
    assert service.scan_once()["quarantined"] == 1
    asyncio.run(service.drain())
    assert codex.calls == []
    with service.db.connection() as c:
        assert c.execute("SELECT count(*) FROM quarantine").fetchone()[0] == 1


def test_new_email_starts_thread_in_project_selected_by_plus_alias(tmp_path):
    message = incoming(
        "m1",
        "g1",
        "Nouvelle demande",
        recipient="agent+project-a@example.com",
    )
    gmail, codex = FakeGmail([message]), FakeCodex()
    service = make_service(
        tmp_path,
        gmail,
        codex,
        gmail_account="agent@example.com",
        default_project="bridge",
        projects={"bridge": "C:/bridge", "project-a": "C:/project-a"},
    )

    assert service.scan_once()["queued"] == 1
    asyncio.run(service.drain())

    assert codex.started == ["Nouvelle demande"]
    assert codex.working_directories == ["C:/project-a"]
    route = service.db.route_for_gmail("g1")
    assert route["codex_thread_id"] == "created-1"
    assert route["project_key"] == "project-a"
    assert gmail.sent[0]["thread_id"] == "g1"
    assert gmail.sent[0]["in_reply_to"] == "<m1@gmail>"


def test_new_email_to_plain_address_uses_default_project(tmp_path):
    message = incoming("m1", "g1", recipient="agent@example.com")
    gmail, codex = FakeGmail([message]), FakeCodex()
    service = make_service(
        tmp_path,
        gmail,
        codex,
        gmail_account="agent@example.com",
        default_project="bridge",
        projects={"bridge": "C:/bridge"},
    )

    service.scan_once()
    asyncio.run(service.drain())

    assert codex.working_directories == ["C:/bridge"]


def test_unknown_project_alias_is_quarantined(tmp_path):
    message = incoming(
        "m1", "g1", recipient="agent+unknown@example.com"
    )
    service = make_service(
        tmp_path,
        FakeGmail([message]),
        FakeCodex(),
        gmail_account="agent@example.com",
        default_project="bridge",
        projects={"bridge": "C:/bridge"},
    )

    assert service.scan_once()["quarantined"] == 1


def test_routing_code_recovers_reply_moved_to_new_gmail_thread(tmp_path):
    gmail = FakeGmail([incoming("m1", "new-gmail-thread", "Reply\nRouting: CX-111111")])
    codex = FakeCodex()
    service = make_service(tmp_path, gmail, codex)
    service.db.add_route("original-gmail-thread", "c1", "CX-111111", "Report")
    assert service.scan_once()["queued"] == 1
    asyncio.run(service.drain())
    assert codex.calls == [("c1", "Reply\nRouting: CX-111111")]
    assert gmail.sent[0]["thread_id"] == "original-gmail-thread"


def test_routing_code_requeues_previously_quarantined_message(tmp_path):
    message = incoming("m1", "new-gmail-thread", "Reply\nRouting: CX-111111")
    gmail = FakeGmail([message])
    service = make_service(tmp_path, gmail)
    assert service.scan_once()["quarantined"] == 1
    service.db.add_route("original-gmail-thread", "c1", "CX-111111", "Report")
    assert service.scan_once()["queued"] == 1
    with service.db.connection() as c:
        assert c.execute("SELECT count(*) FROM quarantine").fetchone()[0] == 0


def test_fifo_within_thread_and_parallel_across_threads(tmp_path):
    codex = FakeCodex(delay=0.02)
    gmail = FakeGmail(
        [incoming("a1", "g1", "one"), incoming("a2", "g1", "two"), incoming("b1", "g2", "three")]
    )
    service = make_service(tmp_path, gmail, codex)
    service.db.add_route("g1", "c1", "CX-111111", "R1")
    service.db.add_route("g2", "c2", "CX-222222", "R2")
    service.scan_once()
    asyncio.run(service.drain())
    c1 = [body for tid, body in codex.calls if tid == "c1"]
    assert c1 == ["one", "two"]
    assert codex.max_active == 2
    assert len(gmail.sent) == 3


def test_attachments_only_explicit_and_missing_is_reported(tmp_path):
    present = tmp_path / "result.txt"
    present.write_text("ok")
    missing = tmp_path / "missing.pdf"
    gmail = FakeGmail()
    service = make_service(tmp_path, gmail)
    service.publish(OutgoingReport("c1", "Report", "body", (present, missing)))
    sent = gmail.sent[0]
    assert sent["attachments"] == (present,)
    assert str(missing) in sent["body"]


def test_uncertain_send_is_not_retried(tmp_path):
    gmail = FakeGmail()
    gmail.fail_send = True
    service = make_service(tmp_path, gmail)
    with pytest.raises(TimeoutError):
        service.publish(OutgoingReport("c1", "Report", "body"), "same")
    with pytest.raises(Exception):
        service.publish(OutgoingReport("c1", "Report", "body"), "same")
    with service.db.connection() as c:
        assert c.execute("SELECT state FROM outbox").fetchone()[0] == "uncertain"


def test_restart_requeues_interrupted_job(tmp_path):
    service = make_service(tmp_path)
    service.db.add_route("g1", "c1", "CX-111111", "R")
    service.db.enqueue("m1", "g1", "body")
    assert service.db.claim_next("c1")["gmail_message_id"] == "m1"
    service.db.reset_interrupted()
    assert service.db.claim_next("c1")["gmail_message_id"] == "m1"


def test_existing_database_is_migrated_for_project_routing(tmp_path):
    path = tmp_path / "db.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE routes (
              gmail_thread_id TEXT PRIMARY KEY, codex_thread_id TEXT NOT NULL UNIQUE,
              routing_code TEXT NOT NULL UNIQUE, subject TEXT NOT NULL,
              last_message_id_header TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE inbox (
              gmail_message_id TEXT PRIMARY KEY, gmail_thread_id TEXT NOT NULL,
              codex_thread_id TEXT, body TEXT NOT NULL, state TEXT NOT NULL,
              attempts INTEGER NOT NULL DEFAULT 0, error TEXT,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )

    database = Database(path)
    database.add_route("g1", "c1", "CX-111111", "Sujet", project_key="bridge")

    assert database.route_for_gmail("g1")["project_key"] == "bridge"
