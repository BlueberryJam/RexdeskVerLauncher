from __future__ import annotations

import ctypes
import ctypes.wintypes
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Iterable

from config import safe_version_slug

_SEE_MASK_NOCLOSEPROCESS = 0x00000040
_SW_HIDE = 0
_INFINITE = 0xFFFFFFFF


class _SHELLEXECUTEINFOW(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.wintypes.DWORD),
        ("fMask", ctypes.c_ulong),
        ("hwnd", ctypes.wintypes.HWND),
        ("lpVerb", ctypes.c_wchar_p),
        ("lpFile", ctypes.c_wchar_p),
        ("lpParameters", ctypes.c_wchar_p),
        ("lpDirectory", ctypes.c_wchar_p),
        ("nShow", ctypes.c_int),
        ("hInstApp", ctypes.wintypes.HINSTANCE),
        ("lpIDList", ctypes.c_void_p),
        ("lpClass", ctypes.c_wchar_p),
        ("hkeyClass", ctypes.wintypes.HKEY),
        ("dwHotKey", ctypes.wintypes.DWORD),
        ("hIconOrMonitor", ctypes.wintypes.HANDLE),
        ("hProcess", ctypes.wintypes.HANDLE),
    ]


def _is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _build_msiexec_args(params: list[str]) -> str:
    def _q(s: str) -> str:
        return f'"{s}"' if " " in s else s

    parts: list[str] = []
    for arg in params:
        if "=" in arg and not arg.startswith("/"):
            key, _, value = arg.partition("=")
            parts.append(f"{key}={_q(value)}")
        else:
            parts.append(_q(arg))
    return " ".join(parts)


def _run_elevated(params: list[str]) -> int:
    """Run msiexec with admin elevation via UAC prompt if needed."""
    args_str = _build_msiexec_args(params)

    if _is_admin():
        no_window = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        result = subprocess.run(f"msiexec {args_str}", creationflags=no_window)
        return result.returncode

    sei = _SHELLEXECUTEINFOW()
    sei.cbSize = ctypes.sizeof(sei)
    sei.fMask = _SEE_MASK_NOCLOSEPROCESS
    sei.lpVerb = "runas"
    sei.lpFile = "msiexec"
    sei.lpParameters = args_str
    sei.nShow = _SW_HIDE

    if not ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(sei)):
        raise ctypes.WinError()

    ctypes.windll.kernel32.WaitForSingleObject(sei.hProcess, _INFINITE)
    exit_code = ctypes.wintypes.DWORD()
    ctypes.windll.kernel32.GetExitCodeProcess(sei.hProcess, ctypes.byref(exit_code))
    ctypes.windll.kernel32.CloseHandle(sei.hProcess)
    return exit_code.value


def _read_msi_property(msi_path: Path, property_name: str) -> str | None:
    """Read a single property from an MSI database via the Windows Installer C API."""
    if sys.platform != "win32":
        return None
    try:
        dll = ctypes.WinDLL("msi")
    except OSError:
        return None

    _HANDLE = ctypes.c_uint32
    _PHANDLE = ctypes.POINTER(ctypes.c_uint32)
    _UINT = ctypes.c_uint32
    _PUINT = ctypes.POINTER(ctypes.c_uint32)
    _LPCWSTR = ctypes.c_wchar_p

    dll.MsiOpenDatabaseW.argtypes = [_LPCWSTR, _LPCWSTR, _PHANDLE]
    dll.MsiOpenDatabaseW.restype = _UINT
    dll.MsiDatabaseOpenViewW.argtypes = [_HANDLE, _LPCWSTR, _PHANDLE]
    dll.MsiDatabaseOpenViewW.restype = _UINT
    dll.MsiViewExecute.argtypes = [_HANDLE, _HANDLE]
    dll.MsiViewExecute.restype = _UINT
    dll.MsiViewFetch.argtypes = [_HANDLE, _PHANDLE]
    dll.MsiViewFetch.restype = _UINT
    dll.MsiRecordGetStringW.argtypes = [_HANDLE, _UINT, _LPCWSTR, _PUINT]
    dll.MsiRecordGetStringW.restype = _UINT
    dll.MsiCloseHandle.argtypes = [_HANDLE]
    dll.MsiCloseHandle.restype = _UINT

    h_db = _HANDLE()
    # None → NULL pointer → MSIDBOPEN_READONLY
    if dll.MsiOpenDatabaseW(str(msi_path), None, ctypes.byref(h_db)) != 0:
        return None
    try:
        h_view = _HANDLE()
        sql = f"SELECT `Value` FROM `Property` WHERE `Property` = '{property_name}'"
        if dll.MsiDatabaseOpenViewW(h_db, sql, ctypes.byref(h_view)) != 0:
            return None
        try:
            if dll.MsiViewExecute(h_view, 0) != 0:
                return None
            h_rec = _HANDLE()
            if dll.MsiViewFetch(h_view, ctypes.byref(h_rec)) != 0:
                return None
            try:
                buf_len = _UINT(256)
                buf = ctypes.create_unicode_buffer(256)
                rc = dll.MsiRecordGetStringW(h_rec, 1, buf, ctypes.byref(buf_len))
                if rc == 234:  # ERROR_MORE_DATA
                    buf_len.value += 1
                    buf = ctypes.create_unicode_buffer(buf_len.value)
                    rc = dll.MsiRecordGetStringW(h_rec, 1, buf, ctypes.byref(buf_len))
                return buf.value if rc == 0 else None
            finally:
                dll.MsiCloseHandle(h_rec)
        finally:
            dll.MsiCloseHandle(h_view)
    finally:
        dll.MsiCloseHandle(h_db)


def find_registered_product_code(msi_path: Path) -> str | None:
    """Query Windows Installer for any currently-registered product sharing
    the same UpgradeCode as *msi_path*.  Returns the product code GUID
    string (e.g. ``'{…}'``) or ``None`` if nothing is registered.

    This does NOT require elevation and is always accurate regardless of
    catalog state.
    """
    upgrade_code = _read_msi_property(msi_path, "UpgradeCode")
    if not upgrade_code:
        return None
    try:
        dll = ctypes.WinDLL("msi")
    except OSError:
        return None

    product_code_buf = ctypes.create_unicode_buffer(39)
    dll.MsiEnumRelatedProductsW.argtypes = [
        ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32,
        ctypes.c_wchar_p,
    ]
    dll.MsiEnumRelatedProductsW.restype = ctypes.c_uint32
    rc = dll.MsiEnumRelatedProductsW(upgrade_code, 0, 0, product_code_buf)
    if rc == 0:
        return product_code_buf.value
    return None


def uninstall_product_code(
    product_code: str,
    log_path: Path,
) -> subprocess.CompletedProcess[str]:
    """Uninstall a product by its Windows Installer ProductCode GUID."""
    params = ["/x", product_code, "/qn", "/L*v", str(log_path)]
    returncode = _run_elevated(params)
    return subprocess.CompletedProcess(args=params, returncode=returncode)


def detect_msi_product_key(msi_path: Path) -> str | None:
    """Return 'rexdesk', 'rexbridge', or None based on the MSI's ProductName property."""
    try:
        name = _read_msi_property(msi_path, "ProductName")
    except Exception:
        return None
    if not name:
        return None
    name_lower = name.lower()
    if "rexdesk" in name_lower:
        return "rexdesk"
    if "rexbridge" in name_lower:
        return "rexbridge"
    return None


def infer_version_label(msi_path: Path) -> str:
    stem = msi_path.stem
    match = re.search(r"(\d+\.\d+(?:\.\d+){0,2})", stem)
    if match:
        return match.group(1)
    return stem


def copy_msi_to_store(source_msi: Path, msi_dir: Path, version_label: str) -> Path:
    if source_msi.suffix.lower() != ".msi":
        raise ValueError("Only .msi files are supported.")

    msi_dir.mkdir(parents=True, exist_ok=True)
    target_name = f"{safe_version_slug(version_label)}.msi"
    target_path = msi_dir / target_name
    shutil.copy2(source_msi, target_path)
    return target_path


def ensure_patch_notes_file(notes_dir: Path, version_label: str) -> Path:
    notes_dir.mkdir(parents=True, exist_ok=True)
    notes_path = notes_dir / f"{safe_version_slug(version_label)}.txt"
    if not notes_path.exists():
        notes_path.write_text("", encoding="utf-8")
    return notes_path


def ensure_patch_notes_file_beside_msi(msi_path: Path) -> Path:
    """Create (or find) a patch notes .txt file in the same folder as the MSI."""
    notes_path = msi_path.parent / f"{msi_path.stem}_notes.txt"
    if not notes_path.exists():
        notes_path.write_text("", encoding="utf-8")
    return notes_path


def ensure_bug_notes_file(bug_notes_dir: Path, version_label: str) -> Path:
    bug_notes_dir.mkdir(parents=True, exist_ok=True)
    bug_path = bug_notes_dir / f"{safe_version_slug(version_label)}.txt"
    if not bug_path.exists():
        bug_path.write_text("", encoding="utf-8")
    return bug_path


def export_msi_copy(msi_path: Path, destination_dir: Path) -> Path:
    destination_dir.mkdir(parents=True, exist_ok=True)
    target = destination_dir / msi_path.name
    shutil.copy2(msi_path, target)
    return target


def open_in_explorer(target_path: Path) -> None:
    if not target_path.exists():
        raise FileNotFoundError(target_path)
    subprocess.run(["explorer", "/select,", str(target_path)], check=False)


def open_folder(folder_path: Path) -> None:
    if not folder_path.exists():
        raise FileNotFoundError(folder_path)
    os.startfile(str(folder_path))  # type: ignore[attr-defined]


def launch_executable(exe_path: Path) -> None:
    if not exe_path.exists():
        raise FileNotFoundError(exe_path)
    os.startfile(str(exe_path))  # type: ignore[attr-defined]


_SHELTER_RETRIES = 3
_SHELTER_RETRY_DELAY = 1.0


def shelter_install_dirs(
    dirs_to_shelter: list[tuple[Path, Path]],
) -> list[tuple[Path, Path]]:
    """Move installed version directories to backup locations so msiexec's
    RemoveExistingProducts cannot delete their files.

    Each tuple is (install_dir, backup_dir).
    Returns the pairs that were successfully moved.
    """
    import time as _t

    moved: list[tuple[Path, Path]] = []
    for install_dir, backup_dir in dirs_to_shelter:
        if not install_dir.exists():
            continue
        try:
            if not any(install_dir.iterdir()):
                continue
        except OSError:
            continue
        backup_dir.parent.mkdir(parents=True, exist_ok=True)
        if backup_dir.exists():
            shutil.rmtree(backup_dir, ignore_errors=True)

        last_err: Exception | None = None
        for attempt in range(_SHELTER_RETRIES):
            try:
                if backup_dir.exists():
                    shutil.rmtree(backup_dir, ignore_errors=True)
                shutil.copytree(str(install_dir), str(backup_dir))
                shutil.rmtree(str(install_dir), ignore_errors=True)
                last_err = None
                break
            except OSError as exc:
                last_err = exc
                _t.sleep(_SHELTER_RETRY_DELAY)

        if last_err is not None:
            continue

        moved.append((install_dir, backup_dir))
    return moved


def unshelter_install_dirs(moved: list[tuple[Path, Path]]) -> None:
    """Restore previously sheltered install directories."""
    for install_dir, backup_dir in moved:
        if not backup_dir.exists():
            continue
        if install_dir.exists():
            shutil.rmtree(install_dir)
        install_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(backup_dir), str(install_dir))


def install_with_msiexec(
    msi_path: Path,
    install_dir: Path,
    log_path: Path,
    extra_properties: Iterable[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    install_dir.mkdir(parents=True, exist_ok=True)
    params = [
        "/i",
        str(msi_path),
        f"INSTALLDIR={install_dir}",
        f"TARGETDIR={install_dir}",
        "/qn",
        "/L*v",
        str(log_path),
    ]
    if extra_properties:
        params.extend(extra_properties)
    returncode = _run_elevated(params)
    return subprocess.CompletedProcess(args=params, returncode=returncode)


def uninstall_with_msiexec(
    msi_path: Path,
    log_path: Path,
) -> subprocess.CompletedProcess[str]:
    params = [
        "/x",
        str(msi_path),
        "/qn",
        "/L*v",
        str(log_path),
    ]
    returncode = _run_elevated(params)
    return subprocess.CompletedProcess(args=params, returncode=returncode)
