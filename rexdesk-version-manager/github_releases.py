"""GitHub releases as a version source for local-build products.

The Rust rewrite publishes each build as a GitHub release (tag ``v1.0.0.694``)
holding a portable zip (``ReXdesk-Rust-1.0.0.694-portable.zip``) and a
``SHA256SUMS.txt``. This module lists those releases and installs one into
``library/<product>/installs/<version>/``, after which it is an ordinary local
build.

The repo may be private, so requests carry the GitHub CLI's token when ``gh``
is installed and signed in. The token is only held in memory for the request;
it is never written to the catalog or anywhere else.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tempfile
import threading
from typing import Callable, Optional
import urllib.error
import urllib.request
import zipfile


API_ROOT = "https://api.github.com"
_USER_AGENT = "RexdeskVersionManager/1"
_TIMEOUT_SECONDS = 20
_CHUNK = 1024 * 256
_MAX_PAGES = 10
SUMS_ASSET = "SHA256SUMS.txt"
NOTES_FILE = "RELEASE_NOTES.txt"

_TAG_RE = re.compile(r"^v?(\d+(?:\.\d+)+)$")


class GitHubAccessError(RuntimeError):
    """The releases could not be read (no access, rate limit, offline)."""


class ChecksumError(RuntimeError):
    """The downloaded zip does not match SHA256SUMS.txt."""


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    tag: str
    name: str
    body: str
    published_at: str      # ISO timestamp, e.g. 2026-11-11T10:58:51Z
    html_url: str
    prerelease: bool
    zip_name: str
    zip_url: str           # API asset URL (works for private repos with a token)
    zip_size: int
    sums_url: str          # API asset URL of SHA256SUMS.txt, "" if missing

    @property
    def published_date(self) -> str:
        return self.published_at[:10]


# ---------------------------------------------------------------------- token
# gh can take several seconds just to start (seen: 2-15 s), so a token it
# hands out is kept in memory for the rest of the session. Never written to disk.
_GH_TIMEOUT_SECONDS = 45
_token_lock = threading.Lock()
_cached_token: Optional[str] = None


def forget_token() -> None:
    """Drop the in-memory token (e.g. after GitHub refused it)."""
    global _cached_token
    with _token_lock:
        _cached_token = None


def get_token() -> Optional[str]:
    """A GitHub token for API calls, or None to go unauthenticated.

    Uses GH_TOKEN / GITHUB_TOKEN if set, otherwise asks the GitHub CLI
    (``gh auth token``) when it is installed and signed in.
    """
    global _cached_token
    for var in ("GH_TOKEN", "GITHUB_TOKEN"):
        value = os.environ.get(var, "").strip()
        if value:
            return value
    with _token_lock:
        if _cached_token:
            return _cached_token
        gh = shutil.which("gh")
        if not gh:
            return None
        kwargs: dict = {}
        if os.name == "nt":
            # The manager runs windowless (pythonw); don't flash a console.
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        env = dict(os.environ, GH_NO_UPDATE_NOTIFIER="1",
                   GH_NO_EXTENSION_UPDATE_NOTIFIER="1", GH_PROMPT_DISABLED="1")
        try:
            result = subprocess.run(
                [gh, "auth", "token"], capture_output=True, text=True,
                timeout=_GH_TIMEOUT_SECONDS, check=False, env=env, **kwargs,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        token = (result.stdout or "").strip()
        if result.returncode != 0 or not token or any(c.isspace() for c in token):
            return None
        _cached_token = token
        return token


# ---------------------------------------------------------------------- HTTP
def _request(url: str, token: Optional[str], accept: str) -> urllib.request.Request:
    req = urllib.request.Request(url, headers={
        "User-Agent": _USER_AGENT,
        "Accept": accept,
        "X-GitHub-Api-Version": "2022-11-28",
    })
    if token:
        # Unredirected: asset downloads redirect to a signed storage URL that
        # rejects (and must never see) the GitHub token.
        req.add_unredirected_header("Authorization", f"Bearer {token}")
    return req


def _access_error(what: str, exc: Exception, token: Optional[str]) -> GitHubAccessError:
    """Map a failed request for *what* (e.g. "MadeByDoru/rexdesk-rs releases")
    to a message the status bar can show."""
    if isinstance(exc, urllib.error.HTTPError):
        remaining = exc.headers.get("X-RateLimit-Remaining") if exc.headers else None
        if exc.code in (403, 429) and remaining == "0":
            return GitHubAccessError(
                "GitHub rate limit reached — try again later"
                + ("" if token else ", or sign in with the GitHub CLI (gh auth login)"))
        if exc.code in (401, 403, 404):
            if token:
                return GitHubAccessError(
                    f"GitHub denied access to {what} (HTTP {exc.code}) — "
                    "the signed-in GitHub account may not have access to this repo")
            return GitHubAccessError(
                f"Cannot see {what} (HTTP {exc.code}) — the repo is private. "
                "Install the GitHub CLI and run: gh auth login")
        return GitHubAccessError(f"GitHub returned HTTP {exc.code} for {what}")
    if isinstance(exc, urllib.error.URLError):
        return GitHubAccessError(f"Could not reach GitHub ({exc.reason})")
    return GitHubAccessError(f"Could not read {what} ({exc})")


def _get_json(url: str, token: Optional[str]) -> tuple[object, str]:
    """GET *url*; return (parsed JSON, Link header)."""
    req = _request(url, token, "application/vnd.github+json")
    with urllib.request.urlopen(req, timeout=_TIMEOUT_SECONDS) as resp:
        link = resp.headers.get("Link", "") if resp.headers else ""
        return json.loads(resp.read().decode("utf-8")), link


def _next_link(link_header: str) -> Optional[str]:
    for part in link_header.split(","):
        m = re.search(r'<([^>]+)>\s*;\s*rel="next"', part)
        if m:
            return m.group(1)
    return None


# ---------------------------------------------------------------------- listing
def parse_release(raw: dict, asset_template: str) -> Optional[ReleaseInfo]:
    """Turn one GitHub API release into a ReleaseInfo, or None to skip it
    (draft, tag that isn't a version, or no portable zip)."""
    if raw.get("draft"):
        return None
    tag = str(raw.get("tag_name") or "")
    m = _TAG_RE.match(tag)
    if not m:
        return None
    version = m.group(1)
    assets = {str(a.get("name")): a for a in raw.get("assets") or []}
    zip_name = asset_template.format(version=version)
    zip_asset = assets.get(zip_name)
    if not zip_asset:
        return None
    sums = assets.get(SUMS_ASSET)
    return ReleaseInfo(
        version=version,
        tag=tag,
        name=str(raw.get("name") or tag),
        body=str(raw.get("body") or ""),
        published_at=str(raw.get("published_at") or ""),
        html_url=str(raw.get("html_url") or ""),
        prerelease=bool(raw.get("prerelease")),
        zip_name=zip_name,
        zip_url=str(zip_asset.get("url") or ""),
        zip_size=int(zip_asset.get("size") or 0),
        sums_url=str(sums.get("url") or "") if sums else "",
    )


def list_releases(repo: str, asset_template: str, token: Optional[str]) -> list[ReleaseInfo]:
    """Every published release of *repo* that carries a portable zip.

    Raises GitHubAccessError when GitHub can't be read.
    """
    url: Optional[str] = f"{API_ROOT}/repos/{repo}/releases?per_page=100"
    found: dict[str, ReleaseInfo] = {}
    pages = 0
    try:
        while url and pages < _MAX_PAGES:
            data, link = _get_json(url, token)
            pages += 1
            if not isinstance(data, list):
                raise GitHubAccessError(f"Unexpected reply from GitHub for {repo} releases")
            for raw in data:
                info = parse_release(raw, asset_template) if isinstance(raw, dict) else None
                if info and info.version not in found:
                    found[info.version] = info
            url = _next_link(link)
    except GitHubAccessError:
        raise
    except Exception as exc:  # noqa: BLE001 - mapped to a user-facing message
        raise _access_error(f"{repo} releases", exc, token) from exc
    return list(found.values())


# ---------------------------------------------------------------------- download
def _download(url: str, token: Optional[str], dest: Path,
              progress: Optional[Callable[[int], None]] = None) -> str:
    """Stream an asset to *dest*; return its SHA256 hex digest."""
    digest = hashlib.sha256()
    req = _request(url, token, "application/octet-stream")
    done = 0
    with urllib.request.urlopen(req, timeout=_TIMEOUT_SECONDS) as resp, dest.open("wb") as out:
        while True:
            chunk = resp.read(_CHUNK)
            if not chunk:
                break
            out.write(chunk)
            digest.update(chunk)
            done += len(chunk)
            if progress:
                progress(done)
    return digest.hexdigest()


def parse_sha256sums(text: str) -> dict[str, str]:
    """``<hash>  <name>`` lines (``*name`` for binary mode) -> {name: hash}."""
    sums: dict[str, str] = {}
    for line in text.splitlines():
        m = re.match(r"^\s*([0-9a-fA-F]{64})\s+\*?(.+?)\s*$", line)
        if m:
            sums[m.group(2)] = m.group(1).lower()
    return sums


def _safe_member_path(name: str) -> Optional[PurePosixPath]:
    """Normalise a zip entry name (the release zips use backslashes) and refuse
    anything that would land outside the target folder."""
    norm = name.replace("\\", "/")
    if norm.startswith("/") or re.match(r"^[A-Za-z]:", norm):
        raise ValueError(f"Unsafe path in zip: {name}")
    parts = [p for p in norm.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        raise ValueError(f"Unsafe path in zip: {name}")
    return PurePosixPath(*parts) if parts else None


def extract_zip(zip_path: Path, dest: Path) -> None:
    """Extract *zip_path* into *dest*, normalising backslash separators. If every
    entry sits under one top-level folder, that folder is dropped so the exe
    lands directly in *dest*."""
    with zipfile.ZipFile(zip_path) as zf:
        entries = []
        for info in zf.infolist():
            rel = _safe_member_path(info.filename)
            if rel is None:
                continue
            is_dir = info.filename.replace("\\", "/").endswith("/")
            entries.append((info, rel, is_dir))

        tops = {rel.parts[0] for _, rel, _ in entries}
        strip = (
            len(tops) == 1
            and all(len(rel.parts) > 1 or is_dir for _, rel, is_dir in entries)
        )

        dest.mkdir(parents=True, exist_ok=True)
        for info, rel, is_dir in entries:
            parts = rel.parts[1:] if strip else rel.parts
            if not parts:
                continue
            target = dest.joinpath(*parts)
            if is_dir:
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, target.open("wb") as out:
                shutil.copyfileobj(src, out, _CHUNK)


def release_notes_text(release: ReleaseInfo, product_name: str) -> str:
    header = [f"{product_name} {release.version} — {release.name}"]
    meta = []
    if release.published_date:
        meta.append(f"Published {release.published_date}")
    if release.prerelease:
        meta.append("pre-release")
    if meta:
        header.append(", ".join(meta))
    if release.html_url:
        header.append(release.html_url)
    body = release.body.replace("\r\n", "\n").strip()
    return "\n".join(header) + "\n\n" + (body or "(No release notes on GitHub.)") + "\n"


def install_release(
    release: ReleaseInfo,
    installs_dir: Path,
    token: Optional[str],
    *,
    product_name: str = "",
    staging_parent: Optional[Path] = None,
    progress: Optional[Callable[[int, int], None]] = None,
) -> Path:
    """Download, verify and extract *release* into ``installs_dir/<version>``.

    Work happens in a staging folder (default: next to *installs_dir*, so it never
    shows up as a version) and is moved into place only once complete. Raises
    ChecksumError on a hash mismatch, FileExistsError if the version folder
    already exists, GitHubAccessError if GitHub can't be read.
    """
    final_dir = installs_dir / release.version
    if final_dir.exists():
        raise FileExistsError(f"{final_dir} already exists")
    if not release.sums_url:
        raise ChecksumError(f"Release {release.tag} has no {SUMS_ASSET} to verify against")

    staging_parent = staging_parent or installs_dir.parent
    staging_parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=f"_download_{release.version}_", dir=staging_parent))
    try:
        sums_path = work / SUMS_ASSET
        zip_path = work / release.zip_name
        try:
            _download(release.sums_url, token, sums_path)
            expected = parse_sha256sums(sums_path.read_text(encoding="utf-8-sig")).get(release.zip_name)
            if not expected:
                raise ChecksumError(f"{SUMS_ASSET} has no entry for {release.zip_name}")
            total = release.zip_size
            actual = _download(
                release.zip_url, token, zip_path,
                (lambda done: progress(done, total)) if progress else None)
        except (ChecksumError, GitHubAccessError):
            raise
        except (urllib.error.URLError, OSError) as exc:
            if isinstance(exc, urllib.error.URLError):
                raise _access_error(f"the {release.tag} download", exc, token) from exc
            raise
        if actual != expected:
            raise ChecksumError(
                f"{release.zip_name} failed its SHA256 check "
                f"(expected {expected[:12]}…, got {actual[:12]}…) — not installed")

        content = work / "content"
        extract_zip(zip_path, content)
        (content / NOTES_FILE).write_text(
            release_notes_text(release, product_name or "Version"), encoding="utf-8")

        installs_dir.mkdir(parents=True, exist_ok=True)
        if final_dir.exists():
            raise FileExistsError(f"{final_dir} already exists")
        shutil.move(str(content), str(final_dir))
        return final_dir
    finally:
        shutil.rmtree(work, ignore_errors=True)


# ---------------------------------------------------------------------- catalog
def merge_releases(catalog, releases: list[ReleaseInfo]) -> tuple[list[str], list[str]]:
    """Fold *releases* into *catalog* (a CatalogStore): versions not in it yet
    are added as 'available'; 'available' entries whose release is gone from
    GitHub are dropped; an empty release date is filled from GitHub.

    Returns (added versions, removed versions).
    """
    from dataclasses import replace

    from catalog import VersionRecord

    by_version = {r.version: r for r in releases}
    added: list[str] = []
    removed: list[str] = []
    for record in catalog.all_versions():
        if record.status == "available" and record.version not in by_version:
            catalog.remove(record.version)
            removed.append(record.version)
    for version, release in by_version.items():
        record = catalog.get(version)
        if record is None:
            catalog.upsert(VersionRecord(
                version=version, status="available",
                release_date=release.published_date))
            added.append(version)
        elif not record.release_date and release.published_date:
            catalog.upsert(replace(record, release_date=release.published_date))
    return added, removed
