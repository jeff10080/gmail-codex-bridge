from email.message import EmailMessage

from gmail_codex_bridge.gmail import GoogleGmailClient, _b64


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
    msg["From"] = "Stan <user@example.com>"
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
    assert incoming.attachments[0].read_bytes() == b"data"
    client.send(
        recipient="user@example.com",
        subject="Report",
        body="answer",
        thread_id="g1",
        in_reply_to="<m1@gmail>",
    )
    assert messages.last_send["threadId"] == "g1"
