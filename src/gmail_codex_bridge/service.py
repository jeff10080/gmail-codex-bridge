from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import secrets

from .codex import CodexClient
from .database import Database
from .gmail import GmailClient
from .models import OutgoingReport

log = logging.getLogger(__name__)
ROUTING_CODE_RE = re.compile(r"\bCX-[A-F0-9]{6}\b", re.IGNORECASE)


class BridgeService:
    def __init__(
        self,
        db: Database,
        gmail: GmailClient,
        codex: CodexClient,
        *,
        allowed_sender: str,
        recipient: str,
        gmail_query: str,
        max_parallel_threads: int = 4,
        gmail_account: str = "",
        default_project: str | None = None,
        projects: dict[str, str] | None = None,
    ):
        self.db, self.gmail, self.codex = db, gmail, codex
        self.allowed_sender = allowed_sender.casefold()
        self.recipient, self.gmail_query = recipient, gmail_query
        self.gmail_account = gmail_account.casefold()
        self.default_project = default_project.casefold() if default_project else None
        self.projects = {key.casefold(): value for key, value in (projects or {}).items()}
        self.limit = asyncio.Semaphore(max_parallel_threads)
        self._thread_locks: dict[str, asyncio.Lock] = {}

    def _project_for_recipient(self, recipient: str) -> str | None:
        if not self.gmail_account:
            return None
        target = recipient.casefold() or self.gmail_account
        target_local, separator, target_domain = target.partition("@")
        account_local, _, account_domain = self.gmail_account.partition("@")
        if not separator or target_domain != account_domain:
            return None
        if target_local == account_local:
            return self.default_project if self.default_project in self.projects else None
        prefix = f"{account_local}+"
        if not target_local.startswith(prefix):
            return None
        project_key = target_local.removeprefix(prefix)
        return project_key if project_key in self.projects else None

    def scan_once(self) -> dict[str, int]:
        counts = {"queued": 0, "duplicate": 0, "quarantined": 0, "rejected": 0}
        for message_id in self.gmail.list_candidate_ids(self.gmail_query):
            message = self.gmail.get_message(message_id)
            if message.sender.casefold() != self.allowed_sender:
                counts["rejected"] += 1
                log.warning("gmail_rejected id=%s sender_mismatch=true", message.id)
                continue
            routing_match = ROUTING_CODE_RE.search(f"{message.subject}\n{message.body}")
            routing_code = routing_match.group(0).upper() if routing_match else None
            project_key = self._project_for_recipient(message.recipient)
            state = self.db.enqueue(
                message.id,
                message.thread_id,
                message.body,
                routing_code,
                project_key=project_key,
                subject=message.subject,
                message_id_header=message.message_id_header,
            )
            counts[state] += 1
            log.info(
                "gmail_ingested id=%s thread=%s state=%s", message.id, message.thread_id, state
            )
        return counts

    async def drain(self) -> None:
        tasks = [asyncio.create_task(self._drain_thread(t)) for t in self.db.ready_threads()]
        if tasks:
            await asyncio.gather(*tasks)

    async def _drain_thread(self, work_id: str) -> None:
        lock = self._thread_locks.setdefault(work_id, asyncio.Lock())
        async with self.limit, lock:
            thread_id = work_id
            while row := self.db.claim_next(thread_id):
                try:
                    if row["codex_thread_id"]:
                        route = self.db.route_for_codex(row["codex_thread_id"])
                        project_key = route["project_key"] if route else row["project_key"]
                        working_directory = self.projects.get(project_key or "")
                        result = await self.codex.resume(
                            row["codex_thread_id"], row["body"], working_directory
                        )
                        active_thread_id = row["codex_thread_id"]
                    else:
                        project_key = row["project_key"]
                        working_directory = self.projects.get(project_key or "")
                        if not working_directory:
                            raise RuntimeError(f"Projet Codex inconnu: {project_key!r}")
                        result = await self.codex.start(row["body"], working_directory)
                        if not result.thread_id:
                            raise RuntimeError("Le SDK Codex n'a pas retourne de thread ID")
                        active_thread_id = result.thread_id
                        code = f"CX-{secrets.token_hex(3).upper()}"
                        subject = row["subject"] or f"Conversation Codex [{code}]"
                        self.db.add_route(
                            row["gmail_thread_id"],
                            active_thread_id,
                            code,
                            subject,
                            row["message_id_header"],
                            project_key,
                        )
                        self.db.bind_gmail_thread(row["gmail_thread_id"], active_thread_id)
                        thread_id = active_thread_id
                    await asyncio.to_thread(
                        self.publish,
                        OutgoingReport(
                            active_thread_id, "", result.final_response, result.attachments
                        ),
                        f"reply:{row['gmail_message_id']}",
                    )
                    self.db.finish(row["gmail_message_id"])
                except Exception as exc:
                    self.db.finish(row["gmail_message_id"], str(exc)[:1000])
                    log.exception(
                        "job_failed gmail_id=%s codex_thread=%s", row["gmail_message_id"], thread_id
                    )
                    break

    def publish(self, report: OutgoingReport, dedupe_key: str | None = None):
        route = self.db.route_for_codex(report.codex_thread_id)
        code = report.routing_code or (
            route["routing_code"] if route else f"CX-{secrets.token_hex(3).upper()}"
        )
        subject = route["subject"] if route else (report.subject or f"Rapport Codex [{code}]")
        body = f"{report.body.rstrip()}\n\n---\nRouting: {code}\n"
        existing = tuple(p for p in report.attachments if p.is_file())
        missing = [str(p) for p in report.attachments if not p.is_file()]
        if missing:
            body += (
                "\nPiece(s) jointe(s) introuvable(s):\n"
                + "\n".join(f"- {p}" for p in missing)
                + "\n"
            )
        key = dedupe_key or hashlib.sha256((report.codex_thread_id + body).encode()).hexdigest()
        with self.db.connection() as c:
            try:
                c.execute(
                    "INSERT INTO outbox(dedupe_key,codex_thread_id,state) VALUES(?,?,'sending')",
                    (key, report.codex_thread_id),
                )
            except Exception:
                row = c.execute("SELECT * FROM outbox WHERE dedupe_key=?", (key,)).fetchone()
                if row and row["state"] == "sent":
                    return row
                raise
        try:
            sent = self.gmail.send(
                recipient=self.recipient,
                subject=subject,
                body=body,
                attachments=existing,
                thread_id=route["gmail_thread_id"] if route else None,
                in_reply_to=route["last_message_id_header"] if route else None,
            )
        except Exception as exc:
            with self.db.connection() as c:
                c.execute(
                    "UPDATE outbox SET state='uncertain',error=? WHERE dedupe_key=?",
                    (str(exc)[:1000], key),
                )
            raise
        self.db.add_route(
            sent.thread_id, report.codex_thread_id, code, subject, sent.message_id_header
        )
        with self.db.connection() as c:
            c.execute(
                "UPDATE outbox SET state='sent',gmail_message_id=?,gmail_thread_id=? WHERE dedupe_key=?",
                (sent.message_id, sent.thread_id, key),
            )
        return sent

    async def run_forever(self, interval: int) -> None:
        self.db.reset_interrupted()
        while True:
            try:
                self.scan_once()
                await self.drain()
            except Exception:
                log.exception("poll_cycle_failed")
            await asyncio.sleep(interval)
