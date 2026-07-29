"""Background check for the live version available on the Influx docs website."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import re
import urllib.request
from typing import Callable, Optional


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


# Full-scan tuning. Patches are probed in parallel batches; a batch with no hits
# at all ends that major.minor line, so the batch size doubles as the gap
# tolerance for missing patch numbers within a line.
_SCAN_BATCH = 16
_SCAN_WORKERS = 12
_EMPTY_MINOR_TOLERANCE = 2
_MAX_SCAN_PROBES = 2000


def _version_sort_key(version: str) -> tuple[int, ...]:
    try:
        return tuple(int(p) for p in version.split("."))
    except ValueError:
        return (0,)


def discover_all_versions(
    base_url: str,
    file_prefix: str,
    *,
    start_major: int = 1,
    progress: Optional[Callable[[str], None]] = None,
) -> list[str]:
    """Enumerate every version the server holds, oldest first.

    Unlike :func:`discover_newer_versions`, this does not start from what is
    already known — it walks the whole major/minor/patch space, so a fresh
    install can populate the full release history rather than only releases
    newer than the newest local version.

    Probing is batched across threads because a full walk is several hundred
    HEAD requests. *progress* is called with a short status string as each
    major.minor line finishes.
    """
    if not base_url or not file_prefix:
        return []

    base = base_url.rstrip("/")
    found: list[str] = []
    probes = 0

    with ThreadPoolExecutor(max_workers=_SCAN_WORKERS) as pool:
        def probe_batch(versions: list[str]) -> list[str]:
            nonlocal probes
            probes += len(versions)
            urls = [f"{base}/{file_prefix}_{v}.msi" for v in versions]
            return [v for v, ok in zip(versions, pool.map(_msi_exists, urls)) if ok]

        major = start_major
        while probes < _MAX_SCAN_PROBES:
            major_hits = 0
            empty_minors = 0
            minor = 0
            while empty_minors <= _EMPTY_MINOR_TOLERANCE and probes < _MAX_SCAN_PROBES:
                if progress:
                    progress(f"{major}.{minor}.x")
                line_hits = 0
                patch = 0
                while probes < _MAX_SCAN_PROBES:
                    batch = [f"{major}.{minor}.{p}.0"
                             for p in range(patch, patch + _SCAN_BATCH)]
                    hits = probe_batch(batch)
                    found.extend(hits)
                    line_hits += len(hits)
                    patch += _SCAN_BATCH
                    if not hits:
                        break
                if line_hits:
                    major_hits += line_hits
                    empty_minors = 0
                else:
                    empty_minors += 1
                minor += 1
            # A whole major series with nothing in it means there is no point
            # looking at higher majors.
            if not major_hits:
                break
            major += 1

    found.sort(key=_version_sort_key)
    return found
