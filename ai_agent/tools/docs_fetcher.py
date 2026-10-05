"""Live Documentation & Release Notes Fetcher Tool for ODB@GCP.

Fetches official Oracle Database@Google Cloud documentation and release notes from
a strict allow-list of HTTPS domains (`cloud.google.com`, `docs.cloud.google.com`,
`docs.oracle.com`, `raw.githubusercontent.com`) to prevent SSRF vulnerabilities.
"""

from __future__ import annotations

import html
import json
import re
from urllib.parse import urlparse

import httpx

ALLOWED_DOC_HOSTS: frozenset[str] = frozenset(
    {
        "cloud.google.com",
        "docs.cloud.google.com",
        "docs.oracle.com",
        "raw.githubusercontent.com",
        "registry.terraform.io",
    }
)

CURATED_TOPIC_URLS: dict[str, str] = {
    "overview": "https://cloud.google.com/oracle/database/docs/overview",
    "release-notes": "https://cloud.google.com/oracle/database/docs/release-notes",
    "odb-network": "https://cloud.google.com/oracle/database/docs/odb-networks",
    "autonomous-database": "https://cloud.google.com/oracle/database/docs/autonomous-database",
    "exadata": "https://cloud.google.com/oracle/database/docs/exadata",
    "exascale": "https://cloud.google.com/oracle/database/docs/exascale",
    "base-database": "https://cloud.google.com/oracle/database/docs/base-database",
    "iam-roles": "https://cloud.google.com/oracle/database/docs/access-control",
    "locations": "https://cloud.google.com/oracle/database/docs/locations",
}


def validate_documentation_url(url: str) -> str:
    """Strictly validates that a URL uses HTTPS and targets an allow-listed documentation host."""
    cleaned = url.strip()
    parsed = urlparse(cleaned)
    if parsed.scheme != "https":
        raise ValueError(f"Only HTTPS documentation URLs are permitted (got scheme '{parsed.scheme}').")
    hostname = (parsed.hostname or "").lower()
    if hostname not in ALLOWED_DOC_HOSTS:
        raise ValueError(
            f"Host '{hostname}' is not in the allow-listed documentation domains: {sorted(ALLOWED_DOC_HOSTS)}"
        )
    return cleaned


def _strip_html_to_text(raw_html: str, max_chars: int = 12000) -> str:
    """Extracts readable text from HTML while removing script/style blocks."""
    without_scripts = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", raw_html, flags=re.DOTALL | re.IGNORECASE)
    without_tags = re.sub(r"<[^>]+>", " ", without_scripts)
    unescaped = html.unescape(without_tags)
    collapsed = re.sub(r"\s+", " ", unescaped).strip()
    if len(collapsed) > max_chars:
        return collapsed[:max_chars] + " ...[truncated]"
    return collapsed


def fetch_official_odb_documentation(topic_or_url: str) -> str:
    """Fetches the latest official Oracle Database@Google Cloud documentation or release notes.

    Args:
        topic_or_url: Either a known topic key (`overview`, `release-notes`, `odb-network`,
            `autonomous-database`, `exadata`, `exascale`, `base-database`, `iam-roles`, `locations`)
            or a full HTTPS URL on `cloud.google.com` / `docs.oracle.com`.

    Returns:
        JSON string containing the extracted documentation text and source URL.
    """
    cleaned = topic_or_url.strip()
    target_url = CURATED_TOPIC_URLS.get(cleaned.lower(), cleaned)

    try:
        validated_url = validate_documentation_url(target_url)
    except ValueError as exc:
        return json.dumps(
            {
                "error": str(exc),
                "supported_topics": list(CURATED_TOPIC_URLS.keys()),
                "allowed_hosts": sorted(ALLOWED_DOC_HOSTS),
            },
            indent=2,
        )

    with httpx.Client(timeout=12.0, follow_redirects=True) as client:
        try:
            resp = client.get(validated_url)
            final_host = (urlparse(str(resp.url)).hostname or "").lower()
            if final_host not in ALLOWED_DOC_HOSTS:
                return json.dumps(
                    {"error": f"Redirected to disallowed host '{final_host}'."},
                    indent=2,
                )
            text_excerpt = _strip_html_to_text(resp.text)
            return json.dumps(
                {
                    "topic_or_url": cleaned,
                    "resolved_url": str(resp.url),
                    "http_status": resp.status_code,
                    "content_excerpt": text_excerpt,
                },
                indent=2,
            )
        except Exception as exc:
            return json.dumps(
                {
                    "topic_or_url": cleaned,
                    "resolved_url": validated_url,
                    "error": f"Could not fetch live documentation: {exc}",
                    "available_topics": list(CURATED_TOPIC_URLS.keys()),
                },
                indent=2,
            )
