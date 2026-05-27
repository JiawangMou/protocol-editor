"""网络拓扑图画布 — 设备绘制 + 总线连线 + 手动连线 + 吸附对齐"""
from __future__ import annotations
from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsItem, QGraphicsRectItem, QGraphicsTextItem, QGraphicsLineItem, QGraphicsEllipseItem, QMenu
from PySide6.QtCore import Qt, Signal, QPointF, QRectF, QLineF
from PySide6.QtGui import QPen, QBrush, QColor, QFont, QPainter

from app.models.protocol import Project, Device, Connection, DeviceInterface
from app.models.enums import InterfaceType

W = 160
H = 80
SNAP_THRESHOLD = 15.0

# 总线实例颜色调色板 — 每个总线实例 (按 bus_id) 分配唯一颜色
_BUS_PALETTE = [
    QColor(100, 200, 100),   # 绿
    QColor(200, 200, 80),    # 黄
    QColor(200, 100, 80),    # 橙
    QColor(100, 160, 220),   # 蓝
    QColor(200, 120, 180),   # 紫
    QColor(80, 200, 200),    # 青
    QColor(220, 180, 100),   # 金
    QColor(160, 120, 200),   # 蓝紫
    QColor(200, 80, 80),     # 红
    QColor(120, 200, 160),   # 薄荷
]
_bus_color_cache: dict[str, QColor] = {}
_next_color_idx: int = 0


def _bus_color(bus_id: str) -> QColor:
    """为每个总线实例分配唯一颜色, 同一总线 ID 始终返回相同颜色。"""
    if bus_id not in _bus_color_cache:
        global _next_color_idx
        _bus_color_cache[bus_id] = _BUS_PALETTE[_next_color_idx % len(_BUS_PALETTE)]
        _next_color_idx += 1
    return _bus_color_cache[bus_id]


# 总线类型 → 默认颜色 (向后兼容, 用于未绑定总线的接口)
BUS_TYPE_DEFAULT_COLOR: dict[InterfaceType, QColor] = {
    InterfaceType.ETHERNET: QColor(100, 200, 100),
    InterfaceType.RS422: QColor(200, 200, 80),
    InterfaceType.RS232: QColor(200, 160, 80),
    InterfaceType.CAN: QColor(200, 100, 80),
    InterfaceType.CANFD: QColor(220, 80, 80),
}

# 默认行 Y 坐标
TOP_ROW_Y = 80.0
BOTTOM_ROW_Y = 330.0
SNAP_ROWS = (TOP_ROW_Y, BOTTOM_ROW_Y)


class DeviceRect(QGraphicsRectItem):
    """拓扑图中的设备节点 — 支持拖拽吸附对齐和总线连线刷新。"""

    def __init__(self, device: Device, project: Project, canvas: TopologyCanvas):
        super().__init__(0, 0, W, H)
        self.device_id = device.id
        self._device = device
        self._project = project
        self._canvas = canvas
        self._snapping = False
        self._iface_dots: dict[str, QGraphicsEllipseItem] = {}

        self.setPos(device.x, device.y)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setBrush(QBrush(QColor(60, 63, 65)))
        self.setPen(QPen(QColor(120, 180, 240), 2))
        self.setZValue(2)

        self._label = QGraphicsTextItem(device.name, self)
        self._label.setDefaultTextColor(QColor(220, 220, 220))
        self._label.setFont(QFont("Microsoft YaHei", 9))
        self._label.setPos(8, 4)
        self._label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self._label.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

        self.rebuild_ifaces(device.interfaces)

    def rebuild_ifaces(self, interfaces: list[DeviceInterface]):
        for dot in self._iface_dots.values():
            if dot.scene():
                dot.scene().removeItem(dot)
        self._iface_dots.clear()

        if not interfaces:
            return

        spacing = W / (len(interfaces) + 1)
        for i, iface in enumerate(interfaces):
            x = spacing * (i + 1) - 6
            y = H - 12
            dot = QGraphicsEllipseItem(0, 0, 12, 12, self)
            dot.setPos(x, y)
            bc = self._project.find_bus_config(iface.bus_config_id)
            color = QColor(128, 128, 128)
            if bc:
                color = _bus_color(bc.id)
            dot.setBrush(QBrush(color))
            dot.setPen(QPen(color.darker(120), 1))
            dot.setZValue(4)
            dot.setData(0, iface.id)
            bus_type_str = bc.type.value if bc else "?"
            dot.setToolTip(f"{iface.name} ({bus_type_str})")
            self._iface_dots[iface.id] = dot

        self.setRect(0, 0, W, H + 10)

    def iface_dot_center(self, iface_id: str) -> QPointF:
        dot = self._iface_dots.get(iface_id)
        if dot:
            return self.mapToScene(dot.pos() + QPointF(6, 6))
        return self.mapToScene(QPointF(W / 2, H))

    def itemChange(self, change, value):
        """拖拽时: 先吸附对齐 → 保存坐标 → 通知画布刷新总线连线。"""
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            if not self._snapping:
                self._snapping = True
                snapped = self._apply_snap(QPointF(value))
                self._snapping = False
                return snapped
        elif change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self._device.x = self.pos().x()
            self._device.y = self.pos().y()
            self._canvas._on_device_moved()
        return super().itemChange(change, value)

    def _apply_snap(self, new_pos: QPointF) -> QPointF:
        """寻找场景中其他 DeviceRect, 在阈值范围内吸附对齐 X 或 Y。"""
        x, y = new_pos.x(), new_pos.y()
        snapped_x, snapped_y = x, y

        others: list[DeviceRect] = []
        for item in self._canvas._device_items.values():
            if item is not self:
                others.append(item)

        for other in others:
            ox, oy = other.pos().x(), other.pos().y()
            # X 轴对齐 (左边界)
            if abs(x - ox) < SNAP_THRESHOLD:
                snapped_x = ox
            # 右边界对齐
            if abs((x + W) - (ox + W)) < SNAP_THRESHOLD:
                snapped_x = ox
            # Y 轴对齐 (顶边)
            if abs(y - oy) < SNAP_THRESHOLD:
                snapped_y = oy

        # 吸附到默认行位置
        for row_y in SNAP_ROWS:
            if abs(y - row_y) < SNAP_THRESHOLD:
                snapped_y = row_y

        return QPointF(snapped_x, snapped_y)


class ConnectionLine(QGraphicsLineItem):
    """手动连线 (虚线)。"""

    def __init__(self, conn: Connection, from_pos: QPointF, to_pos: QPointF):
        super().__init__()
        self.conn_id = conn.id
        self.setPen(QPen(QColor(180, 180, 180), 2, Qt.PenStyle.DashLine))
        self.setZValue(1)
        self.setLine(QLineF(from_pos, to_pos))

        self._label = QGraphicsTextItem(conn.label, self)
        self._label.setDefaultTextColor(QColor(150, 150, 150))
        self._label.setFont(QFont("Microsoft YaHei", 7))
        mid = (from_pos + to_pos) / 2
        self._label.setPos(mid.x() + 5, mid.y() - 12)

    def update_positions(self, from_pos: QPointF, to_pos: QPointF):
        self.setLine(QLineF(from_pos, to_pos))
        mid = (from_pos + to_pos) / 2
        self._label.setPos(mid.x() + 5, mid.y() - 12)


class MovableTrunkLine(QGraphicsLineItem):
    """可拖拽的总线主干线 — 支持上下拖动调整垂直位置。"""

    def __init__(self, bus_id: str, canvas, x1, y1, x2, y2):
        super().__init__(x1, y1, x2, y2)
        self.bus_id = bus_id
        self._canvas = canvas
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setCursor(Qt.CursorShape.SizeVerCursor)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            # 约束 X 方向不可移动, 只允许垂直拖动
            pos = QPointF(value)
            pos.setX(0)
            return pos
        elif change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self._canvas._on_trunk_moved(self.bus_id, self.pos().y())
        return super().itemChange(change, value)


class TopologyCanvas(QGraphicsView):
    """网络拓扑视图 — 设备 + 手动连线 + 总线连线 + 吸附对齐。"""
    device_selected = Signal(str)
    device_double_clicked = Signal(str)

    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self._project = project
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setMinimumHeight(300)
        self.setStyleSheet("background: #2b2b2b; border: 1px solid #444;")

        self._device_items: dict[str, DeviceRect] = {}
        self._conn_items: dict[str, ConnectionLine] = {}
        # bus_id → {trunk, label, drops, drop_xs, drop_ys, trunk_y0, avg_y}
        self._bus_items: dict[str, dict] = {}
        self._trunk_y_offsets: dict[str, float] = {}  # bus_id → 用户手动拖拽的 Y 方向偏移量 (相对 avg_y)
        self._drag_conn: DeviceRect | None = None
        self._drag_iface_id: str = ""

        self._scene.selectionChanged.connect(self._on_scene_selection_changed)

    def set_project(self, project: Project):
        self._project = project
        self._rebuild()

    def _rebuild(self):
        self._scene.clear()
        self._device_items.clear()
        self._conn_items.clear()
        self._bus_items.clear()

        for device in self._project.devices:
            item = DeviceRect(device, self._project, self)
            self._scene.addItem(item)
            self._device_items[device.id] = item

        self._rebuild_bus_lines()
        self._rebuild_connections()

    def _rebuild_connections(self):
        for conn in self._project.connections:
            self._add_connection_line(conn)

    def _add_connection_line(self, conn: Connection):
        from_device = self._device_items.get(conn.from_device_id)
        to_device = self._device_items.get(conn.to_device_id)
        if not from_device or not to_device:
            return
        from_pos = from_device.iface_dot_center(conn.from_interface_id)
        to_pos = to_device.iface_dot_center(conn.to_interface_id)
        line = ConnectionLine(conn, from_pos, to_pos)
        self._scene.addItem(line)
        self._conn_items[conn.id] = line

    # ── 总线连线 ──

    def _rebuild_bus_lines(self):
        """为共享同一 BusConfig 的设备接口绘制粗实线总线。干线可通过鼠标上下拖拽调整位置。"""
        # 清除旧总线图形项
        for info in self._bus_items.values():
            if info["trunk"].scene():
                info["trunk"].scene().removeItem(info["trunk"])
            if info["label"].scene():
                info["label"].scene().removeItem(info["label"])
            for drop in info["drops"]:
                if drop.scene():
                    drop.scene().removeItem(drop)
        self._bus_items.clear()

        # 按 bus_config_id 分组: {bus_id: [(DeviceRect, DeviceInterface), ...]}
        bus_groups: dict[str, list[tuple[DeviceRect, DeviceInterface]]] = {}
        for device in self._project.devices:
            item = self._device_items.get(device.id)
            if not item:
                continue
            for iface in device.interfaces:
                bid = iface.bus_config_id
                if bid:
                    bus_groups.setdefault(bid, []).append((item, iface))

        for bus_id, group in bus_groups.items():
            if len(group) < 2:
                continue
            bc = self._project.find_bus_config(bus_id)
            if not bc:
                continue

            # 收集接口点场景坐标
            dots: list[QPointF] = []
            for item, iface in group:
                dots.append(item.iface_dot_center(iface.id))
            if not dots:
                continue

            # 总线干线 Y: 接口点平均 Y + 用户手动拖拽偏移量
            avg_y = sum(d.y() for d in dots) / len(dots)
            trunk_y = avg_y + self._trunk_y_offsets.get(bus_id, 0)
            min_x = min(d.x() for d in dots) - 20
            max_x = max(d.x() for d in dots) + 20

            color = _bus_color(bc.id)
            drop_pen = QPen(color, 2, Qt.PenStyle.SolidLine)

            # 总线标签
            label = QGraphicsTextItem(f"{bc.name} ({bc.type.value.upper()})")
            label.setDefaultTextColor(color.lighter(130))
            label.setFont(QFont("Microsoft YaHei", 8))
            label.setPos(min_x + 5, trunk_y - 18)
            label.setZValue(3)
            self._scene.addItem(label)

            # 干线: 使用 MovableTrunkLine 支持鼠标上下拖拽
            trunk = MovableTrunkLine(bus_id, self, min_x, trunk_y, max_x, trunk_y)
            trunk.setPen(QPen(color, 3, Qt.PenStyle.SolidLine))
            trunk.setZValue(2)
            self._scene.addItem(trunk)

            # 支线 (从设备接口点到干线)
            drops: list[QGraphicsLineItem] = []
            drop_xs: list[float] = []
            drop_ys: list[float] = []
            for dot in dots:
                drop = QGraphicsLineItem(QLineF(dot.x(), dot.y(), dot.x(), trunk_y))
                drop.setPen(drop_pen)
                drop.setZValue(1)
                self._scene.addItem(drop)
                drops.append(drop)
                drop_xs.append(dot.x())
                drop_ys.append(dot.y())

            self._bus_items[bus_id] = {
                "trunk": trunk, "label": label, "drops": drops,
                "drop_xs": drop_xs, "drop_ys": drop_ys,
                "trunk_y0": trunk_y, "avg_y": avg_y,
            }

    def _on_device_moved(self):
        """设备移动后刷新总线连线和手动连线端点。"""
        self._rebuild_bus_lines()
        # 同时也需要更新手动连线的端点
        for conn in self._project.connections:
            line = self._conn_items.get(conn.id)
            if not line:
                continue
            from_dev = self._device_items.get(conn.from_device_id)
            to_dev = self._device_items.get(conn.to_device_id)
            if from_dev and to_dev:
                line.update_positions(
                    from_dev.iface_dot_center(conn.from_interface_id),
                    to_dev.iface_dot_center(conn.to_interface_id),
                )

    def _on_trunk_moved(self, bus_id: str, dy: float):
        """总线主干线被用户拖拽: 原地更新支线和标签位置 (不重建场景)。"""
        info = self._bus_items.get(bus_id)
        if not info:
            return
        new_trunk_y = info["trunk_y0"] + dy
        # 更新支线端点 (设备端不动, 干线端跟随)
        for i, drop in enumerate(info["drops"]):
            drop.setLine(QLineF(info["drop_xs"][i], info["drop_ys"][i],
                                 info["drop_xs"][i], new_trunk_y))
        # 更新标签垂直位置
        info["label"].setPos(info["label"].pos().x(), new_trunk_y - 18)
        # 保存偏移量供后续重建使用
        self._trunk_y_offsets[bus_id] = new_trunk_y - info["avg_y"]

    # ── 选择与交互 ──

    def _on_scene_selection_changed(self):
        selected = self._scene.selectedItems()
        for item in selected:
            if isinstance(item, DeviceRect):
                self.device_selected.emit(item.device_id)
                break

    def mousePressEvent(self, event):
        pos = self.mapToScene(event.pos())
        item = self._scene.itemAt(pos, self.transform())

        if event.button() == Qt.MouseButton.RightButton:
            device_item = self._find_device_at(pos)
            if device_item:
                self._show_device_context_menu(event.pos(), device_item)
                return
            conn_item = self._find_conn_at(pos)
            if conn_item:
                self._remove_connection(conn_item.conn_id)
                return

        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        pos = self.mapToScene(event.pos())
        item = self._scene.itemAt(pos, self.transform())
        while item:
            if isinstance(item, DeviceRect):
                self.device_double_clicked.emit(item.device_id)
                return
            item = item.parentItem()
        super().mouseDoubleClickEvent(event)

    def _find_device_at(self, pos: QPointF) -> DeviceRect | None:
        for item in self._device_items.values():
            if item.contains(item.mapFromScene(pos)):
                return item
        return None

    def _find_conn_at(self, pos: QPointF) -> ConnectionLine | None:
        for item in self._conn_items.values():
            if item.contains(item.mapFromScene(pos)):
                return item
        return None

    def _show_device_context_menu(self, screen_pos, device_item: DeviceRect):
        menu = QMenu(self)
        menu.addAction("删除设备", lambda: self._remove_device(device_item.device_id))
        menu.addSeparator()

        for other in self._device_items.values():
            if other.device_id == device_item.device_id:
                continue
            sub = menu.addMenu(f"连线到 -> {other._label.toPlainText()}")
            device = self._project.find_device(device_item.device_id)
            other_device = self._project.find_device(other.device_id)
            if not device or not other_device:
                continue
            for iface in device.interfaces:
                for other_iface in other_device.interfaces:
                    bc = self._project.find_bus_config(iface.bus_config_id)
                    other_bc = self._project.find_bus_config(other_iface.bus_config_id)
                    bus_type_str = f"{bc.type.value if bc else '?'} -> {other_bc.type.value if other_bc else '?'}"
                    lbl = f"{iface.name} -> {other_iface.name} ({bus_type_str})"
                    sub.addAction(lbl, lambda fi=iface.id, ti=other_iface.id, fn=device.id, tn=other_device.id: self._create_connection(fn, fi, tn, ti))
        menu.exec(self.mapToGlobal(screen_pos))

    def _create_connection(self, from_did, from_iid, to_did, to_iid):
        conn = Connection(from_device_id=from_did, from_interface_id=from_iid,
                          to_device_id=to_did, to_interface_id=to_iid)
        self._project.connections.append(conn)
        self._rebuild_connections()

    def _remove_device(self, device_id: str):
        from PySide6.QtWidgets import QMessageBox
        reply = QMessageBox.question(self, "确认", "确定删除设备？相关连线也会删除。")
        if reply == QMessageBox.StandardButton.Yes:
            self._project.devices = [d for d in self._project.devices if d.id != device_id]
            self._project.connections = [c for c in self._project.connections
                                         if c.from_device_id != device_id and c.to_device_id != device_id]
            self._rebuild()

    def _remove_connection(self, conn_id: str):
        self._project.connections = [c for c in self._project.connections if c.id != conn_id]
        self._rebuild()
