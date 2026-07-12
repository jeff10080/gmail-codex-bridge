from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

from .codex import NodeCodexClient
from .config import ensure_private_dirs, load_settings
from .database import Database
from .gmail import GoogleGmailClient
from .models import OutgoingReport
from .service import BridgeService


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="gmail-codex-bridge")
    p.add_argument("--config", type=Path)
    sub = p.add_subparsers(dest="command", required=True)
    auth = sub.add_parser("auth")
    auth.add_argument("--reauthorize", action="store_true")
    sub.add_parser("run")
    pub = sub.add_parser("publish")
    pub.add_argument("--codex-thread-id", required=True)
    pub.add_argument("--subject", default="Rapport Codex")
    body = pub.add_mutually_exclusive_group(required=True)
    body.add_argument("--body")
    body.add_argument("--body-file", type=Path)
    pub.add_argument("--attachment", type=Path, action="append", default=[])
    return p


def build_service(settings, interactive: bool = False) -> BridgeService:
    root = Path(__file__).resolve().parents[2]
    return BridgeService(
        Database(settings.database_path),
        GoogleGmailClient.from_data_dir(
            settings.data_dir,
            interactive=interactive,
            expected_account=settings.gmail_account,
        ),
        NodeCodexClient(root / "scripts" / "codex-runner.mjs", settings.codex_working_directory),
        allowed_sender=settings.allowed_sender,
        recipient=settings.recipient,
        gmail_query=settings.gmail_query,
        max_parallel_threads=settings.max_parallel_threads,
    )


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    settings = load_settings(args.config)
    ensure_private_dirs(settings)
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper()),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[logging.FileHandler(settings.data_dir / "logs" / "bridge.log", encoding="utf-8")],
    )
    if args.command == "auth":
        GoogleGmailClient.from_data_dir(
            settings.data_dir,
            interactive=True,
            expected_account=settings.gmail_account,
            reauthorize=args.reauthorize,
        )
        print("OAuth Gmail valide.")
        return 0
    service = build_service(settings)
    if args.command == "publish":
        text = args.body if args.body is not None else args.body_file.read_text("utf-8")
        service.publish(
            OutgoingReport(args.codex_thread_id, args.subject, text, tuple(args.attachment))
        )
        return 0
    asyncio.run(service.run_forever(settings.poll_interval_seconds))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
