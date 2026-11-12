from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import shutil
import sys


APP_NAME = "Rexdesk Version Manager"


@dataclass(frozen=True)
class ProductDef:
    key: str
    display_name: str
    exe_hint: str
    # File in assets/ (SVG). Same-stem PNG is used when SVG cannot be rasterized (e.g. no Cairo).
    logo_svg: str
    # Public docs page where the download link lives (empty = skip web check).
    download_page_url: str = ""
    # Direct-download server. The MSI URL is built as:
    #   {download_base_url}/{download_file_prefix}{version_sep}{version}.msi
    # e.g. https://downloads.influxtechnology.com/ReXdesk/ReXdesk_1.2.65.0.msi
    download_base_url: str = "https://downloads.influxtechnology.com/ReXdesk"
    download_file_prefix: str = ""
    # Character between the file prefix and the version in the MSI filename.
    # Rexdesk/Rexbridge use "_" (ReXdesk_1.2.65.0.msi); K-CAL uses "."
    # (InfluxKCal.3.45.msi).
    version_sep: str = "_"
    # Version-number shape the server uses, which drives how the update scanner
    # walks the version space:
    #   "quad" -> a.b.c.0 (Rexdesk/Rexbridge)
    #   "duo"  -> <major>.<minor>, a single major line (K-CAL, e.g. 3.45)
    version_scheme: str = "quad"
    # For the "duo" scheme, the fixed major line to scan (e.g. 3 for K-CAL).
    version_major: int = 0
    # Versions are local builds dropped into library/<key>/installs/<version>/
    # (no MSI, no download server) — e.g. the Rust rewrite, published by
    # rexdesk-rs/tools/publish-to-launcher.ps1.
    local_builds: bool = False
    # Local-build products whose builds are also published as GitHub releases
    # ("owner/name"). Check for Updates lists them; Download fetches the asset
    # named by github_asset_template ({version} = tag without the leading "v")
    # and verifies it against the release's SHA256SUMS.txt.
    github_repo: str = ""
    github_asset_template: str = ""

PRODUCTS: dict[str, ProductDef] = {
    "rexdesk": ProductDef(
        "rexdesk", "Rexdesk", "rexdesk", "rexdesk.svg",
        download_page_url="https://docs.influxtechnology.com/support_guides/software-links/software-links/rexdesk-software-links",
        download_file_prefix="ReXdesk",
    ),
    "rexbridge": ProductDef(
        "rexbridge", "Rexbridge", "rexbridge", "rexbridge.svg",
        download_file_prefix="ReXbridge",
    ),
    "kcal": ProductDef(
        "kcal", "K-CAL", "kcal", "",
        # K-CAL shares the K-Series docs page with K-Log, so auto-parsing that
        # page would report the wrong product's version. Leave the web check off.
        download_base_url="https://downloads.influxtechnology.com/K-Box",
        download_file_prefix="InfluxKCal",
        version_sep=".",
        version_scheme="duo",
        version_major=3,
    ),
    "rustrewrite": ProductDef(
        "rustrewrite", "Rust Rewrite", "rexdesk", "rexdesk.svg",
        download_base_url="",
        local_builds=True,
        github_repo="MadeByDoru/rexdesk-rs",
        github_asset_template="ReXdesk-Rust-{version}-portable.zip",
    ),
    # K-Cal rebuilt in Rust; versions published by kcal-rs/tools/publish-to-launcher.ps1.
    "kcalrust": ProductDef(
        "kcalrust", "K-CAL Rust Build", "kcal", "",
        download_base_url="",
        local_builds=True,
    ),
    # ReXbridge rebuilt in Rust; versions published by rexbridge-rs/tools/publish-to-launcher.ps1.
    "rexbridgerust": ProductDef(
        "rexbridgerust", "ReXbridge Rust Build", "rexbridge", "rexbridge.svg",
        download_base_url="",
        local_builds=True,
    ),
}

PRODUCT_KEYS: list[str] = list(PRODUCTS.keys())
DEFAULT_PRODUCT = "rexdesk"


def build_download_url(product: ProductDef, version: str) -> str | None:
    """Build the direct MSI download URL for *version*, or None if unavailable.

    Mirrors the server layout, e.g. version '1.2.65.0' for Rexdesk becomes
    https://downloads.influxtechnology.com/ReXdesk/ReXdesk_1.2.65.0.msi
    and '3.45' for K-CAL becomes
    https://downloads.influxtechnology.com/K-Box/InfluxKCal.3.45.msi
    """
    version = version.strip()
    if not product.download_file_prefix or not product.download_base_url or not version:
        return None
    base = product.download_base_url.rstrip("/")
    return f"{base}/{product.download_file_prefix}{product.version_sep}{version}.msi"


def safe_version_slug(version_label: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", version_label.strip())
    return cleaned.strip("._-") or "unknown_version"


_CLOUD_FOLDER_MARKERS = ("onedrive", "dropbox", "google drive", "icloud")


def is_cloud_synced_path(path: Path) -> bool:
    """True when *path* sits inside a folder managed by a cloud-sync client.

    Files there can be on-demand placeholders, which Windows Installer cannot
    hydrate, and sync locks interfere with installs writing into the folder.
    """
    return any(
        marker in part.lower()
        for part in Path(path).parts
        for marker in _CLOUD_FOLDER_MARKERS
    )


@dataclass(frozen=True)
class Paths:
    app_root: Path
    library_root: Path
    product_root: Path
    msi_dir: Path
    installs_dir: Path
    patch_notes_dir: Path
    bug_notes_dir: Path
    catalog_path: Path
    backup_dir: Path


def _app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    source_root = Path(__file__).resolve().parent
    if source_root.name == "rexdesk-version-manager":
        return source_root.parent
    return source_root


def assets_dir() -> Path:
    """Bundled logos live under PyInstaller's extract dir, not next to the .exe."""
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            bundled = Path(meipass) / "assets"
            if bundled.is_dir():
                return bundled
        return _app_root() / "assets"
    return Path(__file__).resolve().parent / "assets"


def resolve_paths(product_key: str = DEFAULT_PRODUCT) -> Paths:
    app_root = _app_root()
    library_root = app_root / "library"
    product_root = library_root / product_key

    return Paths(
        app_root=app_root,
        library_root=library_root,
        product_root=product_root,
        msi_dir=product_root / "msi",
        installs_dir=product_root / "installs",
        patch_notes_dir=product_root / "patch_notes",
        bug_notes_dir=product_root / "bug_notes",
        catalog_path=product_root / "catalog.json",
        backup_dir=product_root / "_backup",
    )


def ensure_layout(paths: Paths) -> None:
    paths.product_root.mkdir(parents=True, exist_ok=True)
    paths.msi_dir.mkdir(parents=True, exist_ok=True)
    paths.installs_dir.mkdir(parents=True, exist_ok=True)
    paths.patch_notes_dir.mkdir(parents=True, exist_ok=True)
    paths.bug_notes_dir.mkdir(parents=True, exist_ok=True)


def migrate_legacy_library(library_root: Path) -> None:
    """Move data from the old flat library/ layout into library/rexdesk/."""
    old_catalog = library_root / "catalog.json"
    dest = library_root / DEFAULT_PRODUCT
    if not old_catalog.exists() or dest.exists():
        return

    dest.mkdir(parents=True, exist_ok=True)
    for name in ("msi", "installs", "patch_notes", "bug_notes", "_backup", "catalog.json"):
        src = library_root / name
        if src.exists():
            shutil.move(str(src), str(dest / name))

    _rewrite_catalog_paths(dest / "catalog.json", library_root, dest)


def _rewrite_catalog_paths(catalog_path: Path, old_root: Path, new_root: Path) -> None:
    """Replace absolute path prefixes in catalog.json after a directory move."""
    import json

    if not catalog_path.exists():
        return
    try:
        data = json.loads(catalog_path.read_text(encoding="utf-8"))
        old_str = str(old_root)
        new_str = str(new_root)

        def _rewrite(value: object) -> object:
            if isinstance(value, str) and value.startswith(old_str):
                return new_str + value[len(old_str):]
            if isinstance(value, dict):
                return {k: _rewrite(v) for k, v in value.items()}
            if isinstance(value, list):
                return [_rewrite(item) for item in value]
            return value

        catalog_path.write_text(json.dumps(_rewrite(data), indent=2), encoding="utf-8")
    except Exception:
        pass
