from __future__ import annotations

import html
import re


_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")
_CODE_RE = re.compile(r"`([^`]+)`")
_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")
_ITALIC_RE = re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)")


def _inline(value: str) -> str:
    value = html.escape(value, quote=False)
    value = _LINK_RE.sub(r'<a href="\2">\1</a>', value)
    value = _CODE_RE.sub(r"<code>\1</code>", value)
    value = _BOLD_RE.sub(r"<strong>\1</strong>", value)
    return _ITALIC_RE.sub(r"<em>\1</em>", value)


def markdown_to_html(markdown: str) -> str:
    """Render Codex Markdown as a conservative multipart-email HTML body."""
    lines = markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    blocks: list[str] = []
    paragraph: list[str] = []
    index = 0

    def flush_paragraph() -> None:
        if paragraph:
            blocks.append("<p>" + "<br>\n".join(_inline(line) for line in paragraph) + "</p>")
            paragraph.clear()

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            index += 1
            continue
        if stripped.startswith("```"):
            flush_paragraph()
            language = stripped[3:].strip()
            code: list[str] = []
            index += 1
            while index < len(lines) and not lines[index].strip().startswith("```"):
                code.append(lines[index])
                index += 1
            if index < len(lines):
                index += 1
            class_attr = f' class="language-{html.escape(language)}"' if language else ""
            blocks.append(f"<pre><code{class_attr}>{html.escape(chr(10).join(code))}</code></pre>")
            continue
        heading = re.match(r"^(#{1,6})\s+(.+?)\s*#*$", stripped)
        if heading:
            flush_paragraph()
            level = len(heading.group(1))
            blocks.append(f"<h{level}>{_inline(heading.group(2))}</h{level}>")
            index += 1
            continue
        if re.fullmatch(r"(?:\*{3,}|-{3,}|_{3,})", stripped):
            flush_paragraph()
            blocks.append("<hr>")
            index += 1
            continue
        if re.match(r"^\s*[-*+]\s+", line):
            flush_paragraph()
            items: list[str] = []
            while index < len(lines):
                match = re.match(r"^\s*[-*+]\s+(.+)$", lines[index])
                if not match:
                    break
                items.append(f"<li>{_inline(match.group(1))}</li>")
                index += 1
            blocks.append("<ul>" + "".join(items) + "</ul>")
            continue
        if re.match(r"^\s*\d+[.)]\s+", line):
            flush_paragraph()
            items = []
            while index < len(lines):
                match = re.match(r"^\s*\d+[.)]\s+(.+)$", lines[index])
                if not match:
                    break
                items.append(f"<li>{_inline(match.group(1))}</li>")
                index += 1
            blocks.append("<ol>" + "".join(items) + "</ol>")
            continue
        if stripped.startswith(">"):
            flush_paragraph()
            blocks.append(f"<blockquote>{_inline(stripped[1:].lstrip())}</blockquote>")
            index += 1
            continue
        paragraph.append(stripped)
        index += 1

    flush_paragraph()
    content = "\n".join(blocks)
    return (
        "<!doctype html><html><body style=\"margin:0;padding:24px;"
        "font-family:Arial,sans-serif;color:#1f2937;line-height:1.55;\">"
        f"{content}</body></html>"
    )
