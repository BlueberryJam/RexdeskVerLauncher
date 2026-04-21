from __future__ import annotations

import base64
import io
from dataclasses import replace
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from catalog import CatalogStore, VersionRecord
from config import (
    APP_NAME, DEFAULT_PRODUCT, PRODUCTS, PRODUCT_KEYS, ProductDef,
    assets_dir, ensure_layout, migrate_legacy_library, resolve_paths, safe_version_slug,
)
from logo_assets import load_product_logo
import msi_ops
from web_check import fetch_live_version

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD

    BaseTk = TkinterDnD.Tk
    DRAG_DROP_AVAILABLE = True
except ImportError:
    BaseTk = tk.Tk
    DND_FILES = "DND_Files"
    DRAG_DROP_AVAILABLE = False

ACCENT = "#0078D4"
BG_DARK = "#1e1e1e"
BG_MID = "#252526"
BG_LIGHT = "#2d2d2d"
FG = "#cccccc"
FG_BRIGHT = "#ffffff"
FG_DIM = "#888888"
BORDER = "#3c3c3c"
SELECT_BG = "#094771"
EDITOR_BG = "#1e1e1e"


MSI_ICON_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAYAAABzenr0AAAAAXNSR0IArs4c6QAAAJlJREFUWIXt"
    "ljEOgCAQRIf4/y/jCVhYWEisBRYaC42FBQkJCy7DLGR3k0koxZ/MzAIAAAAAAA"
    "AAwD8REVu0fUS8rl73fkAphBBCKPCb1l5Za/GGLdoYiVE5RkQAAP4OAIA/gLmIiG1Eaqqq"
    "p8ys6q5m5szciUh196OIHCIyVFXdfS8iazKzprtfIjJV1cxsE5F1jwcAAAAAAAAA4Gk+"
    "IjkrLijq6mIAAAAASUVORK5CYII="
)


def _load_msi_icon() -> tk.PhotoImage | None:
    try:
        data = base64.b64decode(MSI_ICON_B64)
        return tk.PhotoImage(data=data)
    except Exception:
        return None


class RexdeskVersionManager(BaseTk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_NAME)
        self.geometry("1100x720")
        self.minsize(900, 580)
        self.configure(bg=BG_DARK)

        self.current_product_key: str = DEFAULT_PRODUCT
        self.product_def: ProductDef = PRODUCTS[self.current_product_key]

        migrate_legacy_library(resolve_paths().library_root)

        self.paths = resolve_paths(self.current_product_key)
        ensure_layout(self.paths)
        self.catalog = CatalogStore(self.paths.catalog_path)
        self.selected_version: str | None = None
        self._live_website_version: str | None = None
        self._version_order: list[str] = []
        self._selected_list_idx: int | None = None
        self.msi_icon: tk.PhotoImage | None = None
        self._product_logo_photo: tk.PhotoImage | None = None
        self._autosave_patch_id: str | None = None
        self._autosave_bug_id: str | None = None
        self._autosave_date_id: str | None = None
        self._loading_notes = False

        self._apply_theme()
        self._build_ui()
        self._refresh_list()
        self._setup_drag_drop()
        self._check_live_version()

    def _apply_theme(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")

        style.configure(".", background=BG_MID, foreground=FG, borderwidth=0)
        style.configure("TFrame", background=BG_MID)
        style.configure("TLabel", background=BG_MID, foreground=FG)
        style.configure("TButton", background=BG_LIGHT, foreground=FG_BRIGHT,
                         padding=(10, 5), relief="flat")
        style.map("TButton",
                   background=[("active", ACCENT), ("pressed", ACCENT)],
                   foreground=[("active", FG_BRIGHT)])
        style.configure("Accent.TButton", background=ACCENT, foreground=FG_BRIGHT)
        style.map("Accent.TButton",
                   background=[("active", "#1a8ad4"), ("pressed", "#005a9e")])

        style.configure("TLabelframe", background=BG_MID, foreground=FG_DIM,
                         borderwidth=1, relief="solid")
        style.configure("TLabelframe.Label", background=BG_MID, foreground=FG_DIM)

        style.configure("Header.TLabel", background=BG_MID, foreground=FG_BRIGHT,
                         font=("Segoe UI", 16, "bold"))
        style.configure("Sub.TLabel", background=BG_MID, foreground=FG_DIM,
                         font=("Segoe UI", 9))
        style.configure("Section.TLabel", background=BG_MID, foreground=ACCENT,
                         font=("Segoe UI", 10, "bold"))
        style.configure("Drop.TLabel", background=BG_DARK, foreground=FG_DIM,
                         font=("Segoe UI", 9), borderwidth=2, relief="groove")
        style.configure("TCombobox", fieldbackground=BG_DARK, background=BG_LIGHT,
                         foreground=FG_BRIGHT, arrowcolor=FG_BRIGHT,
                         selectbackground=SELECT_BG, selectforeground=FG_BRIGHT)
        style.map("TCombobox",
                   fieldbackground=[("readonly", BG_DARK)],
                   foreground=[("readonly", FG_BRIGHT)],
                   selectbackground=[("readonly", SELECT_BG)],
                   selectforeground=[("readonly", FG_BRIGHT)])
        style.configure("ProductBar.TFrame", background=BG_LIGHT)

    def _build_ui(self) -> None:
        self.msi_icon = _load_msi_icon()

        # ---- product switcher bar ----
        product_bar = ttk.Frame(self, style="ProductBar.TFrame", padding=(12, 6))
        product_bar.pack(fill=tk.X)
        self._product_logo_label = tk.Label(
            product_bar, bg=BG_LIGHT, bd=0, highlightthickness=0,
        )
        self._product_logo_label.pack(side=tk.LEFT, padx=(0, 8))
        ttk.Label(product_bar, text="Product:", style="Section.TLabel",
                  background=BG_LIGHT).pack(side=tk.LEFT)
        self._product_names = [PRODUCTS[k].display_name for k in PRODUCT_KEYS]
        self._product_var = tk.StringVar(value=self.product_def.display_name)
        self._product_combo = ttk.Combobox(
            product_bar,
            textvariable=self._product_var,
            values=self._product_names,
            state="readonly",
            width=20,
            font=("Segoe UI", 10),
        )
        self._product_combo.pack(side=tk.LEFT, padx=(8, 0))
        self._product_combo.bind("<<ComboboxSelected>>", self._on_product_combo_changed)

        self._refresh_product_logo()

        bar_sep = tk.Frame(self, bg=BORDER, height=1)
        bar_sep.pack(fill=tk.X)

        outer = ttk.Frame(self)
        outer.pack(fill=tk.BOTH, expand=True)
        self._outer = outer

        # ---- left panel: version list ----
        left = ttk.Frame(outer, padding=(12, 12, 6, 12))
        left.pack(side=tk.LEFT, fill=tk.BOTH)
        self._left_panel = left
        left.pack_propagate(False)
        left.configure(width=280)

        ttk.Label(left, text="Versions", style="Header.TLabel").pack(anchor=tk.W)

        btn_row = ttk.Frame(left)
        btn_row.pack(fill=tk.X, pady=(8, 8))
        ttk.Button(btn_row, text="+ Add MSI", style="Accent.TButton",
                    command=self._choose_and_add_msi).pack(side=tk.LEFT, fill=tk.X, expand=True)

        list_frame = ttk.Frame(left)
        list_frame.pack(fill=tk.BOTH, expand=True)
        self._list_frame = list_frame

        self.version_list = tk.Text(
            list_frame,
            bg=BG_DARK, fg=FG_BRIGHT, borderwidth=0, highlightthickness=0,
            font=("Segoe UI", 11), cursor="arrow", state="disabled",
            wrap="none", takefocus=True, spacing1=3, spacing3=3,
        )
        self.version_list.tag_configure("installed", foreground=FG_BRIGHT)
        self.version_list.tag_configure("not_installed", foreground="#707070")
        self.version_list.tag_configure("conflict", foreground="#d4a056")
        self.version_list.tag_configure("install_failed", foreground="#cc6666")
        self.version_list.tag_configure("live", foreground=ACCENT)
        self.version_list.tag_configure("sel_line", background=SELECT_BG)
        self.version_list.tag_raise("sel_line")

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL,
                                   command=self.version_list.yview)
        self.version_list.configure(yscrollcommand=scrollbar.set)
        self.version_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.version_list.bind("<Button-1>", self._on_list_click)
        self.version_list.bind("<Double-Button-1>", lambda _e: "break")
        self.version_list.bind("<Up>", self._on_list_key_up)
        self.version_list.bind("<Down>", self._on_list_key_down)

        if DRAG_DROP_AVAILABLE:
            self.drop_label = ttk.Label(
                left, text="Drop .msi files here",
                style="Drop.TLabel", anchor=tk.CENTER, padding=10,
            )
            self.drop_label.pack(fill=tk.X, pady=(8, 0))
        else:
            self.drop_label = ttk.Button(
                left, text="Install drag-drop support",
                command=self._install_tkinterdnd2,
            )
            self.drop_label.pack(fill=tk.X, pady=(8, 0))

        sep = tk.Frame(outer, bg=BORDER, width=1)
        sep.pack(side=tk.LEFT, fill=tk.Y)

        # ---- right panel: details ----
        right = ttk.Frame(outer, padding=(12, 12, 12, 12))
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._right_panel = right

        self.detail_container = right

        # placeholder shown when nothing selected
        self.empty_label = ttk.Label(
            right, text="Select a version from the list",
            style="Sub.TLabel", anchor=tk.CENTER,
        )
        self.empty_label.pack(expand=True)

        self._build_detail_widgets(right)

    def _build_detail_widgets(self, parent: ttk.Frame) -> None:
        self.detail_frame = ttk.Frame(parent)

        # header row: version name + status
        header = ttk.Frame(self.detail_frame)
        header.pack(fill=tk.X)
        self.version_title = ttk.Label(header, text="", style="Header.TLabel")
        self.version_title.pack(side=tk.LEFT)
        self.status_badge = ttk.Label(header, text="", style="Sub.TLabel")
        self.status_badge.pack(side=tk.LEFT, padx=(12, 0))

        # Release date row
        date_row = ttk.Frame(self.detail_frame)
        date_row.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(date_row, text="Released:", style="Sub.TLabel").pack(side=tk.LEFT)
        self._release_date_var = tk.StringVar()
        self.release_date_entry = tk.Entry(
            date_row,
            textvariable=self._release_date_var,
            bg=EDITOR_BG, fg=FG_BRIGHT, insertbackground=FG_BRIGHT,
            selectbackground=SELECT_BG, borderwidth=0, highlightthickness=1,
            highlightcolor=ACCENT, highlightbackground=BORDER,
            font=("Segoe UI", 10), width=20,
        )
        self.release_date_entry.pack(side=tk.LEFT, padx=(8, 0))
        self.release_date_entry.bind("<KeyRelease>", self._on_release_date_key)

        # MSI action row
        msi_row = ttk.Frame(self.detail_frame)
        msi_row.pack(fill=tk.X, pady=(12, 0))

        if self.msi_icon:
            self.msi_btn = ttk.Button(msi_row, image=self.msi_icon,
                                       command=self._reveal_msi)
        else:
            self.msi_btn = ttk.Button(msi_row, text="MSI", width=5,
                                       command=self._reveal_msi)
        self.msi_btn.pack(side=tk.LEFT)

        ttk.Button(msi_row, text="Copy MSI Path",
                    command=self._copy_msi_path).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(msi_row, text="Export MSI",
                    command=self._export_msi).pack(side=tk.LEFT, padx=(8, 0))

        sep1 = tk.Frame(self.detail_frame, bg=BORDER, height=1)
        sep1.pack(fill=tk.X, pady=(14, 10))

        # ---- Patch Notes ----
        pn_header = ttk.Frame(self.detail_frame)
        pn_header.pack(fill=tk.X)
        ttk.Label(pn_header, text="Patch Notes", style="Section.TLabel").pack(side=tk.LEFT)
        ttk.Button(pn_header, text="Upload Patch Notes",
                   command=self._upload_patch_notes).pack(side=tk.RIGHT, padx=(0, 6))

        self.patch_notes_editor = tk.Text(
            self.detail_frame, wrap=tk.WORD, height=8,
            bg=EDITOR_BG, fg=FG_BRIGHT, insertbackground=FG_BRIGHT,
            selectbackground=SELECT_BG, borderwidth=0, highlightthickness=1,
            highlightcolor=ACCENT, highlightbackground=BORDER,
            font=("Consolas", 10),
        )
        self.patch_notes_editor.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        self.patch_notes_editor.bind("<<Modified>>", self._on_patch_notes_modified)

        sep2 = tk.Frame(self.detail_frame, bg=BORDER, height=1)
        sep2.pack(fill=tk.X, pady=(12, 10))

        # ---- Bugs & Notes ----
        bn_header = ttk.Frame(self.detail_frame)
        bn_header.pack(fill=tk.X)
        ttk.Label(bn_header, text="Bugs & Notes", style="Section.TLabel").pack(side=tk.LEFT)

        self.bug_notes_editor = tk.Text(
            self.detail_frame, wrap=tk.WORD, height=6,
            bg=EDITOR_BG, fg=FG_BRIGHT, insertbackground=FG_BRIGHT,
            selectbackground=SELECT_BG, borderwidth=0, highlightthickness=1,
            highlightcolor=ACCENT, highlightbackground=BORDER,
            font=("Consolas", 10),
        )
        self.bug_notes_editor.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        self.bug_notes_editor.bind("<<Modified>>", self._on_bug_notes_modified)

        sep3 = tk.Frame(self.detail_frame, bg=BORDER, height=1)
        sep3.pack(fill=tk.X, pady=(12, 10))

        # ---- Actions ----
        self.actions_frame = ttk.Frame(self.detail_frame)
        self.actions_frame.pack(fill=tk.X)

        # Not-installed set
        self.btn_install = ttk.Button(self.actions_frame, text="Install",
                                      style="Accent.TButton", command=self._install_selected)
        self.btn_open_msi_folder = ttk.Button(self.actions_frame, text="Open Folder Location",
                                              command=self._open_msi_folder)
        self.btn_remove = ttk.Button(self.actions_frame, text="Remove Version",
                                     command=self._remove_selected)

        # Installed set
        self.btn_launch = ttk.Button(self.actions_frame, text="Launch",
                                     style="Accent.TButton", command=self._launch_selected)
        self.btn_uninstall = ttk.Button(self.actions_frame, text="Uninstall",
                                        command=self._uninstall_selected)
        self.btn_reinstall = ttk.Button(self.actions_frame, text="Reinstall",
                                        command=self._reinstall_selected)
        self.btn_open_folder = ttk.Button(self.actions_frame, text="Open in Folder",
                                          command=self._open_install_folder)

        # status bar
        self.status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(self.detail_frame, textvariable=self.status_var,
                                style="Sub.TLabel")
        status_bar.pack(fill=tk.X, pady=(10, 0))

    # ------------------------------------------------------------------ product switching
    def _on_product_combo_changed(self, _event: object) -> None:
        display_name = self._product_var.get()
        for k in PRODUCT_KEYS:
            if PRODUCTS[k].display_name == display_name:
                self._select_product(k)
                return

    def _select_product(self, new_key: str) -> None:
        if new_key == self.current_product_key:
            return
        self.current_product_key = new_key
        self.product_def = PRODUCTS[new_key]
        self._product_var.set(self.product_def.display_name)
        self.paths = resolve_paths(new_key)
        ensure_layout(self.paths)
        self.catalog = CatalogStore(self.paths.catalog_path)
        self.selected_version = None
        self._live_website_version = None
        self._show_detail(False)
        self._refresh_list()
        self.title(f"{APP_NAME}  —  {self.product_def.display_name}")
        self._set_status(f"Switched to {self.product_def.display_name}")
        self._refresh_product_logo()
        self._check_live_version()

    def _refresh_product_logo(self) -> None:
        self._product_logo_photo = load_product_logo(
            self,
            self.product_def.logo_svg,
            assets_dir(),
            max_height=40,
            max_width=280,
        )
        if self._product_logo_photo:
            self._product_logo_label.configure(image=self._product_logo_photo)
        else:
            self._product_logo_label.configure(image="")

    # ------------------------------------------------------------------ live version check
    def _check_live_version(self) -> None:
        """Fetch the live version from the website in a background thread."""
        url = self.product_def.download_page_url
        if not url:
            self._live_website_version = None
            return

        def _do_check(page_url: str, product_key: str) -> None:
            version = fetch_live_version(page_url)
            self.after(0, lambda: self._on_live_version_result(version, product_key))

        threading.Thread(
            target=_do_check, args=(url, self.current_product_key), daemon=True,
        ).start()

    def _on_live_version_result(self, version: str | None, product_key: str) -> None:
        if product_key != self.current_product_key:
            return
        self._live_website_version = version
        self._refresh_list()

    # ------------------------------------------------------------------ helpers
    def _update_action_buttons(self, record: "VersionRecord") -> None:
        """Show the correct set of action buttons depending on install state."""
        all_btns = (
            self.btn_install, self.btn_open_msi_folder, self.btn_remove,
            self.btn_launch, self.btn_uninstall, self.btn_reinstall, self.btn_open_folder,
        )
        for btn in all_btns:
            btn.pack_forget()

        if record.status == "installed":
            self.btn_launch.pack(side=tk.LEFT, padx=(0, 6))
            self.btn_uninstall.pack(side=tk.LEFT, padx=(0, 6))
            self.btn_reinstall.pack(side=tk.LEFT, padx=(0, 6))
            self.btn_open_folder.pack(side=tk.LEFT)
        else:
            self.btn_install.pack(side=tk.LEFT, padx=(0, 6))
            self.btn_open_msi_folder.pack(side=tk.LEFT, padx=(0, 6))
            self.btn_remove.pack(side=tk.LEFT)

    def _show_detail(self, show: bool) -> None:
        if show:
            self.empty_label.pack_forget()
            self.detail_frame.pack(fill=tk.BOTH, expand=True)
        else:
            self.detail_frame.pack_forget()
            self.empty_label.pack(expand=True)

    def _set_status(self, text: str) -> None:
        self.status_var.set(text)

    # ------------------------------------------------------------------ drag-drop
    def _install_tkinterdnd2(self) -> None:
        import shutil
        # When frozen by PyInstaller, sys.executable is the .exe — find real python
        if getattr(sys, "frozen", False):
            python = shutil.which("python") or shutil.which("python3")
            if python is None:
                messagebox.showerror(
                    "Install failed",
                    "Could not find Python. Try running: pip install tkinterdnd2",
                )
                return
        else:
            python = sys.executable

        self.drop_label.configure(state="disabled", text="Installing…")
        self.update_idletasks()
        try:
            subprocess.check_call(
                [python, "-m", "pip", "install", "tkinterdnd2"],
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            messagebox.showinfo(
                "Installed",
                "tkinterdnd2 installed successfully.\nRebuild the app using build.bat to enable drag-drop.",
            )
        except subprocess.CalledProcessError:
            messagebox.showerror(
                "Install failed",
                "Could not install tkinterdnd2.\nTry running: pip install tkinterdnd2",
            )
            self.drop_label.configure(state="normal", text="Install drag-drop support")

    def _setup_drag_drop(self) -> None:
        if not DRAG_DROP_AVAILABLE:
            return
        _drop_targets = [
            self, self._outer, self._left_panel, self._list_frame, self._right_panel,
            self.drop_label, self.version_list, self.empty_label,
            self.detail_frame, self.patch_notes_editor, self.bug_notes_editor,
            self.release_date_entry,
        ]
        for w in _drop_targets:
            w.drop_target_register(DND_FILES)
            w.dnd_bind("<<Drop>>", self._on_drop_files)
            w.dnd_bind("<<DragEnter>>", lambda _e: self._set_status("Drop to add MSI"))
            w.dnd_bind("<<DragLeave>>", lambda _e: self._set_status("Ready"))

    def _parse_drop_paths(self, raw_data: str) -> list[Path]:
        parsed = self.tk.splitlist(raw_data)
        return [Path(item) for item in parsed if item]

    def _on_drop_files(self, event) -> None:  # type: ignore[no-untyped-def]
        files = self._parse_drop_paths(event.data)
        msi_files = [p for p in files if p.suffix.lower() == ".msi"]
        if not msi_files:
            messagebox.showwarning(APP_NAME, "Only .msi files can be added.")
            return
        added = 0
        for msi_file in msi_files:
            if self._add_version_from_msi(msi_file):
                added += 1
        self._refresh_list()
        self._set_status(f"Imported {added} MSI file(s)")

    # ------------------------------------------------------------------ catalog recovery
    def _recover_catalog_from_disk(self) -> None:
        """If the catalog is empty but MSI files exist on disk, rebuild entries."""
        if self.catalog.all_versions():
            return
        msi_files = sorted(self.paths.msi_dir.glob("*.msi"))
        if not msi_files:
            return
        for msi_file in msi_files:
            version = msi_ops.infer_version_label(msi_file)
            slug = safe_version_slug(version)
            notes_path = msi_file.parent / f"{msi_file.stem}_notes.txt"
            bug_path = self.paths.bug_notes_dir / f"{slug}.txt"
            install_dir = self.paths.installs_dir / slug

            status = "not_installed"
            install_path = ""
            exe_path = ""
            if install_dir.exists():
                exe = self._guess_executable(install_dir)
                if exe:
                    status = "installed"
                    install_path = str(install_dir)
                    exe_path = str(exe)

            self.catalog.upsert(VersionRecord(
                version=version,
                status=status,
                install_path=install_path,
                exe_path=exe_path,
                msi_path=str(msi_file),
                notes_path=str(notes_path) if notes_path.exists() else "",
                bug_notes_path=str(bug_path) if bug_path.exists() else "",
            ))

    # ------------------------------------------------------------------ list
    def _prune_missing_msi(self) -> None:
        """Remove catalog entries whose MSI file has been deleted from disk."""
        to_remove = [
            r.version for r in self.catalog.all_versions()
            if r.msi_path and not Path(r.msi_path).exists()
        ]
        for version in to_remove:
            if self.selected_version == version:
                self.selected_version = None
                self._show_detail(False)
            self.catalog.remove(version)

    def _prune_missing_installs(self) -> None:
        """Reset status to not_installed when the install folder has been removed."""
        for record in self.catalog.all_versions():
            if record.status == "installed" and record.install_path and not Path(record.install_path).exists():
                updated = replace(record, status="not_installed",
                                  install_path="", exe_path="", last_error="")
                self.catalog.upsert(updated)

    def _recover_existing_installs(self) -> None:
        """If a version has files on disk but is not marked installed, fix the catalog."""
        for record in self.catalog.all_versions():
            if record.status == "installed":
                continue
            slug = safe_version_slug(record.version)
            install_dir = self.paths.installs_dir / slug
            if not install_dir.exists():
                continue
            exe = self._guess_executable(install_dir)
            if not exe:
                continue
            updated = replace(record, status="installed",
                              install_path=str(install_dir),
                              exe_path=str(exe),
                              coexistence_conflict=False, last_error="")
            self.catalog.upsert(updated)

    def _is_live_version(self, version: str) -> bool:
        """Check whether *version* matches the live website version."""
        live = self._live_website_version
        if not live:
            return False
        return version == live or version.startswith(live) or live.startswith(version)

    def _refresh_list(self) -> None:
        self._recover_catalog_from_disk()
        self._prune_missing_msi()
        self._prune_missing_installs()
        self._recover_existing_installs()

        self._version_order = []
        self.version_list.configure(state="normal")
        self.version_list.delete("1.0", tk.END)

        for idx, record in enumerate(self.catalog.all_versions()):
            if idx > 0:
                self.version_list.insert(tk.END, "\n")

            status_tag = {
                "installed": "installed",
                "conflict": "conflict",
                "install_failed": "install_failed",
            }.get(record.status, "not_installed")

            prefix = "  !   " if record.status in ("conflict", "install_failed") else "  "
            self.version_list.insert(tk.END, f"{prefix}{record.version}", status_tag)

            if self._is_live_version(record.version):
                self.version_list.insert(tk.END, "  - Live", "live")

            self._version_order.append(record.version)

        self.version_list.configure(state="disabled")

        if self.selected_version and self.selected_version in self._version_order:
            idx = self._version_order.index(self.selected_version)
            self._select_list_line(idx)
        else:
            self._selected_list_idx = None

    # ---- list interaction helpers ----
    def _select_list_line(self, idx: int) -> None:
        self.version_list.tag_remove("sel_line", "1.0", tk.END)
        if 0 <= idx < len(self._version_order):
            self._selected_list_idx = idx
            self.version_list.tag_add("sel_line", f"{idx + 1}.0", f"{idx + 2}.0")
            self.version_list.see(f"{idx + 1}.0")
        else:
            self._selected_list_idx = None

    def _on_list_click(self, event: object) -> str:
        idx_str = self.version_list.index(f"@{event.x},{event.y}")  # type: ignore[union-attr]
        line = int(idx_str.split(".")[0]) - 1
        if 0 <= line < len(self._version_order):
            self.version_list.focus_set()
            self._select_list_line(line)
            self._on_select_version(event)
        return "break"

    def _on_list_key_up(self, _event: object) -> str:
        if self._selected_list_idx is not None and self._selected_list_idx > 0:
            self._select_list_line(self._selected_list_idx - 1)
            self._on_select_version(_event)
        return "break"

    def _on_list_key_down(self, _event: object) -> str:
        if self._selected_list_idx is not None and self._selected_list_idx < len(self._version_order) - 1:
            self._select_list_line(self._selected_list_idx + 1)
            self._on_select_version(_event)
        return "break"

    # ------------------------------------------------------------------ selection
    def _on_select_version(self, _event: object) -> None:
        if self._selected_list_idx is None or self._selected_list_idx >= len(self._version_order):
            self.selected_version = None
            self._show_detail(False)
            return

        self.selected_version = self._version_order[self._selected_list_idx]
        record = self.catalog.get(self.selected_version)
        if not record:
            self._show_detail(False)
            return

        self._show_detail(True)
        self.version_title.configure(text=record.version)

        status_text = {
            "installed": "Installed",
            "not_installed": "Not installed",
            "conflict": "Conflict",
            "install_failed": "Install failed",
        }.get(record.status, record.status)
        self.status_badge.configure(text=f"({status_text})")

        self._loading_notes = True
        self._release_date_var.set(record.release_date or "")

        self.patch_notes_editor.delete("1.0", tk.END)
        notes_path = Path(record.notes_path) if record.notes_path else None
        if notes_path and notes_path.exists():
            self.patch_notes_editor.insert("1.0", notes_path.read_text(encoding="utf-8"))
        self.patch_notes_editor.edit_modified(False)

        self.bug_notes_editor.delete("1.0", tk.END)
        bug_path = Path(record.bug_notes_path) if record.bug_notes_path else None
        if bug_path and bug_path.exists():
            self.bug_notes_editor.insert("1.0", bug_path.read_text(encoding="utf-8"))
        self.bug_notes_editor.edit_modified(False)
        self._loading_notes = False

        self._update_action_buttons(record)
        self._set_status(f"Selected {record.version}")

    def _get_selected_record(self) -> VersionRecord | None:
        if not self.selected_version:
            messagebox.showinfo(APP_NAME, "Select a version first.")
            return None
        record = self.catalog.get(self.selected_version)
        if not record:
            messagebox.showerror(APP_NAME, "Version no longer in catalog.")
            return None
        return record

    # ------------------------------------------------------------------ add MSI
    def _choose_and_add_msi(self) -> None:
        picked = filedialog.askopenfilenames(
            title="Select MSI file(s)",
            filetypes=[("MSI files", "*.msi"), ("All files", "*.*")],
        )
        if not picked:
            return
        for path_str in picked:
            self._add_version_from_msi(Path(path_str))
        self._refresh_list()

    def _add_version_from_msi(self, source_msi: Path) -> bool:
        if not source_msi.exists():
            messagebox.showerror(APP_NAME, f"File not found:\n{source_msi}")
            return False

        detected_key = msi_ops.detect_msi_product_key(source_msi)
        if detected_key is None:
            messagebox.showerror(
                APP_NAME,
                f"Unrecognised MSI:\n{source_msi.name}\n\n"
                "Only Rexdesk and Rexbridge installers are supported.",
            )
            return False

        if detected_key != self.current_product_key:
            self._select_product(detected_key)

        suggested = msi_ops.infer_version_label(source_msi)
        version = simpledialog.askstring(
            APP_NAME,
            f"Version label for:\n{source_msi.name}",
            initialvalue=suggested,
            parent=self,
        )
        if version is None:
            return False
        version = version.strip()
        if not version:
            messagebox.showwarning(APP_NAME, "Version cannot be empty.")
            return False

        existing = self.catalog.get(version)
        if existing:
            if not messagebox.askyesno(
                APP_NAME,
                f"Version \"{version}\" already exists.\n\n"
                "Do you want to replace it?",
                icon="warning",
            ):
                return False

        msi_path = msi_ops.copy_msi_to_store(source_msi, self.paths.msi_dir, version)
        notes_path = msi_ops.ensure_patch_notes_file_beside_msi(msi_path)
        bug_path = msi_ops.ensure_bug_notes_file(self.paths.bug_notes_dir, version)

        if existing:
            updated = replace(existing, msi_path=str(msi_path),
                              notes_path=str(notes_path), bug_notes_path=str(bug_path))
        else:
            updated = VersionRecord(
                version=version, msi_path=str(msi_path),
                notes_path=str(notes_path), bug_notes_path=str(bug_path),
            )
        self.catalog.upsert(updated)
        self._set_status(f"{'Replaced' if existing else 'Added'} {version}")
        return True

    # ------------------------------------------------------------------ auto-save
    def _on_patch_notes_modified(self, _event: object = None) -> None:
        if self.patch_notes_editor.edit_modified():
            self.patch_notes_editor.edit_modified(False)
            if not self._loading_notes:
                self._schedule_autosave_patch()

    def _on_bug_notes_modified(self, _event: object = None) -> None:
        if self.bug_notes_editor.edit_modified():
            self.bug_notes_editor.edit_modified(False)
            if not self._loading_notes:
                self._schedule_autosave_bug()

    def _on_release_date_key(self, _event: object = None) -> None:
        if not self._loading_notes:
            self._schedule_autosave_date()

    def _schedule_autosave_patch(self) -> None:
        if self._autosave_patch_id is not None:
            self.after_cancel(self._autosave_patch_id)
        self._autosave_patch_id = self.after(500, lambda: self._save_patch_notes(quiet=True))

    def _schedule_autosave_bug(self) -> None:
        if self._autosave_bug_id is not None:
            self.after_cancel(self._autosave_bug_id)
        self._autosave_bug_id = self.after(500, lambda: self._save_bug_notes(quiet=True))

    def _schedule_autosave_date(self) -> None:
        if self._autosave_date_id is not None:
            self.after_cancel(self._autosave_date_id)
        self._autosave_date_id = self.after(500, self._save_release_date)

    def _save_release_date(self) -> None:
        self._autosave_date_id = None
        if not self.selected_version:
            return
        record = self.catalog.get(self.selected_version)
        if not record:
            return
        new_date = self._release_date_var.get().strip()
        if new_date != (record.release_date or ""):
            updated = replace(record, release_date=new_date)
            self.catalog.upsert(updated)
            self._set_status(f"Auto-saved release date for {record.version}")

    # ------------------------------------------------------------------ save notes
    def _save_patch_notes(self, *, quiet: bool = False) -> None:
        self._autosave_patch_id = None
        if quiet:
            if not self.selected_version:
                return
            record = self.catalog.get(self.selected_version)
            if not record:
                return
        else:
            record = self._get_selected_record()
            if not record:
                return
        notes_path = Path(record.notes_path) if record.notes_path else None
        if not notes_path:
            msi_path = Path(record.msi_path) if record.msi_path else None
            if msi_path and msi_path.exists():
                notes_path = msi_ops.ensure_patch_notes_file_beside_msi(msi_path)
            else:
                notes_path = msi_ops.ensure_patch_notes_file(
                    self.paths.patch_notes_dir, record.version)
            record = replace(record, notes_path=str(notes_path))

        text = self.patch_notes_editor.get("1.0", tk.END).rstrip()
        notes_path.write_text(f"{text}\n" if text else "", encoding="utf-8")
        self.catalog.upsert(record)
        if quiet:
            self._set_status(f"Auto-saved patch notes for {record.version}")
        else:
            self._set_status(f"Saved patch notes for {record.version}")

    def _save_bug_notes(self, *, quiet: bool = False) -> None:
        self._autosave_bug_id = None
        if quiet:
            if not self.selected_version:
                return
            record = self.catalog.get(self.selected_version)
            if not record:
                return
        else:
            record = self._get_selected_record()
            if not record:
                return
        bug_path = Path(record.bug_notes_path) if record.bug_notes_path else None
        if not bug_path:
            bug_path = msi_ops.ensure_bug_notes_file(
                self.paths.bug_notes_dir, record.version)
            record = replace(record, bug_notes_path=str(bug_path))

        text = self.bug_notes_editor.get("1.0", tk.END).rstrip()
        bug_path.write_text(f"{text}\n" if text else "", encoding="utf-8")
        self.catalog.upsert(record)
        if quiet:
            self._set_status(f"Auto-saved bugs & notes for {record.version}")
        else:
            self._set_status(f"Saved bugs & notes for {record.version}")

    def _upload_patch_notes(self) -> None:
        if not self.selected_version:
            messagebox.showinfo(APP_NAME, "Select a version first.")
            return
        _BLANK_TEMPLATE = (
            "## What's New\n"
            "- \n\n"
            "## Bug Fixes\n"
            "- \n\n"
            "## Known Issues\n"
            "- \n"
        )
        current = self.patch_notes_editor.get("1.0", tk.END).strip()
        if current:
            if not messagebox.askyesno(
                APP_NAME,
                "Replace the current patch notes with a blank template?\n\n"
                "You can still type and edit freely after loading it.",
            ):
                return
        self._loading_notes = True
        self.patch_notes_editor.delete("1.0", tk.END)
        self.patch_notes_editor.insert("1.0", _BLANK_TEMPLATE)
        self.patch_notes_editor.edit_modified(False)
        self._loading_notes = False
        self._set_status("Blank patch notes template loaded — edit and Save when ready")

    # ------------------------------------------------------------------ MSI actions
    def _reveal_msi(self) -> None:
        record = self._get_selected_record()
        if not record:
            return
        msi_path = Path(record.msi_path)
        if not msi_path.exists():
            messagebox.showwarning(APP_NAME, "MSI file no longer exists.")
            return
        msi_ops.open_in_explorer(msi_path)

    def _copy_msi_path(self) -> None:
        record = self._get_selected_record()
        if not record:
            return
        self.clipboard_clear()
        self.clipboard_append(record.msi_path)
        self._set_status("Copied MSI path to clipboard")

    def _export_msi(self) -> None:
        record = self._get_selected_record()
        if not record:
            return
        msi_path = Path(record.msi_path)
        if not msi_path.exists():
            messagebox.showwarning(APP_NAME, "MSI file no longer exists.")
            return
        destination = filedialog.askdirectory(title="Choose export folder")
        if not destination:
            return
        exported = msi_ops.export_msi_copy(msi_path, Path(destination))
        self._set_status(f"Exported MSI to {exported}")

    # ------------------------------------------------------------------ install/launch
    def _guess_executable(self, install_dir: Path) -> Path | None:
        if not install_dir.exists():
            return None
        candidates = list(install_dir.rglob("*.exe"))
        if not candidates:
            return None
        hint = self.product_def.exe_hint.lower()
        return sorted(
            candidates,
            key=lambda p: ((hint not in p.name.lower()), len(p.parts), p.name.lower()),
        )[0]

    def _collect_shelter_targets(self, exclude_version: str) -> list[tuple[Path, Path]]:
        """Build (install_dir, backup_dir) pairs for every *other* version that
        has files on disk, so their files survive msiexec's RemoveExistingProducts."""
        targets: list[tuple[Path, Path]] = []
        for r in self.catalog.all_versions():
            if r.version == exclude_version:
                continue
            slug = safe_version_slug(r.version)
            install_dir = Path(r.install_path) if r.install_path else self.paths.installs_dir / slug
            if not install_dir.exists():
                continue
            backup_dir = self.paths.backup_dir / slug
            targets.append((install_dir, backup_dir))
        return targets

    def _install_selected(self, *, _after_uninstall: bool = False) -> None:
        record = self._get_selected_record()
        if not record:
            return
        msi_path = Path(record.msi_path)
        if not msi_path.exists():
            messagebox.showerror(APP_NAME, f"MSI not found:\n{msi_path}")
            return

        slug = safe_version_slug(record.version)
        install_dir = self.paths.installs_dir / slug
        log_path = self.paths.product_root / f"install_{slug}.log"
        shelter_targets = self._collect_shelter_targets(record.version)

        registered_product_code = msi_ops.find_registered_product_code(msi_path)

        self._set_status(f"Installing {record.version}…  (do not close)")
        self.update_idletasks()

        def _do_install() -> None:
            sheltered: list[tuple[Path, Path]] = []
            install_rc: int | None = None
            try:
                sheltered = msi_ops.shelter_install_dirs(shelter_targets)

                if registered_product_code:
                    unreg_log = self.paths.product_root / f"uninstall_prev.log"
                    unreg_result = msi_ops.uninstall_product_code(registered_product_code, unreg_log)
                    if unreg_result.returncode not in (0, 1605):
                        self.after(0, lambda: (
                            self._set_status("Install failed: could not unregister current version"),
                            messagebox.showwarning(
                                APP_NAME,
                                f"Could not uninstall currently registered product "
                                f"(exit {unreg_result.returncode}).\n"
                                f"Log: {unreg_log}",
                            ),
                        ))
                        return

                result = msi_ops.install_with_msiexec(msi_path, install_dir, log_path)
                install_rc = result.returncode
            except Exception as exc:
                self.after(0, lambda e=exc: (
                    self._set_status("Install error"),
                    messagebox.showerror(APP_NAME, f"Install error:\n{e}"),
                ))
            finally:
                msi_ops.unshelter_install_dirs(sheltered)

            if install_rc is not None:
                self.after(0, lambda: self._on_install_done(record, install_dir, log_path, install_rc))

        threading.Thread(target=_do_install, daemon=True).start()

    def _on_install_done(self, record: "VersionRecord", install_dir: Path, log_path: Path, returncode: int) -> None:
        if returncode == 0:
            exe = self._guess_executable(install_dir)
            updated = replace(record, status="installed", install_path=str(install_dir),
                              exe_path=str(exe) if exe else record.exe_path,
                              coexistence_conflict=False, last_error="")
            self.catalog.upsert(updated)
            self._refresh_list()
            self._on_select_version(None)
            self._set_status(f"Installed {record.version}")
            return

        conflict = returncode in {1638, 1603}
        updated = replace(record,
                          status="conflict" if conflict else "install_failed",
                          coexistence_conflict=conflict,
                          last_error=f"msiexec exit code {returncode}")
        self.catalog.upsert(updated)
        self._refresh_list()
        self._on_select_version(None)
        messagebox.showwarning(APP_NAME, (
            f"Install failed for {record.version}.\n"
            f"Exit code: {returncode}\nLog: {log_path}\n"
            "MSI remains archived for reinstall later."
        ))

    def _uninstall_selected(self) -> None:
        record = self._get_selected_record()
        if not record:
            return
        msi_path = Path(record.msi_path)
        if not msi_path.exists():
            messagebox.showerror(APP_NAME, f"MSI not found:\n{msi_path}")
            return
        slug = safe_version_slug(record.version)
        log_path = self.paths.product_root / f"uninstall_{slug}.log"
        self._set_status(f"Uninstalling {record.version}…  (do not close)")
        self.update_idletasks()

        def _do_uninstall() -> None:
            try:
                result = msi_ops.uninstall_with_msiexec(msi_path, log_path)
                self.after(0, lambda: self._on_uninstall_done(record, log_path, result.returncode))
            except OSError:
                self.after(0, lambda: self._on_uninstall_cancelled(record))

        threading.Thread(target=_do_uninstall, daemon=True).start()

    def _on_uninstall_done(self, record: "VersionRecord", log_path: Path, returncode: int) -> None:
        if returncode == 0 or returncode == 1605:
            updated = replace(record, status="not_installed",
                              install_path="", exe_path="", last_error="")
            self.catalog.upsert(updated)
            install_dir = Path(record.install_path) if record.install_path else None
            if install_dir and install_dir.exists():
                shutil.rmtree(install_dir, ignore_errors=True)
            self._refresh_list()
            self._on_select_version(None)
            self._set_status(f"Uninstalled {record.version}; MSI kept")
            return
        messagebox.showwarning(APP_NAME,
                               f"Uninstall failed (exit {returncode}).\nLog: {log_path}")
        self._set_status("")

    def _on_uninstall_cancelled(self, record: "VersionRecord") -> None:
        self._set_status("")
        messagebox.showinfo(APP_NAME,
                            f"Uninstall of {record.version} was cancelled.")

    def _reinstall_selected(self) -> None:
        record = self._get_selected_record()
        if not record:
            return
        msi_path = Path(record.msi_path)
        if not msi_path.exists():
            messagebox.showerror(APP_NAME, f"MSI not found:\n{msi_path}")
            return

        slug = safe_version_slug(record.version)
        install_dir = self.paths.installs_dir / slug
        uninstall_log = self.paths.product_root / f"uninstall_{slug}.log"
        install_log = self.paths.product_root / f"install_{slug}.log"
        shelter_targets = self._collect_shelter_targets(record.version)

        self._set_status(f"Reinstalling {record.version}…  (do not close)")
        self.update_idletasks()

        def _do_reinstall() -> None:
            sheltered: list[tuple[Path, Path]] = []
            install_rc: int | None = None
            try:
                sheltered = msi_ops.shelter_install_dirs(shelter_targets)
                un_result = msi_ops.uninstall_with_msiexec(msi_path, uninstall_log)
                if un_result.returncode != 0:
                    self.after(0, lambda: (
                        self._set_status("Reinstall failed during uninstall"),
                        messagebox.showwarning(
                            APP_NAME,
                            f"Uninstall step failed (exit {un_result.returncode}).\n"
                            f"Log: {uninstall_log}",
                        ),
                    ))
                    return
                result = msi_ops.install_with_msiexec(msi_path, install_dir, install_log)
                install_rc = result.returncode
            except Exception as exc:
                self.after(0, lambda e=exc: (
                    self._set_status("Reinstall error"),
                    messagebox.showerror(APP_NAME, f"Reinstall error:\n{e}"),
                ))
            finally:
                msi_ops.unshelter_install_dirs(sheltered)

            if install_rc is not None:
                self.after(0, lambda: self._on_install_done(record, install_dir, install_log, install_rc))

        threading.Thread(target=_do_reinstall, daemon=True).start()

    def _launch_selected(self) -> None:
        record = self._get_selected_record()
        if not record:
            return
        exe_path = Path(record.exe_path) if record.exe_path else None
        if not exe_path or not exe_path.exists():
            install_dir = Path(record.install_path) if record.install_path else None
            if not install_dir:
                messagebox.showwarning(APP_NAME, "Version is not installed.")
                return
            exe_path = self._guess_executable(install_dir)
            if not exe_path:
                messagebox.showwarning(APP_NAME, "No executable found in install folder.")
                return
            self.catalog.upsert(replace(record, exe_path=str(exe_path)))
        msi_ops.launch_executable(exe_path)
        self._set_status(f"Launched {record.version}")

    def _open_msi_folder(self) -> None:
        record = self._get_selected_record()
        if not record:
            return
        msi_path = Path(record.msi_path) if record.msi_path else None
        if not msi_path or not msi_path.exists():
            messagebox.showwarning(APP_NAME, "MSI file no longer exists.")
            return
        msi_ops.open_folder(msi_path.parent)

    def _open_install_folder(self) -> None:
        record = self._get_selected_record()
        if not record:
            return
        if not record.install_path:
            messagebox.showwarning(APP_NAME, "No install path recorded.")
            return
        msi_ops.open_folder(Path(record.install_path))

    def _remove_selected(self) -> None:
        record = self._get_selected_record()
        if not record:
            return
        confirmed = messagebox.askyesno(
            APP_NAME,
            f"Remove version {record.version}?\n\n"
            "This will delete the stored MSI file and remove it from the list.\n"
            "Any installed copy will NOT be uninstalled.",
            icon="warning",
        )
        if not confirmed:
            return
        msi_path = Path(record.msi_path) if record.msi_path else None
        if msi_path and msi_path.exists():
            try:
                msi_path.unlink()
            except OSError as exc:
                messagebox.showerror(APP_NAME, f"Could not delete MSI file:\n{exc}")
                return
        self.catalog.remove(record.version)
        self.selected_version = None
        self._show_detail(False)
        self._refresh_list()
        self._set_status(f"Removed {record.version}")


def _enable_dpi_awareness() -> None:
    """Tell Windows to use per-monitor DPI so Tkinter isn't bitmap-scaled."""
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass


def main() -> None:
    _enable_dpi_awareness()
    app = RexdeskVersionManager()
    app.mainloop()


if __name__ == "__main__":
    main()
