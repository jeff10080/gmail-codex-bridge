from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class IncomingMessage:
    id: str
    thread_id: str
    sender: str
    subject: str
    body: str
    message_id_header: str | None = None
    attachments: tuple[Path, ...] = ()
    recipient: str = ""


@dataclass(frozen=True)
class OutgoingReport:
    codex_thread_id: str
    subject: str
    body: str
    attachments: tuple[Path, ...] = ()
    routing_code: str | None = None


@dataclass(frozen=True)
class SendResult:
    message_id: str
    thread_id: str
    message_id_header: str | None = None


@dataclass(frozen=True)
class CodexResult:
    final_response: str
    attachments: tuple[Path, ...] = field(default_factory=tuple)
    thread_id: str | None = None
