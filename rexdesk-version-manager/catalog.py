from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Dict


@dataclass
class VersionRecord:
    version: str
    status: str = "not_installed"
    install_path: str = ""
    exe_path: str = ""
    msi_path: str = ""
    notes_path: str = ""
    bug_notes_path: str = ""
    release_date: str = ""
    coexistence_conflict: bool = False
    last_error: str = ""


class CatalogStore:
    def __init__(self, catalog_path: Path) -> None:
        self.catalog_path = catalog_path
        self._records: Dict[str, VersionRecord] = {}
        self.load()

    def load(self) -> None:
        if not self.catalog_path.exists():
            self._records = {}
            return

        raw = json.loads(self.catalog_path.read_text(encoding="utf-8"))
        records = {}
        for key, value in raw.get("versions", {}).items():
            records[key] = VersionRecord(**value)
        self._records = records

    def save(self) -> None:
        payload = {
            "versions": {version: asdict(record) for version, record in self._records.items()}
        }
        self.catalog_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def all_versions(self) -> list[VersionRecord]:
        return sorted(self._records.values(), key=lambda r: r.version.lower())

    def get(self, version: str) -> VersionRecord | None:
        return self._records.get(version)

    def upsert(self, record: VersionRecord) -> None:
        self._records[record.version] = record
        self.save()

    def remove(self, version: str) -> None:
        self._records.pop(version, None)
        self.save()
