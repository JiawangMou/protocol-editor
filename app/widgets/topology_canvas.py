"""网络拓扑图画布 — 节点绘制 + 手动连线"""
from __future__ import annotations
from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsItem, QGraphicsRectItem, QGraphicsTextItem, QGraphicsLineItem, QGraphicsEllipseItem, QMenu
from PySide6.QtCore import Qt, Signal, QPointF, QRectF, QLineF
from PySide6.QtGui import QPen, QBrush, QColor, QFont, QPainter

from app.models.protocol import Project, Node, Connection, Interface
from app.models.enums import InterfaceType

W = 160
H = 80


class NodeRect(QGraphicsRectItem):
    """A node in the topology view."""

    def __init__(self, node: Node):
        super().__init__(0, 0, W, H)
        self.node_id = node.id
        self._iface_dots: dict[str, QGraphicsEllipseItem] = {}

        self.setPos(node.x, node.y)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setBrush(QBrush(QColor(60, 63, 65)))
        self.setPen(QPen(QColor(120, 180, 240), 2))
        self.setZValue(2)

        self._label = QGraphicsTextItem(node.name, self)
        self._label.setDefaultTextColor(QColor(220, 220, 220))
        self._label.setFont(QFont("Microsoft YaHei", 9))
        self._label.setPos(8, 4)

        # Interface dots
        self.rebuild_ifaces(node.interfaces)

    def rebuild_ifaces(self, interfaces: list[Interface]):
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
            color = {
                InterfaceType.ETHERNET: QColor(100, 200, 100),
                InterfaceType.RS422: QColor(200, 200, 80),
                InterfaceType.RS232: QColor(200, 160, 80),
                InterfaceType.CAN: QColor(200, 100, 80),
                InterfaceType.CANFD: QColor(220, 80, 80),
            }.get(iface.type, QColor(128, 128, 128))
            dot.setBrush(QBrush(color))
            dot.setPen(QPen(color.darker(120), 1))
            dot.setZValue(4)
            dot.setData(0, iface.id)
            dot.setToolTip(f"{iface.name} ({iface.type.value})")
            self._iface_dots[iface.id] = dot

        # Adjust height
        self.setRect(0, 0, W, H + 10)

    def iface_dot_center(self, iface_id: str) -> QPointF:
        dot = self._iface_dots.get(iface_id)
        if dot:
            return self.mapToScene(dot.pos() + QPointF(6, 6))
        return self.mapToScene(QPointF(W / 2, H))

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            from PySide6.QtCore import pyqtSignal
            # let scene handle this
        return super().itemChange(change, value)


class ConnectionLine(QGraphicsLineItem):
    """A connection line between two interface dots."""

    def __init__(self, conn: Connection, from_pos: QPointF, to_pos: QPointF):
        super().__init__()
        self.conn_id = conn.id
        self._from_pos = from_pos
        self._to_pos = to_pos
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


class TopologyCanvas(QGraphicsView):
    node_selected = Signal(str)  # node_id

    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self._project = project
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setMinimumHeight(300)
        self.setStyleSheet("background: #2b2b2b; border: 1px solid #444;")

        self._node_items: dict[str, NodeRect] = {}
        self._conn_items: dict[str, ConnectionLine] = {}
        self._drag_conn: NodeRect | None = None
        self._drag_iface_id: str = ""

        self._scene.selectionChanged.connect(self._on_scene_selection_changed)

    def set_project(self, project: Project):
        self._project = project
        self._rebuild()

    def _rebuild(self):
        self._scene.clear()
        self._node_items.clear()
        self._conn_items.clear()

        for node in self._project.nodes:
            item = NodeRect(node)
            self._scene.addItem(item)
            self._node_items[node.id] = item

        self._rebuild_connections()

    def _rebuild_connections(self):
        for conn in self._project.connections:
            self._add_connection_line(conn)

    def _add_connection_line(self, conn: Connection):
        from_node = self._node_items.get(conn.from_node_id)
        to_node = self._node_items.get(conn.to_node_id)
        if not from_node or not to_node:
            return
        from_pos = from_node.iface_dot_center(conn.from_interface_id)
        to_pos = to_node.iface_dot_center(conn.to_interface_id)
        line = ConnectionLine(conn, from_pos, to_pos)
        self._scene.addItem(line)
        self._conn_items[conn.id] = line

    def _on_scene_selection_changed(self):
        selected = self._scene.selectedItems()
        for item in selected:
            if isinstance(item, NodeRect):
                self.node_selected.emit(item.node_id)
                break

    def mousePressEvent(self, event):
        pos = self.mapToScene(event.pos())
        item = self._scene.itemAt(pos, self.transform())

        if event.button() == Qt.MouseButton.RightButton:
            # Check if we're on a node
            node_item = self._find_node_at(pos)
            if node_item:
                self._show_node_context_menu(event.pos(), node_item)
                return
            # Check if on a connection line
            conn_item = self._find_conn_at(pos)
            if conn_item:
                self._remove_connection(conn_item.conn_id)
                return

        super().mousePressEvent(event)

    def _find_node_at(self, pos: QPointF) -> NodeRect | None:
        for item in self._node_items.values():
            if item.contains(item.mapFromScene(pos)):
                return item
        return None

    def _find_conn_at(self, pos: QPointF) -> ConnectionLine | None:
        for item in self._conn_items.values():
            if item.contains(item.mapFromScene(pos)):
                return item
        return None

    def _show_node_context_menu(self, screen_pos, node_item: NodeRect):
        menu = QMenu(self)
        menu.addAction("删除节点", lambda: self._remove_node(node_item.node_id))
        menu.addSeparator()

        # "Connect to..." submenu
        for other in self._node_items.values():
            if other.node_id == node_item.node_id:
                continue
            sub = menu.addMenu(f"连线到 → {other._label.toPlainText()}")
            node = self._project.find_node(node_item.node_id)
            other_node = self._project.find_node(other.node_id)
            if not node or not other_node:
                continue
            for iface in node.interfaces:
                for other_iface in other_node.interfaces:
                    label = f"{iface.name} → {other_iface.name} ({iface.type.value} → {other_iface.type.value})"
                    sub.addAction(label, lambda fi=iface.id, ti=other_iface.id, fn=node.id, tn=other_node.id: self._create_connection(fn, fi, tn, ti))
        menu.exec(self.mapToGlobal(screen_pos))

    def _create_connection(self, from_nid, from_iid, to_nid, to_iid):
        from app.models.protocol import Connection
        conn = Connection(from_node_id=from_nid, from_interface_id=from_iid,
                          to_node_id=to_nid, to_interface_id=to_iid)
        self._project.connections.append(conn)
        self._rebuild_connections()

    def _remove_node(self, node_id: str):
        from PySide6.QtWidgets import QMessageBox
        reply = QMessageBox.question(self, "确认", "确定删除节点？相关连线也会删除。")
        if reply == QMessageBox.StandardButton.Yes:
            self._project.nodes = [n for n in self._project.nodes if n.id != node_id]
            self._project.connections = [c for c in self._project.connections
                                         if c.from_node_id != node_id and c.to_node_id != node_id]
            self._rebuild()

    def _remove_connection(self, conn_id: str):
        self._project.connections = [c for c in self._project.connections if c.id != conn_id]
        self._rebuild()
