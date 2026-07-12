from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Protocol

from .models import CodexResult


class CodexClient(Protocol):
    async def resume(self, thread_id: str, prompt: str) -> CodexResult: ...


class NodeCodexClient:
    def __init__(self, runner: Path, working_directory: str | None = None):
        self.runner = runner
        self.working_directory = working_directory

    async def resume(self, thread_id: str, prompt: str) -> CodexResult:
        proc = await asyncio.create_subprocess_exec(
            "node",
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
                    "workingDirectory": self.working_directory,
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
        return CodexResult(data["finalResponse"])
