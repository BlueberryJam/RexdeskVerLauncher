"""Background check for the live version available on the Influx docs website."""

from __future__ import annotations

import re
import urllib.request
from typing import Optional


_TIMEOUT_SECONDS = 8

# When walking version numbers forward, stop a line after this many consecutive
# 404s — big enough to jump real gaps on the server (e.g. a missing 1.2.32),
# small enough to finish quickly once past the newest release.
_GAP_TOLERANCE = 8
# Safety cap so a misbehaving server (always 200) can't loop forever.
_MAX_PROBES_PER_LINE = 300


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
    m = re.search(r"influxtechnology\.com/[^\"'\s]*?[_/](\d+(?:\.\d+){2,})\.msi", html, re.IGNORECASE)
    if m:
        return m.group(1)

    # Fallback: "Version X.Y.Z" text on the page
    m = re.search(r"Version\s+(\d+(?:\.\d+){2,})", html, re.IGNORECASE)
    if m:
        return m.group(1)

    return None


def _msi_exists(url: str) -> bool:
    """Return True if *url* responds 200 to a HEAD request."""
    req = urllib.request.Request(
        url, method="HEAD", headers={"User-Agent": "RexdeskVersionManager/1"}
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_SECONDS) as resp:
            return resp.status == 200
    except Exception:
        return False


def discover_newer_versions(
    base_url: str,
    file_prefix: str,
    from_version: str,
    *,
    gap: int = _GAP_TOLERANCE,
) -> list[str]:
    """Find versions newer than *from_version* by walking version numbers forward.

    Starting just past *from_version*, probes ``patch`` numbers upward on the
    current major.minor line, then the start of the next minor and next major
    series.  Each line stops after *gap* consecutive 404s, so real gaps on the
    server (e.g. a missing 1.2.32) are jumped but the walk still terminates
    soon after the newest release.  Returns the versions that exist, oldest
    first.
    """
    if not base_url or not file_prefix:
        return []

    base = base_url.rstrip("/")

    def exists(version: str) -> bool:
        return _msi_exists(f"{base}/{file_prefix}_{version}.msi")

    try:
        parts = [int(p) for p in from_version.split(".")]
    except ValueError:
        parts = [0, 0, 0]
    while len(parts) < 3:
        parts.append(0)
    major, minor, patch = parts[0], parts[1], parts[2]

    # Lines to walk, in order: rest of this minor, next minor, next major.
    starts = [
        (major, minor, patch + 1),
        (major, minor + 1, 0),
        (major + 1, 0, 0),
    ]

    found: list[str] = []
    for (ma, mi, start_patch) in starts:
        misses = 0
        p = start_patch
        while misses < gap and (p - start_patch) < _MAX_PROBES_PER_LINE:
            version = f"{ma}.{mi}.{p}.0"
            if exists(version):
                found.append(version)
                misses = 0
            else:
                misses += 1
            p += 1
    return found
