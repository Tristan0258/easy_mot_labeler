from __future__ import annotations

from pathlib import Path

import yaml

from .models import ClassDef, MediaInfo, Project


DEFAULT_CLASSES = [
    ClassDef(1, "person", "#ff1744", "1"),
    ClassDef(2, "vehicle", "#00e676", "2"),
    ClassDef(3, "bicycle", "#2979ff", "3"),
]


def write_project(project: Project) -> None:
    (project.root / "annotations").mkdir(parents=True, exist_ok=True)
    (project.root / "configs").mkdir(parents=True, exist_ok=True)
    write_classes(project)
    data = {
        "project_name": project.project_name,
        "version": project.version,
        "created_at": project.created_at,
        "media": project.media.__dict__,
        "annotation_file": "annotations/internal.json",
        "autosave_file": "annotations/internal.autosave.json",
        "classes_file": "configs/classes.yaml",
        "settings_file": "configs/settings.yaml",
    }
    project.project_file.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def write_classes(project: Project) -> None:
    (project.root / "configs").mkdir(parents=True, exist_ok=True)
    project.classes_file.write_text(
        yaml.safe_dump({"classes": [c.__dict__ for c in project.classes]}, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def load_project(path: Path) -> Project:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    root = path.parent
    media = MediaInfo(**data["media"])
    classes_path = root / data.get("classes_file", "configs/classes.yaml")
    classes_data = yaml.safe_load(classes_path.read_text(encoding="utf-8")) if classes_path.exists() else {}
    classes = [ClassDef(**item) for item in classes_data.get("classes", [])] or DEFAULT_CLASSES
    return Project(
        project_name=data["project_name"],
        root=root,
        media=media,
        classes=classes,
        version=str(data.get("version", "1.0")),
        created_at=data.get("created_at", ""),
    )
