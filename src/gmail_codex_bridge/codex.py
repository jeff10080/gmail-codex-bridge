from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path
from typing import Protocol

from .models import CodexResult


class CodexClient(Protocol):
    async def start(self, prompt: str, working_directory: str | None = None) -> CodexResult: ...
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


class NodeCodexClient:
    def __init__(self, runner: Path, working_directory: str | None = None):
        self.runner = runner
        self.working_directory = working_directory
        self.node_executable = find_node_executable()

    async def _run(
        self,
        prompt: str,
        *,
        thread_id: str | None = None,
        working_directory: str | None = None,
    ) -> CodexResult:
        proc = await asyncio.create_subprocess_exec(
            self.node_executable,
            str(self.runner),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        payload = (
            json.dumps(
                {
                    "threadId": thread_id,
                    "prompt": prompt,
                    "workingDirectory": working_directory or self.working_directory,
                }
            )
            + "\n"
        )
        stdout, stderr = await proc.communicate(payload.encode())
        if proc.returncode:
            raise RuntimeError(
                f"Codex runner exit={proc.returncode}: {stderr.decode(errors='replace')[:1000]}"
            )
        line = stdout.decode().strip().splitlines()[-1]
        data = json.loads(line)
        if not data.get("ok"):
            raise RuntimeError(data.get("error", "Codex runner failed"))
        return CodexResult(data["finalResponse"], thread_id=data.get("threadId"))

    async def start(self, prompt: str, working_directory: str | None = None) -> CodexResult:
        return await self._run(prompt, working_directory=working_directory)

    async def resume(
        self, thread_id: str, prompt: str, working_directory: str | None = None
    ) -> CodexResult:
        return await self._run(
            prompt, thread_id=thread_id, working_directory=working_directory
        )
