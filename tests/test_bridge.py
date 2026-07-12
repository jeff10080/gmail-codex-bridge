from __future__ import annotations

import asyncio

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

    async def resume(self, thread_id, prompt):
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        await asyncio.sleep(self.delay)
        self.calls.append((thread_id, prompt))
        self.active -= 1
        return CodexResult(f"answer:{prompt}")


def make_service(tmp_path, gmail=None, codex=None):
    return BridgeService(
        Database(tmp_path / "db.sqlite3"),
        gmail or FakeGmail(),
        codex or FakeCodex(),
        allowed_sender="user@example.com",
        recipient="user@example.com",
        gmail_query="from:user@example.com",
        max_parallel_threads=4,
    )


def incoming(mid, thread, body="hello", sender="user@example.com"):
    return IncomingMessage(mid, thread, sender, "Re: report", body, f"<{mid}@gmail>")


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
