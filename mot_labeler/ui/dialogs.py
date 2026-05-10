from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QComboBox, QDialog, QFormLayout, QHBoxLayout, QLineEdit, QPushButton, QSpinBox, QVBoxLayout


class ExportDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("导出标注")
        self.format_combo = QComboBox()
        self.format_combo.addItems(["MOT多类别", "YOLO", "LabelMe JSON"])
        self.include_unconfirmed = QCheckBox("导出未确认自动框")
        self.include_ignore = QCheckBox("导出 ignore 标注")
        self.auto_repair = QCheckBox("导出前自动裁剪越界框并删除无效框")
        self.auto_repair.setChecked(True)
        ok = QPushButton("导出")
        ok.clicked.connect(self.accept)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.addRow("导出格式", self.format_combo)
        layout.addLayout(form)
        layout.addWidget(self.include_unconfirmed)
        layout.addWidget(self.include_ignore)
        layout.addWidget(self.auto_repair)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(cancel)
        row.addWidget(ok)
        layout.addLayout(row)


class TrackerDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("自动跟踪")
        self.frames = QSpinBox()
        self.frames.setRange(1, 300)
        self.frames.setValue(30)
        self.direction = QComboBox()
        self.direction.addItems(["向后", "向前"])
        self.algorithm = QComboBox()
        self.algorithm.addItems(["AUTO", "光流", "CSRT", "KCF", "MOSSE", "模板匹配"])
        self.overwrite = QCheckBox("覆盖已有同 ID 标注")
        form = QFormLayout()
        form.addRow("跟踪帧数", self.frames)
        form.addRow("方向", self.direction)
        form.addRow("算法", self.algorithm)
        form.addRow("", self.overwrite)
        ok = QPushButton("开始")
        ok.clicked.connect(self.accept)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(cancel)
        buttons.addWidget(ok)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(buttons)

    def direction_value(self) -> int:
        return 1 if self.direction.currentIndex() == 0 else -1


class InterpolationDialog(QDialog):
    def __init__(self, current_frame: int, selected_track: int | None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("区间插值")
        self.track_id = QSpinBox()
        self.track_id.setRange(1, 999999)
        if selected_track:
            self.track_id.setValue(selected_track)
        self.start_frame = QSpinBox()
        self.start_frame.setRange(0, 999999)
        self.start_frame.setValue(current_frame)
        self.end_frame = QSpinBox()
        self.end_frame.setRange(0, 999999)
        self.end_frame.setValue(current_frame + 10)
        self.overwrite = QCheckBox("覆盖中间帧已有同 ID 标注")
        form = QFormLayout()
        form.addRow("Track ID", self.track_id)
        form.addRow("起始帧(0-based)", self.start_frame)
        form.addRow("结束帧(0-based)", self.end_frame)
        form.addRow("", self.overwrite)
        ok = QPushButton("生成插值")
        ok.clicked.connect(self.accept)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(cancel)
        row.addWidget(ok)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(row)


class GoToFrameDialog(QDialog):
    def __init__(self, max_frame: int, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("跳转帧")
        self.frame = QSpinBox()
        self.frame.setRange(1, max_frame)
        ok = QPushButton("跳转")
        ok.clicked.connect(self.accept)
        layout = QFormLayout(self)
        layout.addRow("帧号(1-based)", self.frame)
        layout.addRow("", ok)
