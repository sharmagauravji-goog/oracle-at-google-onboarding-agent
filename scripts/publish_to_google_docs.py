#!/usr/bin/env python3
"""Converts `docs/DEMO_FLOW_PLAYBOOK.md` into a Google Docs-ready HTML file and optionally uploads it to Google Docs.

Usage:
  # 1. Generate the Google Docs importable HTML file (`docs/Oracle_At_Google_Onboarding_Agent_Demo_Playbook.html`)
  python3 scripts/publish_to_google_docs.py --html-only

  # 2. Authenticate with Google Drive scope and create a live Google Doc in your Google Drive:
  gcloud auth login --enable-gdrive-access
  python3 scripts/publish_to_google_docs.py
"""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent
MD_PATH = REPO_ROOT / "docs" / "DEMO_FLOW_PLAYBOOK.md"
HTML_PATH = REPO_ROOT / "docs" / "Oracle_At_Google_Onboarding_Agent_Demo_Playbook.html"
DOC_TITLE = "Oracle@Google Onboarding Agent — Live Demo Flow Playbook (Antigravity IDE)"


def _markdown_to_google_docs_html(md_text: str) -> str:
    """Converts the Markdown playbook into clean, styled HTML that Google Docs converts into native tables & headings."""
    lines = md_text.splitlines()
    out: list[str] = [
        "<!DOCTYPE html>",
        "<html><head><meta charset='utf-8'>",
        f"<title>{html.escape(DOC_TITLE)}</title>",
        "<style>",
        "body { font-family: Arial, sans-serif; color: #202124; line-height: 1.5; max-width: 900px; margin: 24px auto; }",
        "h1 { color: #1a73e8; font-size: 22pt; border-bottom: 2px solid #1a73e8; padding-bottom: 6px; }",
        "h2 { color: #174ea6; font-size: 16pt; margin-top: 24px; }",
        "h3 { color: #188038; font-size: 13pt; margin-top: 18px; }",
        "code { font-family: 'Courier New', monospace; background-color: #f1f3f4; padding: 1px 4px; border-radius: 3px; }",
        "pre { font-family: 'Courier New', monospace; background-color: #f8f9fa; border: 1px solid #dadce0; padding: 12px; border-radius: 6px; white-space: pre-wrap; }",
        "blockquote { border-left: 4px solid #1a73e8; background-color: #e8f0fe; padding: 10px 14px; margin: 12px 0; }",
        "table { border-collapse: collapse; width: 100%; margin: 14px 0; }",
        "th, td { border: 1px solid #dadce0; padding: 8px 10px; text-align: left; vertical-align: top; }",
        "th { background-color: #e8f0fe; color: #174ea6; font-weight: bold; }",
        "</style></head><body>",
    ]

    in_code_block = False
    code_lines: list[str] = []
    in_table = False
    table_rows: list[list[str]] = []

    def _inline_format(text: str) -> str:
        escaped = html.escape(text)
        escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
        escaped = re.sub(r"\*(.+?)\*", r"<i>\1</i>", escaped)
        escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
        escaped = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"<a href='\2'>\1</a>", escaped)
        return escaped

    def _flush_table() -> None:
        nonlocal in_table, table_rows
        if not in_table or not table_rows:
            return
        out.append("<table>")
        header = table_rows[0]
        out.append("<thead><tr>" + "".join(f"<th>{_inline_format(c)}</th>" for c in header) + "</tr></thead>")
        out.append("<tbody>")
        for row in table_rows[1:]:
            if all(re.match(r"^:?-{2,}:?$", c.strip()) for c in row):
                continue
            out.append("<tr>" + "".join(f"<td>{_inline_format(c)}</td>" for c in row) + "</tr>")
        out.append("</tbody></table>")
        in_table = False
        table_rows = []

    for line in lines:
        if line.strip().startswith("```"):
            _flush_table()
            if not in_code_block:
                in_code_block = True
                code_lines = []
            else:
                out.append("<pre>" + html.escape("\n".join(code_lines)) + "</pre>")
                in_code_block = False
            continue

        if in_code_block:
            code_lines.append(line)
            continue

        if line.strip().startswith("|") and line.strip().endswith("|"):
            in_table = True
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            table_rows.append(cells)
            continue
        else:
            _flush_table()

        stripped = line.strip()
        if not stripped:
            continue
        if stripped == "---":
            out.append("<hr/>")
        elif stripped.startswith("# "):
            out.append(f"<h1>{_inline_format(stripped[2:])}</h1>")
        elif stripped.startswith("## "):
            out.append(f"<h2>{_inline_format(stripped[3:])}</h2>")
        elif stripped.startswith("### "):
            out.append(f"<h3>{_inline_format(stripped[4:])}</h3>")
        elif stripped.startswith("> "):
            out.append(f"<blockquote>{_inline_format(stripped[2:])}</blockquote>")
        elif re.match(r"^(\d+\.|-)\s+", stripped):
            out.append(f"<p style='margin: 4px 0 4px 18px;'>• {_inline_format(re.sub(r'^(\d+\.|-)\s+', '', stripped))}</p>")
        else:
            out.append(f"<p>{_inline_format(stripped)}</p>")

    _flush_table()
    out.append("</body></html>")
    return "\n".join(out)


def _get_gcloud_token() -> str | None:
    gcloud_bin = shutil.which("gcloud")
    if not gcloud_bin:
        return None
    proc = subprocess.run(
        [gcloud_bin, "auth", "print-access-token", "--quiet"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if proc.returncode == 0 and proc.stdout.strip():
        return proc.stdout.strip()
    return None


def upload_html_as_google_doc(html_content: str, title: str) -> str | None:
    """Uploads HTML content to Google Drive with conversion to a native Google Doc (`application/vnd.google-apps.document`)."""
    token = _get_gcloud_token()
    if not token:
        return None

    boundary = "===odb_onboarding_agent_gdoc_boundary==="
    metadata = json.dumps(
        {
            "name": title,
            "mimeType": "application/vnd.google-apps.document",
        }
    )
    body = (
        f"--{boundary}\r\n"
        "Content-Type: application/json; charset=UTF-8\r\n\r\n"
        f"{metadata}\r\n"
        f"--{boundary}\r\n"
        "Content-Type: text/html; charset=UTF-8\r\n\r\n"
        f"{html_content}\r\n"
        f"--{boundary}--\r\n"
    ).encode("utf-8")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": f"multipart/related; boundary={boundary}",
    }
    url = "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id,name,webViewLink"
    with httpx.Client(timeout=20.0) as client:
        resp = client.post(url, headers=headers, content=body)
        if resp.status_code in (200, 201):
            data = resp.json()
            return data.get("webViewLink") or f"https://docs.google.com/document/d/{data.get('id')}/edit"
        print(
            f"[info] Google Drive API returned HTTP {resp.status_code}: {resp.text[:300]}",
            file=sys.stderr,
        )
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Google Docs HTML and optionally upload to Google Docs.")
    parser.add_argument("--html-only", action="store_true", help="Only generate the Google Docs HTML file locally.")
    args = parser.parse_args()

    md_text = MD_PATH.read_text(encoding="utf-8")
    html_content = _markdown_to_google_docs_html(md_text)
    HTML_PATH.write_text(html_content, encoding="utf-8")
    print(f"[ok] Generated Google Docs-ready HTML file: {HTML_PATH}")

    if args.html_only:
        return 0

    doc_url = upload_html_as_google_doc(html_content, DOC_TITLE)
    if doc_url:
        print(f"\n[SUCCESS] Created Google Doc in your Google Drive:\n  {doc_url}")
        return 0

    print(
        "\n[Action Needed to Auto-Create in Google Drive]\n"
        "Your current `gcloud` token only has `cloud-platform` scope (not Google Drive scope).\n"
        "Either:\n"
        "  Option A (1-Click Upload via CLI): Run:\n"
        "    gcloud auth login --enable-gdrive-access\n"
        "    python3 scripts/publish_to_google_docs.py\n\n"
        "  Option B (Instant Browser Import): Open https://docs.new -> File -> Open -> Upload -> select:\n"
        f"    {HTML_PATH}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
