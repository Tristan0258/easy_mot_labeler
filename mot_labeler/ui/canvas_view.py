from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QGraphicsPixmapItem, QGraphicsRectItem, QGraphicsScene, QGraphicsTextItem, QGraphicsView

from ..core.models import Annotation, BBox, ClassDef


class BBoxItem(QGraphicsRectItem):
    def __init__(self, ann: Annotation, color: QColor, selected: bool = False) -> None:
        super().__init__(QRectF(ann.bbox.x, ann.bbox.y, ann.bbox.w, ann.bbox.h))
        self.ann = ann
        pen = QPen(color.darker(140), 7.0 if selected else 5.0)
        if ann.source == "interpolation":
            pen.setStyle(Qt.DashLine)
        elif ann.source == "tracker":
            pen.setStyle(Qt.DashDotLine)
        if selected:
            pen.setColor(QColor("#0057ff"))
        self.setPen(pen)
        self.setBrush(QBrush(QColor(0, 87, 255, 55) if selected else QColor(0, 0, 0, 0)))
        self.setZValue(10)


class CanvasView(QGraphicsView):
    box_created = Signal(float, float, float, float)
    box_selected = Signal(str, bool)
    box_changed = Signal(str, float, float, float, float)
    mouse_position = Signal(float, float)

    def __init__(self) -> None:
        super().__init__()
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.pixmap_item: QGraphicsPixmapItem | None = None
        self.items_by_uuid: dict[str, BBoxItem] = {}
        self.label_by_uuid: dict[str, tuple[QGraphicsTextItem, QGraphicsRectItem]] = {}
        self.label_items = []
        self.selected_uuids: set[str] = set()
        self.classes: dict[int, ClassDef] = {}
        self._drawing = False
        self._moving = False
        self._resizing = False
        self._resize_mode = ""
        self._start = QPointF()
        self._last = QPointF()
        self._temp_rect: QGraphicsRectItem | None = None
        self._active_item: BBoxItem | None = None

    def set_frame(self, frame_bgr) -> None:
        self.scene.clear()
        self.items_by_uuid = {}
        self.label_by_uuid = {}
        self.label_items = []
        self.pixmap_item = None
        if frame_bgr is None:
            return
        h, w = frame_bgr.shape[:2]
        rgb = frame_bgr[:, :, ::-1].copy()
        image = QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888)
        self.pixmap_item = self.scene.addPixmap(QPixmap.fromImage(image))
        self.pixmap_item.setZValue(0)
        self.scene.setSceneRect(0, 0, w, h)

    def set_annotations(self, annotations: list[Annotation], classes: list[ClassDef], selected_uuids) -> None:
        self.classes = {c.id: c for c in classes}
        if isinstance(selected_uuids, str):
            self.selected_uuids = {selected_uuids}
        else:
            self.selected_uuids = set(selected_uuids or [])
        for item in list(self.items_by_uuid.values()):
            self.scene.removeItem(item)
        for item in self.label_items:
            self.scene.removeItem(item)
        self.items_by_uuid = {}
        self.label_by_uuid = {}
        self.label_items = []
        for ann in annotations:
            cls = self.classes.get(ann.class_id)
            color = QColor(cls.color if cls else "#ff7875")
            item = BBoxItem(ann, color, ann.uuid in self.selected_uuids)
            self.scene.addItem(item)
            self.items_by_uuid[ann.uuid] = item
            label = self.scene.addText(f"{cls.name if cls else ann.class_id} #{ann.track_id}")
            label.setFont(QFont("Arial", 16, QFont.Bold))
            label.setDefaultTextColor(QColor("#ffffff"))
            label.setZValue(12)
            bg = QGraphicsRectItem()
            bg.setBrush(QBrush(QColor(0, 0, 0, 185)))
            bg.setPen(QPen(QColor(0, 0, 0, 0)))
            bg.setZValue(11)
            self.scene.addItem(bg)
            self.label_items.extend([bg, label])
            self.label_by_uuid[ann.uuid] = (label, bg)
            self._position_label(ann.uuid, item.rect())

    def fit_to_view(self) -> None:
        if self.scene.sceneRect().isValid():
            self.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)

    def wheelEvent(self, event) -> None:
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)

    def mousePressEvent(self, event) -> None:
        pos = self.mapToScene(event.position().toPoint())
        self._start = pos
        self._last = pos
        if event.button() == Qt.MiddleButton:
            self.setDragMode(QGraphicsView.ScrollHandDrag)
            fake = event.clone()
            super().mousePressEvent(fake)
            return
        if event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return
        item = self._hit_item(pos)
        if item:
            uuid = item.ann.uuid
            additive = bool(event.modifiers() & (Qt.ControlModifier | Qt.ShiftModifier))
            if additive and uuid in self.selected_uuids:
                self.box_selected.emit(uuid, additive)
                self._active_item = None
                self._moving = False
                self._resizing = False
                self.viewport().unsetCursor()
                return
            self.box_selected.emit(uuid, additive)
            item = self.items_by_uuid.get(uuid, item)
            self._active_item = item
            rect = item.rect()
            self._resize_mode = self._hit_mode(rect, pos)
            self._resizing = self._resize_mode != "move"
            self._moving = self._resize_mode == "move"
            self.viewport().setCursor(Qt.CrossCursor if self._resizing else Qt.SizeAllCursor)
        else:
            self._drawing = True
            self._temp_rect = QGraphicsRectItem(QRectF(pos, pos))
            self._temp_rect.setPen(QPen(QColor("#ffd666"), 2, Qt.DashLine))
            self._temp_rect.setZValue(20)
            self.scene.addItem(self._temp_rect)

    def mouseMoveEvent(self, event) -> None:
        pos = self.mapToScene(event.position().toPoint())
        self.mouse_position.emit(pos.x(), pos.y())
        if self._drawing and self._temp_rect:
            self._temp_rect.setRect(QRectF(self._start, pos).normalized())
            return
        if self._active_item and (self._moving or self._resizing):
            rect = self._active_item.rect()
            delta = pos - self._last
            if self._moving:
                rect.translate(delta)
            else:
                rect = self._resize_rect(rect, delta)
            rect = rect.normalized()
            if rect.width() >= 2 and rect.height() >= 2:
                self._active_item.setRect(rect)
                self._position_label(self._active_item.ann.uuid, rect)
            self._last = pos
            return
        hover_item = self._hit_item(pos)
        if hover_item:
            mode = self._hit_mode(hover_item.rect(), pos)
            self.viewport().setCursor(Qt.CrossCursor if mode != "move" else Qt.SizeAllCursor)
        else:
            self.viewport().unsetCursor()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MiddleButton:
            self.setDragMode(QGraphicsView.NoDrag)
            super().mouseReleaseEvent(event)
            return
        if self._drawing and self._temp_rect:
            rect = self._temp_rect.rect().normalized()
            self.scene.removeItem(self._temp_rect)
            self._temp_rect = None
            self._drawing = False
            if rect.width() > 3 and rect.height() > 3:
                self.box_created.emit(rect.x(), rect.y(), rect.width(), rect.height())
            return
        if self._active_item and (self._moving or self._resizing):
            rect = self._active_item.rect().normalized()
            self.box_changed.emit(self._active_item.ann.uuid, rect.x(), rect.y(), rect.width(), rect.height())
        self._active_item = None
        self._moving = False
        self._resizing = False
        self._resize_mode = ""
        self.viewport().unsetCursor()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:
        primary_uuid = next(iter(self.selected_uuids), None)
        if primary_uuid and primary_uuid in self.items_by_uuid:
            step = 10 if event.modifiers() & Qt.ShiftModifier else 1
            dx = dy = 0
            if event.key() == Qt.Key_Left:
                dx = -step
            elif event.key() == Qt.Key_Right:
                dx = step
            elif event.key() == Qt.Key_Up:
                dy = -step
            elif event.key() == Qt.Key_Down:
                dy = step
            if dx or dy:
                item = self.items_by_uuid[primary_uuid]
                rect = item.rect()
                rect.translate(dx, dy)
                item.setRect(rect)
                self.box_changed.emit(primary_uuid, rect.x(), rect.y(), rect.width(), rect.height())
                return
        super().keyPressEvent(event)

    def _hit_item(self, pos: QPointF) -> BBoxItem | None:
        for item in reversed(list(self.items_by_uuid.values())):
            if item.rect().adjusted(-12, -12, 12, 12).contains(pos):
                return item
        return None

    def _hit_mode(self, rect: QRectF, pos: QPointF) -> str:
        tolerance = 18
        left = abs(pos.x() - rect.left()) <= tolerance
        right = abs(pos.x() - rect.right()) <= tolerance
        top = abs(pos.y() - rect.top()) <= tolerance
        bottom = abs(pos.y() - rect.bottom()) <= tolerance
        if left and top:
            return "top_left"
        if right and top:
            return "top_right"
        if left and bottom:
            return "bottom_left"
        if right and bottom:
            return "bottom_right"
        if left:
            return "left"
        if right:
            return "right"
        if top:
            return "top"
        if bottom:
            return "bottom"
        return "move"

    def _resize_rect(self, rect: QRectF, delta: QPointF) -> QRectF:
        mode = self._resize_mode
        if "left" in mode:
            rect.setLeft(rect.left() + delta.x())
        if "right" in mode:
            rect.setRight(rect.right() + delta.x())
        if "top" in mode:
            rect.setTop(rect.top() + delta.y())
        if "bottom" in mode:
            rect.setBottom(rect.bottom() + delta.y())
        return rect

    def _position_label(self, uuid: str, rect: QRectF) -> None:
        if uuid not in self.label_by_uuid:
            return
        label, bg = self.label_by_uuid[uuid]
        label.setPos(rect.x() + 2, max(0, rect.y() - 31))
        bounds = label.boundingRect().adjusted(-4, -2, 4, 2)
        bg.setRect(bounds)
        bg.setPos(label.pos())
