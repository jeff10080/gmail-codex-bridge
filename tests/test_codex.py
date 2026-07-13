import asyncio
import json
from pathlib import Path

import pytest

from gmail_codex_bridge import codex


def test_find_node_prefers_path(monkeypatch):
    monkeypatch.setattr(codex.shutil, "which", lambda name: "C:/node/node.exe")
    assert codex.find_node_executable() == "C:/node/node.exe"


def test_find_node_uses_codex_runtime(monkeypatch, tmp_path):
    monkeypatch.setattr(codex.shutil, "which", lambda name: None)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    node = (
        tmp_path
        / ".cache"
        / "codex-runtimes"
        / "codex-primary-runtime"
        / "dependencies"
        / "node"
        / "bin"
        / "node.exe"
    )
    node.parent.mkdir(parents=True)
    node.touch()
    assert codex.find_node_executable() == str(node)


def test_find_codex_prefers_path(monkeypatch):
    monkeypatch.setattr(codex.shutil, "which", lambda name: "C:/codex/codex.exe")
    assert codex.find_codex_executable() == "C:/codex/codex.exe"


def test_find_codex_uses_desktop_install(monkeypatch, tmp_path):
    monkeypatch.setattr(codex.shutil, "which", lambda name: None)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    executable = tmp_path / "Programs" / "OpenAI" / "Codex" / "bin" / "codex.exe"
    executable.parent.mkdir(parents=True)
    executable.touch()
    assert codex.find_codex_executable() == str(executable)


def test_node_client_passes_app_server_executable_and_thread_title(monkeypatch, tmp_path):
    captured = {}

    class FakeProcess:
        returncode = 0

        async def communicate(self, payload):
            captured.update(json.loads(payload.decode()))
            return b'{"ok":true,"finalResponse":"done","threadId":"thread-1"}\n', b""

    async def fake_create_subprocess_exec(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return FakeProcess()

    monkeypatch.setattr(codex, "find_node_executable", lambda: "C:/node/node.exe")
    monkeypatch.setattr(codex, "find_codex_executable", lambda: "C:/codex/codex.exe")
    monkeypatch.setattr(codex.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    client = codex.NodeCodexClient(tmp_path / "runner.mjs")
    result = asyncio.run(client.start("prompt", "C:/project", "Sujet Gmail"))

    assert result.thread_id == "thread-1"
    assert captured["codexExecutable"] == "C:/codex/codex.exe"
    assert captured["workingDirectory"] == "C:/project"
    assert captured["title"] == "Sujet Gmail"
    assert captured["threadId"] is None


def test_node_client_preserves_runner_error_from_stdout(monkeypatch, tmp_path):
    class FakeProcess:
        returncode = 1

        async def communicate(self, payload):
            return b'{"ok":false,"error":"app-server detail"}\n', b""

    async def fake_create_subprocess_exec(*args, **kwargs):
        return FakeProcess()

    monkeypatch.setattr(codex, "find_node_executable", lambda: "C:/node/node.exe")
    monkeypatch.setattr(codex, "find_codex_executable", lambda: "C:/codex/codex.exe")
    monkeypatch.setattr(codex.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    client = codex.NodeCodexClient(tmp_path / "runner.mjs")
    with pytest.raises(RuntimeError, match="app-server detail"):
        asyncio.run(client.start("prompt"))


def test_subprocess_creation_flags_hide_windows_console(monkeypatch):
    monkeypatch.setattr(codex.os, "name", "nt")
    monkeypatch.setattr(codex.subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    assert codex.subprocess_creation_flags() == 0x08000000


def test_subprocess_creation_flags_are_empty_off_windows(monkeypatch):
    monkeypatch.setattr(codex.os, "name", "posix")
    assert codex.subprocess_creation_flags() == 0
