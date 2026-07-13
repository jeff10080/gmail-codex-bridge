from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Protocol

from .models import CodexResult


class CodexClient(Protocol):
    async def start(
        self,
        prompt: str,
        working_directory: str | None = None,
        title: str | None = None,
    ) -> CodexResult: ...
    async def resume(
        self, thread_id: str, prompt: str, working_directory: str | None = None
    ) -> CodexResult: ...


def find_node_executable() -> str:
    installed = shutil.which("node")
    if installed:
        return installed
    bundled = (
        Path.home()
        / ".cache"
        / "codex-runtimes"
        / "codex-primary-runtime"
        / "dependencies"
        / "node"
        / "bin"
        / "node.exe"
    )
    if bundled.is_file():
        return str(bundled)
    raise RuntimeError(
        "Node.js introuvable. Installez Node.js 18+ ou rendez le runtime Codex disponible."
    )


def find_codex_executable() -> str:
    installed = shutil.which("codex")
    if installed:
        return installed
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        desktop = Path(local_app_data) / "Programs" / "OpenAI" / "Codex" / "bin" / "codex.exe"
        if desktop.is_file():
            return str(desktop)
    raise RuntimeError(
        "Codex CLI introuvable. Installez Codex Desktop ou rendez codex disponible dans PATH."
    )


def subprocess_creation_flags() -> int:
    """Prevent Node and the Codex CLI from opening a console window on Windows."""
    if os.name == "nt":
        return subprocess.CREATE_NO_WINDOW
    return 0


class NodeCodexClient:
    def __init__(self, runner: Path, working_directory: str | None = None):
        self.runner = runner
        self.working_directory = working_directory
        self.node_executable = find_node_executable()
        self.codex_executable = find_codex_executable()

    async def _run(
        self,
        prompt: str,
        *,
        thread_id: str | None = None,
        working_directory: str | None = None,
        title: str | None = None,
    ) -> CodexResult:
        proc = await asyncio.create_subprocess_exec(
            self.node_executable,
            str(self.runner),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            creationflags=subprocess_creation_flags(),
        )
        payload = (
            json.dumps(
                {
                    "threadId": thread_id,
                    "prompt": prompt,
                    "workingDirectory": working_directory or self.working_directory,
                    "title": title,
                    "codexExecutable": self.codex_executable,
                }
            )
            + "\n"
        )
        timeout_seconds = float(os.environ.get("CODEX_RUN_TIMEOUT_SECONDS", "21600"))
        try:
            async with asyncio.timeout(timeout_seconds):
                stdout, stderr = await proc.communicate(payload.encode())
        except BaseException:
            if proc.returncode is None:
                proc.kill()
                await proc.wait()
            raise
        decoded_stdout = stdout.decode(errors="replace").strip()
        decoded_stderr = stderr.decode(errors="replace").strip()
        try:
            data = json.loads(decoded_stdout.splitlines()[-1])
        except (IndexError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                f"Reponse invalide du runner Codex (exit={proc.returncode}): "
                f"{decoded_stdout[-1000:] or decoded_stderr[-1000:]}"
            ) from exc
        if not data.get("ok"):
            detail = data.get("error", "Codex runner failed")
            if decoded_stderr:
                detail = f"{detail}\napp-server stderr: {decoded_stderr[-1000:]}"
            raise RuntimeError(detail)
        if proc.returncode:
            raise RuntimeError(
                f"Codex runner exit={proc.returncode}: {decoded_stderr[-1000:]}"
            )
        return CodexResult(data["finalResponse"], thread_id=data.get("threadId"))

    async def start(
        self,
        prompt: str,
        working_directory: str | None = None,
        title: str | None = None,
    ) -> CodexResult:
        return await self._run(prompt, working_directory=working_directory, title=title)

    async def resume(
        self, thread_id: str, prompt: str, working_directory: str | None = None
    ) -> CodexResult:
        return await self._run(
            prompt, thread_id=thread_id, working_directory=working_directory
        )
