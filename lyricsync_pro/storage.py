from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
from datetime import datetime
import json

@dataclass
class Snapshot:
    timestamp: str
    filename: str
    content: str
    cursor_pos: int

class SnapshotStore:
    def __init__(self, folder: Path):
        self.folder = folder
        self.folder.mkdir(parents=True, exist_ok=True)

    def save_snapshot(self, filename: str, content: str, cursor_pos: int = 0) -> Path:
        ts = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
        snap = Snapshot(timestamp=ts, filename=filename, content=content, cursor_pos=cursor_pos)
        path = self.folder / f"{Path(filename).stem}_{ts}.json"
        path.write_text(json.dumps(asdict(snap), ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def list_snapshots(self) -> list[Path]:
        return sorted(self.folder.glob("*.json"))
