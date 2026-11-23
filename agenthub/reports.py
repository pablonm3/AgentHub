"""Reports of a task and files of a harness run, served to Pablo's browser (AC32, gate links).

`.md` is rendered to an HTML page, `.ipynb` is rendered read-only with a download link, anything
else is served as it is. Paths are confined to their folder.
"""

from __future__ import annotations

import html
import mimetypes
from pathlib import Path
from typing import TYPE_CHECKING

import markdown as md

if TYPE_CHECKING:
    from .hub import Hub

PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{title}</title>
<style>body{{font-family:Inter,system-ui,sans-serif;max-width:920px;margin:32px auto;padding:0 20px;color:#161A22;line-height:1.55}}
pre,code{{font-family:'JetBrains Mono',monospace;background:#F3F4F7}}pre{{padding:12px;overflow:auto}}
table{{border-collapse:collapse}}td,th{{border:1px solid #D9DDE5;padding:4px 8px}}.bar{{color:#5B6375;font-size:13px;margin-bottom:16px}}</style>
</head><body><div class="bar">{bar}</div>{body}</body></html>"""


class ReportError(Exception):
    def __init__(self, message: str, status: int = 404):
        super().__init__(message)
        self.message = message
        self.status = status


def confined(folder: Path, rel: str) -> Path:
    folder = folder.resolve()
    path = (folder / rel).resolve()
    if path != folder and folder not in path.parents:
        raise ReportError("the path is outside the folder", 403)
    if not path.is_file():
        raise ReportError("no such file", 404)
    return path


def render(path: Path, raw: bool = False) -> tuple[bytes, str]:
    """(content, media type) for a browser."""
    if raw:
        return path.read_bytes(), mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    if path.suffix == ".md":
        body = md.markdown(path.read_text(errors="replace"), extensions=["tables", "fenced_code"])
        return PAGE.format(title=html.escape(path.name), bar=html.escape(path.name), body=body).encode(), "text/html; charset=utf-8"
    if path.suffix == ".ipynb":
        from nbconvert import HTMLExporter

        body, _ = HTMLExporter(template_name="classic").from_filename(str(path))
        bar = f'{html.escape(path.name)} · read-only · <a href="?raw=1" download>download the notebook</a>'
        return body.replace("<body>", f'<body><div style="font-family:sans-serif;padding:8px 16px">{bar}</div>', 1).encode(), "text/html; charset=utf-8"
    media = mimetypes.guess_type(path.name)[0] or "text/plain"
    if media.startswith("text/") and "charset" not in media:
        media += "; charset=utf-8"
    return path.read_bytes(), media


class Reports:
    def __init__(self, hub: "Hub"):
        self.hub = hub

    def report(self, task_id: int, rel: str, raw: bool = False) -> tuple[bytes, str]:
        return render(confined(self.hub.sessions.reports_dir(task_id), rel), raw)

    def run_file(self, run_id: str, name: str, raw: bool = False) -> tuple[bytes, str]:
        if "/" in run_id or run_id.startswith("."):
            raise ReportError("bad run id", 403)
        return render(confined(self.hub.config.layout().run_dir(run_id), name), raw)

    def with_report_links(self, task_id: int, since_ms: int, message: str) -> str:
        """Files that appeared in the reports folder during the turn and are not linked get a "Reports" line."""
        folder = self.hub.sessions.reports_dir(task_id)
        if not folder.is_dir():
            return message
        base = self.hub.sessions.reports_url(task_id)
        missing = []
        for path in sorted(p for p in folder.rglob("*") if p.is_file()):
            if path.stat().st_mtime * 1000 < since_ms - 1000:
                continue
            rel = path.relative_to(folder).as_posix()
            url = f"{base}/{rel}"
            if url not in message:
                missing.append(f"[{rel}]({url})")
        if not missing:
            return message
        return (message.rstrip() + "\n\n" if message.strip() else "") + "Reports: " + " · ".join(missing)
