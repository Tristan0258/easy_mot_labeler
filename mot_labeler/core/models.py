from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@dataclass
class ClassDef:
    id: int
    name: str
    color: str
    shortcut: str = ""
    visible: bool = True
    description: str = ""


@dataclass
class BBox:
    x: float
    y: float
    w: float
    h: float

    def as_list(self) -> list[float]:
        return [float(self.x), float(self.y), float(self.w), float(self.h)]

    @classmethod
    def from_list(cls, values: list[float]) -> "BBox":
        return cls(float(values[0]), float(values[1]), float(values[2]), float(values[3]))


@dataclass
class Annotation:
    uuid: str
    frame: int
    track_id: int
    class_id: int
    bbox: BBox
    visibility: float = 1.0
    occlusion: int = 0
    ignore: bool = False
    source: str = "manual"
    confirmed: bool = True
    note: str = ""
    created_at: str = field(default_factory=now_text)
    updated_at: str = field(default_factory=now_text)

    @classmethod
    def create(cls, frame: int, track_id: int, class_id: int, bbox: BBox, source: str = "manual") -> "Annotation":
        return cls(
            uuid=f"ann_{uuid4().hex[:12]}",
            frame=frame,
            track_id=track_id,
            class_id=class_id,
            bbox=bbox,
            source=source,
            confirmed=source in {"manual", "copy", "imported"},
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["bbox"] = self.bbox.as_list()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Annotation":
        item = dict(data)
        item["bbox"] = BBox.from_list(item["bbox"])
        return cls(**item)

    def clone_to_frame(self, frame: int, source: str = "copy") -> "Annotation":
        return Annotation.create(frame, self.track_id, self.class_id, BBox(*self.bbox.as_list()), source=source)


@dataclass
class MediaInfo:
    type: str
    path: str
    width: int
    height: int
    fps: float
    frame_count: int
    image_files: list[str] = field(default_factory=list)


@dataclass
class Project:
    project_name: str
    root: Path
    media: MediaInfo
    classes: list[ClassDef]
    version: str = "1.0"
    created_at: str = field(default_factory=now_text)

    @property
    def project_file(self) -> Path:
        return self.root / "project.yaml"

    @property
    def annotation_file(self) -> Path:
        return self.root / "annotations" / "internal.json"

    @property
    def autosave_file(self) -> Path:
        return self.root / "annotations" / "internal.autosave.json"

    @property
    def classes_file(self) -> Path:
        return self.root / "configs" / "classes.yaml"

