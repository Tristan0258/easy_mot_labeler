from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

from .models import Annotation


class AnnotationStore:
    def __init__(self) -> None:
        self.annotations: list[Annotation] = []
        self.dirty = False

    def load(self, path: Path) -> None:
        if not path.exists():
            self.annotations = []
            self.dirty = False
            return
        data = json.loads(path.read_text(encoding="utf-8"))
        self.annotations = [Annotation.from_dict(item) for item in data.get("annotations", [])]
        self.dirty = False

    def save(self, path: Path, make_backup: bool = False) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if make_backup and path.exists():
            backup_dir = path.parent / "backups"
            backup_dir.mkdir(exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            shutil.copy2(path, backup_dir / f"internal_{stamp}.json")
            backups = sorted(backup_dir.glob("internal_*.json"))
            for old in backups[:-10]:
                old.unlink(missing_ok=True)
        data = {
            "version": "1.0",
            "frame_base": 0,
            "annotations": [ann.to_dict() for ann in self.annotations],
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        self.dirty = False

    def frame_items(self, frame: int) -> list[Annotation]:
        return [ann for ann in self.annotations if ann.frame == frame]

    def add(self, ann: Annotation) -> None:
        self.annotations.append(ann)
        self.dirty = True

    def remove(self, uuids: set[str]) -> None:
        self.annotations = [ann for ann in self.annotations if ann.uuid not in uuids]
        self.dirty = True

    def replace_for_track_frame(self, frame: int, track_id: int, ann: Annotation) -> None:
        self.annotations = [a for a in self.annotations if not (a.frame == frame and a.track_id == track_id)]
        self.annotations.append(ann)
        self.dirty = True

    def next_track_id(self) -> int:
        used = [ann.track_id for ann in self.annotations if ann.track_id is not None]
        return max(used, default=0) + 1

    def annotated_frame_count(self) -> int:
        return len({ann.frame for ann in self.annotations})
