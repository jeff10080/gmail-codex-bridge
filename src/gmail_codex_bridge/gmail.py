from __future__ import annotations

import base64
import email
import json
import logging
import mimetypes
import re
from email.message import EmailMessage
from email.utils import make_msgid, parseaddr
from pathlib import Path
from typing import Protocol

from .models import IncomingMessage, SendResult
from .secrets import protect, unprotect

log = logging.getLogger(__name__)
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


class GmailClient(Protocol):
    def list_candidate_ids(self, query: str) -> list[str]: ...
    def get_message(self, message_id: str) -> IncomingMessage: ...
    def send(
        self,
        *,
        recipient: str,
        subject: str,
        body: str,
        html_body: str | None = None,
        attachments: tuple[Path, ...] = (),
        thread_id: str | None = None,
        in_reply_to: str | None = None,
    ) -> SendResult: ...


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


_GMAIL_QUOTE_END_RE = re.compile(r"(?:a écrit\s*:|wrote\s*:)", re.IGNORECASE)
_OUTLOOK_SEPARATOR_RE = re.compile(
    r"^\s*(?:-{2,}\s*(?:Original Message|Message d'origine)\s*-{2,}|_{5,})\s*$",
    re.IGNORECASE,
)


def extract_latest_reply(body: str) -> str:
    """Return only the text written above the quoted email history."""
    normalized = body.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    cut = len(lines)
    for index, line in enumerate(lines):
        if _OUTLOOK_SEPARATOR_RE.match(line):
            cut = index
            break
        if re.match(r"^\s*(?:Le|On)\b", line, re.IGNORECASE):
            header = " ".join(lines[index : index + 4])
            if _GMAIL_QUOTE_END_RE.search(header):
                cut = index
                break
        if line.lstrip().startswith(">"):
            cut = index
            break
    reply = "\n".join(lines[:cut]).strip()
    return reply or normalized.strip()


class GoogleGmailClient:
    def __init__(self, service, attachment_dir: Path, sender: str | None = None):
        self.service = service
        self.attachment_dir = attachment_dir
        self.sender = sender

    @classmethod
    def from_data_dir(
        cls,
        data_dir: Path,
        interactive: bool = False,
        expected_account: str | None = None,
        reauthorize: bool = False,
    ):
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build

        token_path = data_dir / "token.dpapi"
        credentials_path = data_dir / "credentials.json"
        if reauthorize:
            token_path.unlink(missing_ok=True)
        creds = None
        if token_path.exists():
            token_info = json.loads(unprotect(token_path.read_bytes()).decode("utf-8"))
            creds = Credentials.from_authorized_user_info(token_info, SCOPES)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        if not creds or not creds.valid:
            if not interactive:
                raise RuntimeError("OAuth Gmail requis: executez `gmail-codex-bridge auth`")
            if not credentials_path.exists():
                raise FileNotFoundError(f"Identifiants OAuth absents: {credentials_path}")
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
            creds = flow.run_local_server(port=0)
        service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        authenticated_account = service.users().getProfile(userId="me").execute()["emailAddress"]
        if expected_account and authenticated_account.casefold() != expected_account.casefold():
            raise RuntimeError(
                f"Compte Gmail OAuth incorrect: {authenticated_account}; attendu: {expected_account}"
            )
        token_path.write_bytes(protect(creds.to_json().encode("utf-8")))
        return cls(service, data_dir / "attachments", authenticated_account)

    def list_candidate_ids(self, query: str) -> list[str]:
        result: list[str] = []
        token = None
        while True:
            page = (
                self.service.users()
                .messages()
                .list(userId="me", q=query, maxResults=500, pageToken=token)
                .execute()
            )
            result.extend(item["id"] for item in page.get("messages", []))
            token = page.get("nextPageToken")
            if not token:
                return result

    def get_message(self, message_id: str) -> IncomingMessage:
        resource = (
            self.service.users().messages().get(userId="me", id=message_id, format="raw").execute()
        )
        parsed = email.message_from_bytes(_unb64(resource["raw"]))
        sender = parseaddr(parsed.get("From", ""))[1].casefold()
        body = ""
        paths: list[Path] = []
        for part in parsed.walk():
            disposition = part.get_content_disposition()
            if part.get_content_type() == "text/plain" and disposition != "attachment" and not body:
                decoded = part.get_payload(decode=True).decode(
                    part.get_content_charset() or "utf-8", errors="replace"
                )
                body = extract_latest_reply(decoded)
            if disposition == "attachment" and part.get_filename():
                safe_name = Path(part.get_filename()).name
                target_dir = self.attachment_dir / message_id
                target_dir.mkdir(parents=True, exist_ok=True)
                target = target_dir / safe_name
                target.write_bytes(part.get_payload(decode=True) or b"")
                paths.append(target)
        return IncomingMessage(
            message_id,
            resource["threadId"],
            sender,
            parsed.get("Subject", ""),
            body,
            parsed.get("Message-ID"),
            tuple(paths),
            parseaddr(parsed.get("Delivered-To") or parsed.get("To", ""))[1].casefold(),
        )

    def send(
        self,
        *,
        recipient: str,
        subject: str,
        body: str,
        html_body: str | None = None,
        attachments: tuple[Path, ...] = (),
        thread_id: str | None = None,
        in_reply_to: str | None = None,
    ) -> SendResult:
        msg = EmailMessage()
        msg["To"] = recipient
        msg["From"] = self.sender or recipient
        msg["Subject"] = subject
        msg["Message-ID"] = make_msgid(domain=(self.sender or recipient).partition("@")[2] or None)
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
            msg["References"] = in_reply_to
        msg.set_content(body)
        if html_body:
            msg.add_alternative(html_body, subtype="html")
        for path in attachments:
            mime, _ = mimetypes.guess_type(path.name)
            major, minor = (mime or "application/octet-stream").split("/", 1)
            msg.add_attachment(path.read_bytes(), maintype=major, subtype=minor, filename=path.name)
        request = {"raw": _b64(msg.as_bytes())}
        if thread_id:
            request["threadId"] = thread_id
        result = self.service.users().messages().send(userId="me", body=request).execute()
        return SendResult(result["id"], result["threadId"], msg.get("Message-ID"))
