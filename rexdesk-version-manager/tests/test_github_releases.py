"""Tests for GitHub-release updates of local-build products (Rust Rewrite).

No network: urllib.request.urlopen and the gh CLI are mocked. Every test works in
a throwaway library folder.

Run from rexdesk-version-manager/:  python -m unittest discover -s tests -v
"""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import urllib.error
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from catalog import CatalogStore, VersionRecord  # noqa: E402
import config  # noqa: E402
import github_releases as gr  # noqa: E402

REPO = "MadeByDoru/rexdesk-rs"
TEMPLATE = "ReXdesk-Rust-{version}-portable.zip"
API = f"{gr.API_ROOT}/repos/{REPO}"


def make_zip(entries: dict[str, bytes]) -> bytes:
    """A zip whose entry names are written exactly as given (backslashes kept,
    like the release zips built on Windows)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries.items():
            info = zipfile.ZipInfo("placeholder")
            info.filename = name  # bypass ZipInfo's os.sep normalisation
            info.compress_type = zipfile.ZIP_DEFLATED
            if name.endswith(("/", "\\")):
                info.external_attr = 0o40755 << 16 | 0x10
            zf.writestr(info, data)
    return buf.getvalue()


def raw_release(version: str, *, asset_id: int, draft: bool = False,
                prerelease: bool = False, with_zip: bool = True,
                with_sums: bool = True, body: str = "Fixes things.") -> dict:
    assets = []
    if with_zip:
        assets.append({"name": TEMPLATE.format(version=version), "size": 1234,
                       "url": f"{API}/releases/assets/{asset_id}"})
    if with_sums:
        assets.append({"name": "SHA256SUMS.txt", "size": 103,
                       "url": f"{API}/releases/assets/{asset_id + 1}"})
    return {
        "tag_name": f"v{version}", "name": f"ReXdesk {version}", "body": body,
        "draft": draft, "prerelease": prerelease,
        "published_at": "2026-11-11T10:58:51Z",
        "html_url": f"https://github.com/{REPO}/releases/tag/v{version}",
        "assets": assets,
    }


class FakeResponse(io.BytesIO):
    def __init__(self, data: bytes, headers: dict | None = None) -> None:
        super().__init__(data)
        self.headers = headers or {}
        self.status = 200

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


class FakeGitHub:
    """Serves canned URLs and records each request (URL, headers)."""

    def __init__(self, routes: dict[str, object]) -> None:
        self.routes = routes
        self.requests: list[tuple[str, dict, dict]] = []

    def __call__(self, req, timeout=None):
        self.requests.append((req.full_url, dict(req.headers), dict(req.unredirected_hdrs)))
        route = self.routes.get(req.full_url)
        if route is None:
            raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)
        if isinstance(route, Exception):
            raise route
        if isinstance(route, tuple):
            body, headers = route
            return FakeResponse(body, headers)
        if isinstance(route, (list, dict)):
            return FakeResponse(json.dumps(route).encode())
        return FakeResponse(route)


def http_error(code: int, headers: dict | None = None) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://api.github.com/x", code, "err", headers or {}, None)


class ListReleasesTests(unittest.TestCase):
    def test_parses_versions_and_skips_unusable_releases(self):
        fake = FakeGitHub({f"{API}/releases?per_page=100": [
            raw_release("1.0.0.694", asset_id=10),
            raw_release("1.0.0.700", asset_id=20, draft=True),
            raw_release("1.0.0.612", asset_id=30, prerelease=True),
            raw_release("1.0.0.650", asset_id=40, with_zip=False),
            {"tag_name": "nightly", "assets": []},
        ]})
        with mock.patch("urllib.request.urlopen", fake):
            releases = gr.list_releases(REPO, TEMPLATE, "tok")
        by_version = {r.version: r for r in releases}
        self.assertEqual(set(by_version), {"1.0.0.694", "1.0.0.612"})
        r = by_version["1.0.0.694"]
        self.assertEqual(r.zip_name, "ReXdesk-Rust-1.0.0.694-portable.zip")
        self.assertEqual(r.zip_url, f"{API}/releases/assets/10")
        self.assertEqual(r.sums_url, f"{API}/releases/assets/11")
        self.assertEqual(r.published_date, "2026-11-11")
        self.assertTrue(by_version["1.0.0.612"].prerelease)
        # Token sent as an unredirected header, never a normal (forwarded) one.
        _url, headers, unredirected = fake.requests[0]
        self.assertEqual(unredirected.get("Authorization"), "Bearer tok")
        self.assertNotIn("Authorization", headers)

    def test_follows_pagination(self):
        page2 = f"{API}/releases?per_page=100&page=2"
        fake = FakeGitHub({
            f"{API}/releases?per_page=100": (
                json.dumps([raw_release("1.0.0.694", asset_id=10)]).encode(),
                {"Link": f'<{page2}>; rel="next", <{page2}>; rel="last"'}),
            page2: [raw_release("0.1.0.6", asset_id=20)],
        })
        with mock.patch("urllib.request.urlopen", fake):
            versions = {r.version for r in gr.list_releases(REPO, TEMPLATE, None)}
        self.assertEqual(versions, {"1.0.0.694", "0.1.0.6"})

    def test_private_repo_without_token_says_how_to_sign_in(self):
        fake = FakeGitHub({f"{API}/releases?per_page=100": http_error(404)})
        with mock.patch("urllib.request.urlopen", fake):
            with self.assertRaises(gr.GitHubAccessError) as ctx:
                gr.list_releases(REPO, TEMPLATE, None)
        self.assertIn("private", str(ctx.exception))
        self.assertIn("gh auth login", str(ctx.exception))
        _url, headers, unredirected = fake.requests[0]
        self.assertNotIn("Authorization", {**headers, **unredirected})

    def test_denied_with_token(self):
        fake = FakeGitHub({f"{API}/releases?per_page=100": http_error(403)})
        with mock.patch("urllib.request.urlopen", fake):
            with self.assertRaises(gr.GitHubAccessError) as ctx:
                gr.list_releases(REPO, TEMPLATE, "tok")
        self.assertIn("denied", str(ctx.exception))

    def test_rate_limited(self):
        fake = FakeGitHub({f"{API}/releases?per_page=100":
                           http_error(403, {"X-RateLimit-Remaining": "0"})})
        with mock.patch("urllib.request.urlopen", fake):
            with self.assertRaises(gr.GitHubAccessError) as ctx:
                gr.list_releases(REPO, TEMPLATE, None)
        self.assertIn("rate limit", str(ctx.exception))

    def test_offline(self):
        fake = FakeGitHub({f"{API}/releases?per_page=100":
                           urllib.error.URLError("no route to host")})
        with mock.patch("urllib.request.urlopen", fake):
            with self.assertRaises(gr.GitHubAccessError) as ctx:
                gr.list_releases(REPO, TEMPLATE, None)
        self.assertIn("Could not reach GitHub", str(ctx.exception))


class TokenTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict("os.environ", {}, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        import os
        os.environ.pop("GH_TOKEN", None)
        os.environ.pop("GITHUB_TOKEN", None)
        gr.forget_token()
        self.addCleanup(gr.forget_token)

    def test_no_gh_means_unauthenticated(self):
        with mock.patch("shutil.which", return_value=None):
            self.assertIsNone(gr.get_token())

    def test_uses_gh_auth_token(self):
        done = subprocess.CompletedProcess(["gh"], 0, stdout="gho_abc123\n", stderr="")
        with mock.patch("shutil.which", return_value="gh.exe"), \
                mock.patch("subprocess.run", return_value=done) as run:
            self.assertEqual(gr.get_token(), "gho_abc123")
        self.assertEqual(run.call_args.args[0], ["gh.exe", "auth", "token"])

    def test_token_is_cached_in_memory_until_forgotten(self):
        done = subprocess.CompletedProcess(["gh"], 0, stdout="gho_abc123\n", stderr="")
        with mock.patch("shutil.which", return_value="gh.exe"), \
                mock.patch("subprocess.run", return_value=done) as run:
            gr.get_token()
            gr.get_token()
            self.assertEqual(run.call_count, 1)
            gr.forget_token()
            gr.get_token()
            self.assertEqual(run.call_count, 2)

    def test_gh_timeout_means_unauthenticated(self):
        with mock.patch("shutil.which", return_value="gh.exe"), \
                mock.patch("subprocess.run",
                           side_effect=subprocess.TimeoutExpired(["gh"], 45)):
            self.assertIsNone(gr.get_token())

    def test_gh_not_signed_in(self):
        done = subprocess.CompletedProcess(["gh"], 1, stdout="", stderr="not logged in")
        with mock.patch("shutil.which", return_value="gh.exe"), \
                mock.patch("subprocess.run", return_value=done):
            self.assertIsNone(gr.get_token())


class InstallReleaseTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.product_root = Path(self._tmp.name) / "library" / "rustrewrite"
        self.installs = self.product_root / "installs"
        self.installs.mkdir(parents=True)

    def _release(self, version="1.0.0.700") -> gr.ReleaseInfo:
        return gr.parse_release(raw_release(version, asset_id=10,
                                            body="## Fixed\r\n- Live data socket"), TEMPLATE)

    def _serve(self, zip_bytes: bytes, sums_hash: str | None = None,
               version: str = "1.0.0.700") -> FakeGitHub:
        digest = sums_hash or hashlib.sha256(zip_bytes).hexdigest()
        sums = f"{digest}  {TEMPLATE.format(version=version)}\n".encode()
        return FakeGitHub({
            f"{API}/releases/assets/10": zip_bytes,
            f"{API}/releases/assets/11": sums,
        })

    def test_downloads_verifies_and_extracts_backslash_zip(self):
        data = make_zip({
            "rexdesk.exe": b"MZ-rexdesk",
            "cli\\rexdesk-cli.exe": b"MZ-cli",
            "Help\\": b"",
            "Help\\ReXdeskManual.pdf": b"%PDF",
            "Firmware\\LPC\\image.bin": b"\x00\x01",
        })
        fake = self._serve(data)
        seen = []
        with mock.patch("urllib.request.urlopen", fake):
            dest = gr.install_release(self._release(), self.installs, "tok",
                                      product_name="Rust Rewrite",
                                      staging_parent=self.product_root,
                                      progress=lambda d, t: seen.append((d, t)))
        self.assertEqual(dest, self.installs / "1.0.0.700")
        self.assertEqual((dest / "rexdesk.exe").read_bytes(), b"MZ-rexdesk")
        self.assertEqual((dest / "cli" / "rexdesk-cli.exe").read_bytes(), b"MZ-cli")
        self.assertTrue((dest / "Help" / "ReXdeskManual.pdf").is_file())
        self.assertTrue((dest / "Firmware" / "LPC" / "image.bin").is_file())
        notes = (dest / "RELEASE_NOTES.txt").read_text(encoding="utf-8")
        self.assertIn("Rust Rewrite 1.0.0.700", notes)
        self.assertIn("Published 2026-11-11", notes)
        self.assertIn("## Fixed\n- Live data socket", notes)
        # No staging folder left behind, nothing extra in installs/.
        self.assertEqual([p.name for p in self.installs.iterdir()], ["1.0.0.700"])
        self.assertEqual(sorted(p.name for p in self.product_root.iterdir()), ["installs"])
        self.assertTrue(seen and seen[-1][0] == len(data))
        # Asset downloads ask for the binary, with the token unredirected.
        for _url, headers, unredirected in fake.requests:
            self.assertEqual(headers.get("Accept"), "application/octet-stream")
            self.assertEqual(unredirected.get("Authorization"), "Bearer tok")

    def test_single_top_level_folder_is_flattened(self):
        data = make_zip({
            "ReXdesk-Rust-1.0.0.700\\rexdesk.exe": b"MZ",
            "ReXdesk-Rust-1.0.0.700\\cli\\rexdesk-cli.exe": b"MZ",
        })
        with mock.patch("urllib.request.urlopen", self._serve(data)):
            dest = gr.install_release(self._release(), self.installs, None,
                                      staging_parent=self.product_root)
        self.assertTrue((dest / "rexdesk.exe").is_file())
        self.assertTrue((dest / "cli" / "rexdesk-cli.exe").is_file())

    def test_checksum_mismatch_installs_nothing(self):
        data = make_zip({"rexdesk.exe": b"MZ"})
        with mock.patch("urllib.request.urlopen", self._serve(data, sums_hash="0" * 64)):
            with self.assertRaises(gr.ChecksumError):
                gr.install_release(self._release(), self.installs, None,
                                   staging_parent=self.product_root)
        self.assertEqual(list(self.installs.iterdir()), [])
        self.assertEqual(sorted(p.name for p in self.product_root.iterdir()), ["installs"])

    def test_missing_sums_entry_installs_nothing(self):
        data = make_zip({"rexdesk.exe": b"MZ"})
        fake = FakeGitHub({
            f"{API}/releases/assets/10": data,
            f"{API}/releases/assets/11": f"{'a' * 64}  some-other.zip\n".encode(),
        })
        with mock.patch("urllib.request.urlopen", fake):
            with self.assertRaises(gr.ChecksumError):
                gr.install_release(self._release(), self.installs, None,
                                   staging_parent=self.product_root)
        self.assertEqual(list(self.installs.iterdir()), [])

    def test_zip_slip_is_refused(self):
        data = make_zip({"rexdesk.exe": b"MZ", "..\\..\\evil.txt": b"bad"})
        with mock.patch("urllib.request.urlopen", self._serve(data)):
            with self.assertRaises(ValueError):
                gr.install_release(self._release(), self.installs, None,
                                   staging_parent=self.product_root)
        self.assertEqual(list(self.installs.iterdir()), [])
        self.assertFalse((Path(self._tmp.name) / "evil.txt").exists())
        self.assertFalse((self.product_root / "evil.txt").exists())

    def test_existing_version_folder_is_not_overwritten(self):
        (self.installs / "1.0.0.700").mkdir()
        (self.installs / "1.0.0.700" / "rexdesk.exe").write_bytes(b"local build")
        with mock.patch("urllib.request.urlopen", self._serve(make_zip({"rexdesk.exe": b"MZ"}))):
            with self.assertRaises(FileExistsError):
                gr.install_release(self._release(), self.installs, None,
                                   staging_parent=self.product_root)
        self.assertEqual((self.installs / "1.0.0.700" / "rexdesk.exe").read_bytes(), b"local build")

    def test_parse_sha256sums_formats(self):
        h = "0B85B950E28D9DDDE3044E03B22C5F6E9068319CAF51917CCD98419DEF9A8FF9"
        sums = gr.parse_sha256sums(f"{h}  a.zip\r\n{h.lower()} *b.zip\n# comment\n")
        self.assertEqual(sums, {"a.zip": h.lower(), "b.zip": h.lower()})


class CatalogMergeTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.catalog = CatalogStore(Path(self._tmp.name) / "catalog.json")

    def _releases(self, *versions: str) -> list[gr.ReleaseInfo]:
        return [gr.parse_release(raw_release(v, asset_id=10), TEMPLATE) for v in versions]

    def test_adds_missing_as_available_and_keeps_installed(self):
        self.catalog.upsert(VersionRecord(version="1.0.0.694", status="installed",
                                          release_date="2026-11-12"))
        added, removed = gr.merge_releases(
            self.catalog, self._releases("1.0.0.694", "1.0.0.700", "0.1.0.6"))
        self.assertEqual(sorted(added), ["0.1.0.6", "1.0.0.700"])
        self.assertEqual(removed, [])
        self.assertEqual(self.catalog.get("1.0.0.694").status, "installed")
        self.assertEqual(self.catalog.get("1.0.0.694").release_date, "2026-11-12")
        new = self.catalog.get("1.0.0.700")
        self.assertEqual((new.status, new.release_date), ("available", "2026-11-11"))

    def test_drops_available_entries_whose_release_is_gone(self):
        self.catalog.upsert(VersionRecord(version="1.0.0.650", status="available"))
        self.catalog.upsert(VersionRecord(version="1.0.0.600", status="installed"))
        _added, removed = gr.merge_releases(self.catalog, self._releases("1.0.0.694"))
        self.assertEqual(removed, ["1.0.0.650"])
        self.assertIsNone(self.catalog.get("1.0.0.650"))
        self.assertIsNotNone(self.catalog.get("1.0.0.600"))


class SyncLocalBuildsTests(unittest.TestCase):
    """main._sync_local_builds must keep 'available' entries (no folder yet) and
    turn them into installed builds once their folder appears."""

    def setUp(self):
        import main  # Tk is imported but no window is created here.
        self.main = main
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        app_root = Path(self._tmp.name)
        with mock.patch.object(config, "_app_root", return_value=app_root):
            self.paths = config.resolve_paths("rustrewrite")
        config.ensure_layout(self.paths)
        app = object.__new__(main.RexdeskVersionManager)
        app.paths = self.paths
        app.product_def = config.PRODUCTS["rustrewrite"]
        app.catalog = CatalogStore(self.paths.catalog_path)
        app.selected_version = None
        app._show_detail = lambda show: None
        self.app = app

    def _add_folder(self, version: str) -> None:
        d = self.paths.installs_dir / version
        d.mkdir()
        (d / "rexdesk.exe").write_bytes(b"MZ")
        (d / "cli").mkdir()
        (d / "cli" / "rexdesk-cli.exe").write_bytes(b"MZ")

    def test_available_kept_then_promoted(self):
        self._add_folder("1.0.0.694")
        self.app.catalog.upsert(VersionRecord(version="1.0.0.700", status="available",
                                              release_date="2026-11-20"))
        self.app.catalog.upsert(VersionRecord(version="1.0.0.500", status="installed"))
        self.app._sync_local_builds()
        self.assertEqual(self.app.catalog.get("1.0.0.700").status, "available")
        self.assertEqual(self.app.catalog.get("1.0.0.694").status, "installed")
        self.assertTrue(self.app.catalog.get("1.0.0.694").exe_path.endswith("rexdesk.exe"))
        self.assertIsNone(self.app.catalog.get("1.0.0.500"))  # folder gone

        self._add_folder("1.0.0.700")
        self.app._sync_local_builds()
        rec = self.app.catalog.get("1.0.0.700")
        self.assertEqual(rec.status, "installed")
        self.assertEqual(rec.release_date, "2026-11-20")

    def test_products_wired_as_intended(self):
        self.assertEqual(config.PRODUCTS["rustrewrite"].github_repo, REPO)
        self.assertEqual(config.PRODUCTS["rustrewrite"].github_asset_template, TEMPLATE)
        for key in ("kcalrust", "rexbridgerust", "rexdesk", "rexbridge", "kcal"):
            self.assertEqual(config.PRODUCTS[key].github_repo, "", key)


class CheckForUpdatesGuiTests(unittest.TestCase):
    """Drives the real Tk window on a temp library: Check for Updates on Rust
    Rewrite lists a new GitHub release, Download installs it."""

    def setUp(self):
        import main
        import tkinter as tk
        self.main = main
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.app_root = Path(self._tmp.name)
        patches = [
            mock.patch.object(config, "_app_root", return_value=self.app_root),
            mock.patch.object(main.RexdeskVersionManager, "_check_live_version",
                              lambda self: None),
            mock.patch.object(main.messagebox, "showerror"),
            mock.patch.object(gr, "get_token", return_value="tok"),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        try:
            self.app = main.RexdeskVersionManager()
        except tk.TclError as exc:  # no display
            self.skipTest(f"Tk unavailable: {exc}")
        self.addCleanup(self.app.destroy)
        self.app.withdraw()
        self.app._show_toast = lambda *a, **k: None
        self.app._select_product("rustrewrite")
        installs = self.app.paths.installs_dir
        (installs / "1.0.0.694").mkdir()
        (installs / "1.0.0.694" / "rexdesk.exe").write_bytes(b"MZ")

    def _pump(self, until, timeout=10.0):
        """Run the real mainloop (worker threads can only post back to Tk while
        it runs) until *until()* is true."""
        import time
        end = time.time() + timeout
        timed_out = []

        def _poll():
            if until():
                self.app.quit()
            elif time.time() > end:
                timed_out.append(True)
                self.app.quit()
            else:
                self.app.after(20, _poll)

        self.app.after(20, _poll)
        self.app.mainloop()
        if timed_out:
            self.fail(f"timed out waiting for the GUI; status: {self.app.status_var.get()}")

    def test_check_then_download(self):
        zip_bytes = make_zip({"rexdesk.exe": b"MZ-new", "cli\\rexdesk-cli.exe": b"MZ"})
        sums = f"{hashlib.sha256(zip_bytes).hexdigest()}  {TEMPLATE.format(version='1.0.0.700')}\n"
        fake = FakeGitHub({
            f"{API}/releases?per_page=100": [
                raw_release("1.0.0.700", asset_id=10),
                raw_release("1.0.0.694", asset_id=20),
            ],
            f"{API}/releases/assets/10": zip_bytes,
            f"{API}/releases/assets/11": sums.encode(),
        })
        with mock.patch("urllib.request.urlopen", fake):
            # The folder dropped in after the product was opened shows up at once.
            self.app._check_for_updates()
            self.assertIn("1.0.0.694", self.app._version_order)
            self._pump(lambda: str(self.app._check_updates_btn["state"]) == "normal")
            self.assertEqual(self.app.catalog.get("1.0.0.700").status, "available")
            self.assertEqual(self.app.selected_version, "1.0.0.700")
            self.assertIn("New release on GitHub: 1.0.0.700", self.app.status_var.get())
            self.assertTrue(self.app.btn_download_available.winfo_manager())
            self.assertFalse(self.app.btn_launch.winfo_manager())

            self.app._download_available_selected()
            self._pump(lambda: "Downloaded and verified" in self.app.status_var.get()
                       or "failed" in self.app.status_var.get())
        self.main.messagebox.showerror.assert_not_called()
        rec = self.app.catalog.get("1.0.0.700")
        self.assertEqual(rec.status, "installed")
        self.assertTrue(Path(rec.exe_path).is_file())
        self.assertTrue(Path(rec.notes_path).is_file())
        self.assertTrue(self.app.btn_launch.winfo_manager())

        # A second check now reports up to date.
        with mock.patch("urllib.request.urlopen", fake):
            self.app._check_for_updates()
            self._pump(lambda: str(self.app._check_updates_btn["state"]) == "normal")
        self.assertIn("Up to date (1.0.0.700)", self.app.status_var.get())

    def test_access_denied_shows_status(self):
        fake = FakeGitHub({f"{API}/releases?per_page=100": http_error(404)})
        with mock.patch("urllib.request.urlopen", fake):
            self.app._check_for_updates()
            self._pump(lambda: str(self.app._check_updates_btn["state"]) == "normal")
        self.assertIn("denied access", self.app.status_var.get())
        self.assertEqual(self.app.catalog.get("1.0.0.694").status, "installed")


if __name__ == "__main__":
    unittest.main()
