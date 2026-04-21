"""Background check for the live version available on the Influx docs website."""

from __future__ import annotations

import re
import urllib.request
from typing import Optional


_TIMEOUT_SECONDS = 8


def fetch_live_version(page_url: str) -> Optional[str]:
    """Fetch *page_url* and try to extract the version from the MSI download link.

    Returns a version string like ``"1.2.37.0"`` on success, or ``None`` when
    the page cannot be reached or the version cannot be parsed.  Designed to
    fail silently so callers can simply ignore a ``None`` result.
    """
    if not page_url:
        return None
    try:
        req = urllib.request.Request(page_url, headers={"User-Agent": "RexdeskVersionManager/1"})
        with urllib.request.urlopen(req, timeout=_TIMEOUT_SECONDS) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception:
        return None

    # Primary: grab version from the MSI download URL
    #   e.g. https://downloads.influxtechnology.com/ReXdesk/ReXdesk_1.2.37.0.msi
    m = re.search(r"[\w/]+[_/](\d+(?:\.\d+){2,})\.msi", html, re.IGNORECASE)
    if m:
        return m.group(1)

    # Fallback: "Version X.Y.Z" text on the page
    m = re.search(r"Version\s+(\d+(?:\.\d+){2,})", html, re.IGNORECASE)
    if m:
        return m.group(1)

    return None
