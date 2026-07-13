from pathlib import Path

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


def test_subprocess_creation_flags_hide_windows_console(monkeypatch):
    monkeypatch.setattr(codex.os, "name", "nt")
    monkeypatch.setattr(codex.subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    assert codex.subprocess_creation_flags() == 0x08000000


def test_subprocess_creation_flags_are_empty_off_windows(monkeypatch):
    monkeypatch.setattr(codex.os, "name", "posix")
    assert codex.subprocess_creation_flags() == 0
