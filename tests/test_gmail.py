import email
from email.message import EmailMessage

from gmail_codex_bridge.gmail import GoogleGmailClient, _b64, _unb64, extract_latest_reply


class Request:
    def __init__(self, value):
        self.value = value

    def execute(self):
        return self.value


class Messages:
    def __init__(self, raw):
        self.raw = raw
        self.last_send = None

    def get(self, **kwargs):
        return Request({"id": kwargs["id"], "threadId": "g1", "raw": self.raw})

    def send(self, **kwargs):
        self.last_send = kwargs["body"]
        return Request({"id": "s1", "threadId": kwargs["body"].get("threadId", "new")})


class Service:
    def __init__(self, messages):
        self._messages = messages

    def users(self):
        return self

    def messages(self):
        return self._messages


def test_mime_parse_and_threaded_send(tmp_path):
    msg = EmailMessage()
    msg["From"] = "User <user@example.com>"
    msg["To"] = "bridge@example.com"
    msg["Subject"] = "Re: Report"
    msg["Message-ID"] = "<m1@gmail>"
    msg.set_content("instruction")
    msg.add_attachment(
        b"data", maintype="application", subtype="octet-stream", filename="result.bin"
    )
    messages = Messages(_b64(msg.as_bytes()))
    client = GoogleGmailClient(Service(messages), tmp_path, "bridge@example.com")
    incoming = client.get_message("m1")
    assert incoming.sender == "user@example.com"
    assert incoming.body.strip() == "instruction"
    assert incoming.recipient == "bridge@example.com"
    assert incoming.attachments[0].read_bytes() == b"data"
    client.send(
        recipient="user@example.com",
        subject="Report",
        body="answer",
        html_body="<html><body><h1>answer</h1></body></html>",
        attachments=incoming.attachments,
        thread_id="g1",
        in_reply_to="<m1@gmail>",
    )
    assert messages.last_send["threadId"] == "g1"
    sent = email.message_from_bytes(_unb64(messages.last_send["raw"]))
    html_part = next(part for part in sent.walk() if part.get_content_type() == "text/html")
    assert html_part.get_payload(decode=True).decode().strip() == (
        "<html><body><h1>answer</h1></body></html>"
    )
    attachment = next(part for part in sent.walk() if part.get_content_disposition() == "attachment")
    assert attachment.get_filename() == "result.bin"
    assert attachment.get_payload(decode=True) == b"data"


def test_extract_latest_reply_from_french_gmail_quote():
    body = """Une interface homme/machine

Le dim. 12 juil. 2026 à 22:33, Stanislas <bridge@example.com> a
écrit :

> Quel projet aimerais-tu construire ?
> Routing: CX-123456
"""
    assert extract_latest_reply(body) == "Une interface homme/machine"


def test_extract_latest_reply_from_english_gmail_quote():
    body = """A wearable interface.

On Sun, Jul 12, 2026 at 10:33 PM Codex <bridge@example.com> wrote:
> What would you build?
"""
    assert extract_latest_reply(body) == "A wearable interface."


def test_extract_latest_reply_preserves_multiline_message():
    body = "First paragraph.\n\nSecond paragraph."
    assert extract_latest_reply(body) == body
