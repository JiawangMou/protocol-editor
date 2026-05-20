"""工程导航树"""
from __future__ import annotations
from PySide6.QtWidgets import QTreeView, QMenu
from PySide6.QtCore import Qt, Signal, QModelIndex
from PySide6.QtGui import QStandardItemModel, QStandardItem, QAction

from app.models.protocol import Project, Node, Interface, Protocol, StatusVariable
from app.models.enums import ProtocolCategory

CATEGORY_NAMES = {
    ProtocolCategory.CONTROL_REQUEST: "控制/请求指令",
    ProtocolCategory.PERIODIC_REPORT: "周期上报消息",
    ProtocolCategory.STATUS_CHANGE: "状态变化上报消息",
    ProtocolCategory.EXECUTION_FEEDBACK: "执行结果反馈消息",
}

COMM_METHODS = {
    ProtocolCategory.CONTROL_REQUEST: "请求-应答",
    ProtocolCategory.PERIODIC_REPORT: "周期发送",
    ProtocolCategory.STATUS_CHANGE: "变化触发",
    ProtocolCategory.EXECUTION_FEEDBACK: "应答返回",
}


class ProjectTree(QTreeView):
    item_selected = Signal(str, str)  # obj_type, obj_id

    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self._project = project
        self._model = QStandardItemModel()
        self.setModel(self._model)
        self.setHeaderHidden(True)
        self.setEditTriggers(QTreeView.EditTrigger.NoEditTriggers)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)
        self.selectionModel().selectionChanged.connect(self._on_selection_changed)

    def refresh(self, project: Project):
        self._project = project
        self._model.clear()
        self._build_tree()

    def _build_tree(self):
        root = self._model.invisibleRootItem()

        # Project node
        proj_item = self._make_item(f"工程: {self._project.name}", "project", "")
        root.appendRow(proj_item)

        # Nodes
        for node in self._project.nodes:
            node_item = self._make_item(f"📦 {node.name}", "node", node.id)
            proj_item.appendRow(node_item)

            # Status variable group
            sv_group = self._make_item(f"📊 状态量 ({len(node.status_variables)})", "sv_group", node.id)
            node_item.appendRow(sv_group)
            for sv in node.status_variables:
                sv_item = self._make_item(f"  {sv.name} [{sv.data_type.value}]", "status_var", sv.id)
                sv_group.appendRow(sv_item)

            # Interfaces
            for iface in node.interfaces:
                iface_type_name = {
                    "ethernet": "🌐",
                    "rs422": "🔌",
                    "rs232": "🔌",
                    "can": "🚌",
                    "canfd": "🚌",
                }.get(iface.type.value, "")
                iface_item = self._make_item(
                    f"{iface_type_name} {iface.name} [{iface.type.value.upper()}]",
                    "interface", iface.id
                )
                iface_item.setData(node.id, Qt.ItemDataRole.UserRole + 1)
                node_item.appendRow(iface_item)

                for proto in iface.protocols:
                    cat_name = CATEGORY_NAMES.get(proto.category, proto.category.value)
                    proto_item = self._make_item(
                        f"📋 {proto.name} ({cat_name})", "protocol", proto.id
                    )
                    proto_item.setData(iface.id, Qt.ItemDataRole.UserRole + 1)
                    iface_item.appendRow(proto_item)

        self.expandAll()

    def _make_item(self, text: str, obj_type: str, obj_id: str) -> QStandardItem:
        item = QStandardItem(text)
        item.setData(obj_type, Qt.ItemDataRole.UserRole)  # type
        item.setData(obj_id, Qt.ItemDataRole.UserRole + 2)  # id
        return item

    def _get_item_data(self, index: QModelIndex):
        if not index.isValid():
            return None, None
        item = self._model.itemFromIndex(index)
        return item.data(Qt.ItemDataRole.UserRole), item.data(Qt.ItemDataRole.UserRole + 2)

    def _on_selection_changed(self):
        obj_type, obj_id = self._get_item_data(self.currentIndex())
        if obj_type and obj_type not in ("project", "sv_group"):
            self.item_selected.emit(obj_type, obj_id)

    def current_selection(self):
        return self._get_item_data(self.currentIndex())

    def current_node_id(self) -> str | None:
        obj_type, obj_id = self._get_item_data(self.currentIndex())
        if obj_type == "node":
            return obj_id
        if obj_type in ("interface", "status_var", "protocol", "sv_group"):
            item = self._model.itemFromIndex(self.currentIndex())
            # Walk up to find node
            parent = item.parent()
            while parent:
                pt = parent.data(Qt.ItemDataRole.UserRole)
                pid = parent.data(Qt.ItemDataRole.UserRole + 2)
                if pt == "node":
                    return pid
                parent = parent.parent()
        return None

    def current_interface_id(self) -> str | None:
        obj_type, obj_id = self._get_item_data(self.currentIndex())
        if obj_type == "interface":
            return obj_id
        if obj_type == "protocol":
            item = self._model.itemFromIndex(self.currentIndex())
            if item:
                return item.data(Qt.ItemDataRole.UserRole + 1)
        return None

    def select_node(self, node_id: str):
        self._select_by_type_and_id("node", node_id)

    def select_interface(self, iface_id: str):
        self._select_by_type_and_id("interface", iface_id)

    def select_protocol(self, proto_id: str):
        self._select_by_type_and_id("protocol", proto_id)

    def _select_by_type_and_id(self, obj_type: str, obj_id: str):
        for row in range(self._model.rowCount()):
            parent = self._model.item(row)
            found = self._find_in_item(parent, obj_type, obj_id)
            if found:
                self.setCurrentIndex(found)
                break

    def _find_in_item(self, parent: QStandardItem, obj_type: str, obj_id: str):
        if parent.data(Qt.ItemDataRole.UserRole) == obj_type and parent.data(Qt.ItemDataRole.UserRole + 2) == obj_id:
            return parent.index()
        for row in range(parent.rowCount()):
            child = parent.child(row)
            result = self._find_in_item(child, obj_type, obj_id)
            if result:
                return result
        return None

    def _on_context_menu(self, pos):
        index = self.indexAt(pos)
        obj_type, obj_id = self._get_item_data(index)
        menu = QMenu(self)

        if obj_type in ("project", "node"):
            menu.addAction("添加节点", lambda: self._emit_add("node"))
        if obj_type in ("node",):
            menu.addAction("添加接口", lambda: self._emit_add("interface"))
            menu.addAction("添加状态量", lambda: self._emit_add("status_var"))
        if obj_type in ("interface",):
            menu.addAction("添加协议", lambda: self._emit_add("protocol"))
        if obj_type in ("node", "interface", "protocol", "status_var"):
            menu.addSeparator()
            menu.addAction("删除", lambda: self._emit_delete())

        if not menu.isEmpty():
            menu.exec(self.viewport().mapToGlobal(pos))

    def _emit_add(self, what: str):
        # Emitted via parent's add actions
        pass

    def _emit_delete(self):
        pass
