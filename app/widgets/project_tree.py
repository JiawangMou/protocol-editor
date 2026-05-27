"""工程导航树 — 总线级/单机级二层架构"""
from PySide6.QtWidgets import QTreeView, QMenu
from PySide6.QtCore import Qt, Signal, QModelIndex
from PySide6.QtGui import QStandardItemModel, QStandardItem, QAction

from app.models.protocol import Project, Device, DeviceInterface, Protocol, StatusVariable, BusConfig
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
    """工程导航树 — 信号通知主窗口切换属性面板和状态量表。"""
    item_selected = Signal(str, str)  # obj_type, obj_id
    item_double_clicked = Signal(str, str)  # obj_type, obj_id
    add_requested = Signal(str)       # "bus_config" | "device" | "interface" | "status_var" | "protocol"
    delete_requested = Signal()

    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self._project = project
        self._model = QStandardItemModel()
        self.setModel(self._model)
        self.setHeaderHidden(True)
        self.setEditTriggers(QTreeView.EditTrigger.NoEditTriggers)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)
        self.doubleClicked.connect(self._on_double_clicked)
        self.selectionModel().selectionChanged.connect(self._on_selection_changed)

    def refresh(self, project: Project):
        self._project = project
        self._model.clear()
        self._build_tree()

    def _build_tree(self):
        """构建二层树结构: 总线级 (BusConfig) + 单机级 (Device → 状态量/接口 → 协议)。"""
        root = self._model.invisibleRootItem()

        # 工程根节点
        proj_item = self._make_item(f"工程: {self._project.name}", "project", "")
        root.appendRow(proj_item)

        # ── 总线级: 挂载所有 BusConfig ──
        bus_group = self._make_item("总线级", "bus_group", "")
        proj_item.appendRow(bus_group)
        for bc in self._project.bus_configs:
            bc_item = self._make_item(
                f"🚌 {bc.name} [{bc.type.value.upper()}]", "bus_config", bc.id
            )
            bus_group.appendRow(bc_item)

        # ── 单机级: 挂载所有 Device ──
        device_group = self._make_item("单机级", "device_group", "")
        proj_item.appendRow(device_group)
        for device in self._project.devices:
            device_item = self._make_item(f"📦 {device.name}", "device", device.id)
            device_group.appendRow(device_item)

            # 状态量子组
            sv_group = self._make_item(f"📊 状态量 ({len(device.status_variables)})", "sv_group", device.id)
            device_item.appendRow(sv_group)
            for sv in device.status_variables:
                sv_item = self._make_item(f"  {sv.name} [{sv.data_type.value}]", "status_var", sv.id)
                sv_group.appendRow(sv_item)

            # 通讯接口 (通过 bus_config_id 查找总线名称)
            for iface in device.interfaces:
                bc = self._project.find_bus_config(iface.bus_config_id)
                bus_type_name = bc.type.value.upper() if bc else "?"
                iface_type_name = {
                    "ethernet": "🌐", "rs422": "🔌", "rs232": "🔌",
                    "can": "🚌", "canfd": "🚌",
                }.get(bc.type.value if bc else "", "")
                bc_name = f" [{bc.name}]" if bc else ""
                iface_item = self._make_item(
                    f"{iface_type_name} {iface.name}{bc_name} ({bus_type_name})",
                    "interface", iface.id
                )
                iface_item.setData(device.id, Qt.ItemDataRole.UserRole + 1)  # 存储父设备 id 供向上查找
                device_item.appendRow(iface_item)

                # 协议子项
                for proto in iface.protocols:
                    cat_name = CATEGORY_NAMES.get(proto.category, proto.category.value)
                    proto_item = self._make_item(
                        f"📋 {proto.name} ({cat_name})", "protocol", proto.id
                    )
                    proto_item.setData(iface.id, Qt.ItemDataRole.UserRole + 1)  # 存储父接口 id
                    iface_item.appendRow(proto_item)

        self.expandAll()

    def _make_item(self, text: str, obj_type: str, obj_id: str) -> QStandardItem:
        item = QStandardItem(text)
        item.setData(obj_type, Qt.ItemDataRole.UserRole)
        item.setData(obj_id, Qt.ItemDataRole.UserRole + 2)
        return item

    def _get_item_data(self, index: QModelIndex):
        if not index.isValid():
            return None, None
        item = self._model.itemFromIndex(index)
        return item.data(Qt.ItemDataRole.UserRole), item.data(Qt.ItemDataRole.UserRole + 2)

    def _on_double_clicked(self, index: QModelIndex):
        obj_type, obj_id = self._get_item_data(index)
        if obj_type and obj_type not in ("project", "sv_group", "bus_group", "device_group"):
            self.item_double_clicked.emit(obj_type, obj_id)

    def _on_selection_changed(self):
        obj_type, obj_id = self._get_item_data(self.currentIndex())
        # 跳过组节点 (它们不触发属性面板)
        if obj_type and obj_type not in ("project", "sv_group", "bus_group", "device_group"):
            self.item_selected.emit(obj_type, obj_id)

    def current_selection(self):
        return self._get_item_data(self.currentIndex())

    def current_device_id(self) -> str | None:
        """获取当前选中项所属的 Device ID。"""
        obj_type, obj_id = self._get_item_data(self.currentIndex())
        if obj_type == "device":
            return obj_id
        if obj_type in ("interface", "status_var", "protocol", "sv_group"):
            item = self._model.itemFromIndex(self.currentIndex())
            parent = item.parent()
            while parent:
                pt = parent.data(Qt.ItemDataRole.UserRole)
                pid = parent.data(Qt.ItemDataRole.UserRole + 2)
                if pt == "device":
                    return pid
                parent = parent.parent()
        return None

    def current_interface_id(self) -> str | None:
        """获取当前选中项所属的 DeviceInterface ID。"""
        obj_type, obj_id = self._get_item_data(self.currentIndex())
        if obj_type == "interface":
            return obj_id
        if obj_type == "protocol":
            item = self._model.itemFromIndex(self.currentIndex())
            if item:
                return item.data(Qt.ItemDataRole.UserRole + 1)
        return None

    def current_bus_config_id(self) -> str | None:
        obj_type, obj_id = self._get_item_data(self.currentIndex())
        if obj_type == "bus_config":
            return obj_id
        return None

    def select_device(self, device_id: str):
        self._select_by_type_and_id("device", device_id)

    def select_interface(self, iface_id: str):
        self._select_by_type_and_id("interface", iface_id)

    def select_protocol(self, proto_id: str):
        self._select_by_type_and_id("protocol", proto_id)

    def select_bus_config(self, bus_id: str):
        self._select_by_type_and_id("bus_config", bus_id)

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

        if obj_type == "bus_group":
            menu.addAction("添加总线", lambda: self._trigger_add("bus_config"))
        elif obj_type == "device_group":
            menu.addAction("添加单机", lambda: self._trigger_add("device"))
        elif obj_type == "bus_config":
            menu.addAction("删除总线", lambda: self._trigger_delete())
        elif obj_type == "device":
            menu.addAction("添加接口", lambda: self._trigger_add("interface"))
            menu.addAction("添加状态量", lambda: self._trigger_add("status_var"))
            menu.addSeparator()
            menu.addAction("删除单机", lambda: self._trigger_delete())
        elif obj_type == "interface":
            menu.addAction("添加协议", lambda: self._trigger_add("protocol"))
            menu.addSeparator()
            menu.addAction("删除接口", lambda: self._trigger_delete())
        elif obj_type in ("protocol", "status_var"):
            menu.addAction("删除", lambda: self._trigger_delete())

        if not menu.isEmpty():
            menu.exec(self.viewport().mapToGlobal(pos))

    def _trigger_add(self, what: str):
        self.add_requested.emit(what)

    def _trigger_delete(self):
        self.delete_requested.emit()
