"""通讯协议编辑器 — 主窗口"""
from __future__ import annotations
from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QMenuBar, QToolBar, QStatusBar, QDockWidget, QWidget,
    QVBoxLayout, QHBoxLayout, QSplitter, QFileDialog, QMessageBox, QLabel, QPlainTextEdit,
    QInputDialog, QStackedWidget,
)
from PySide6.QtCore import Qt, QSettings, Signal
from PySide6.QtGui import QAction, QKeySequence

from app.models.protocol import Project, Device, DeviceInterface, BusConfig
from app.models.enums import InterfaceType
from app.utils.serializer import save_project, load_project
from app.widgets.project_tree import ProjectTree
from app.widgets.property_panel import PropertyPanel
from app.widgets.topology_canvas import TopologyCanvas
from app.widgets.status_table import StatusTable
from app.widgets.protocol_editor import ProtocolContentEditor


class MainWindow(QMainWindow):
    project_changed = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("通讯协议编辑器")
        self._project: Project = Project()
        self._current_file: str | None = None
        self._dirty: bool = False
        self._settings = QSettings("ProtocolEditor", "CommProtocolEditor")

        self._setup_menu()
        self._setup_toolbar()
        self._setup_central()
        self._setup_docks()
        self._setup_statusbar()

        self.project_changed.connect(self._on_project_changed)
        self._init_new_project()

    # ── Menu ──
    def _setup_menu(self):
        mb = self.menuBar()

        # File
        file_menu = mb.addMenu("文件(&F)")
        self.act_new = QAction("新建工程(&N)", self)
        self.act_new.setShortcut(QKeySequence.StandardKey.New)
        self.act_new.triggered.connect(self._new_project)
        file_menu.addAction(self.act_new)

        self.act_open = QAction("打开工程(&O)...", self)
        self.act_open.setShortcut(QKeySequence.StandardKey.Open)
        self.act_open.triggered.connect(self._open_project)
        file_menu.addAction(self.act_open)

        self.act_save = QAction("保存(&S)", self)
        self.act_save.setShortcut(QKeySequence.StandardKey.Save)
        self.act_save.triggered.connect(self._save_project)
        file_menu.addAction(self.act_save)

        self.act_save_as = QAction("另存为(&A)...", self)
        self.act_save_as.setShortcut(QKeySequence.StandardKey.SaveAs)
        self.act_save_as.triggered.connect(self._save_as_project)
        file_menu.addAction(self.act_save_as)

        file_menu.addSeparator()

        self.act_exit = QAction("退出(&X)", self)
        self.act_exit.triggered.connect(self.close)
        file_menu.addAction(self.act_exit)

        # Edit
        edit_menu = mb.addMenu("编辑(&E)")
        self.act_add_bus = QAction("添加总线", self)
        self.act_add_bus.triggered.connect(self._add_bus_config)
        edit_menu.addAction(self.act_add_bus)

        self.act_add_device = QAction("添加设备", self)
        self.act_add_device.triggered.connect(self._add_device)
        edit_menu.addAction(self.act_add_device)

        self.act_add_interface = QAction("添加接口", self)
        self.act_add_interface.triggered.connect(self._add_interface)
        edit_menu.addAction(self.act_add_interface)

        self.act_add_status_var = QAction("添加状态量", self)
        self.act_add_status_var.triggered.connect(self._add_status_var)
        edit_menu.addAction(self.act_add_status_var)

        self.act_add_protocol = QAction("添加协议", self)
        self.act_add_protocol.triggered.connect(self._add_protocol)
        edit_menu.addAction(self.act_add_protocol)

        edit_menu.addSeparator()
        self.act_delete_item = QAction("删除选中项", self)
        self.act_delete_item.setShortcut(QKeySequence.StandardKey.Delete)
        self.act_delete_item.triggered.connect(self._delete_selected)
        edit_menu.addAction(self.act_delete_item)

        # View
        self._view_menu = mb.addMenu("视图(&V)")

        # Tools
        tools_menu = mb.addMenu("工具(&T)")
        self.act_export_word = QAction("导出 Word 文档...", self)
        self.act_export_word.triggered.connect(self._export_word)
        tools_menu.addAction(self.act_export_word)

        # Help
        help_menu = mb.addMenu("帮助(&H)")
        self.act_about = QAction("关于", self)
        self.act_about.triggered.connect(self._about)
        help_menu.addAction(self.act_about)

    # ── Toolbar ──
    def _setup_toolbar(self):
        tb = QToolBar("主工具栏")
        tb.setMovable(False)
        self.addToolBar(tb)
        tb.addAction(self.act_new)
        tb.addAction(self.act_open)
        tb.addAction(self.act_save)
        tb.addSeparator()
        tb.addAction(self.act_add_bus)
        tb.addAction(self.act_add_device)
        tb.addAction(self.act_add_interface)
        tb.addAction(self.act_add_status_var)
        tb.addAction(self.act_add_protocol)
        tb.addSeparator()
        tb.addAction(self.act_export_word)

    # ── Central widget ──
    def _setup_central(self):
        self._central_stack = QStackedWidget()
        self.setCentralWidget(self._central_stack)

        # Page 0: 欢迎页
        welcome = QLabel("双击左侧工程树中的协议对象开始编辑协议内容\n\n"
                          "或使用编辑菜单添加总线、设备、接口、状态量和协议。")
        welcome.setAlignment(Qt.AlignmentFlag.AlignCenter)
        welcome.setStyleSheet("color: #888; font-size: 14px;")
        self._central_stack.addWidget(welcome)

        # Page 1: 协议内容编辑器
        self._proto_editor = ProtocolContentEditor()
        self._proto_editor.saved.connect(self._on_protocol_saved)
        self._proto_editor.cancelled.connect(self._on_protocol_cancelled)
        self._central_stack.addWidget(self._proto_editor)

    # ── Docks ──
    def _setup_docks(self):
        # Top: topology canvas (可关闭的总线拓扑图)
        self._topo_dock = QDockWidget("总线拓扑图", self)
        self._topology = TopologyCanvas(self._project)
        self._topology.device_selected.connect(self._on_device_selected)
        self._topology.device_double_clicked.connect(self._on_device_double_clicked)
        self._topo_dock.setWidget(self._topology)
        self._topo_dock.setMinimumHeight(200)
        self.addDockWidget(Qt.DockWidgetArea.TopDockWidgetArea, self._topo_dock)

        # Left: project tree
        self._tree_dock = QDockWidget("工程导航", self)
        self._tree = ProjectTree(self._project)
        self._tree.item_selected.connect(self._on_tree_selection)
        self._tree.item_double_clicked.connect(self._on_tree_double_clicked)
        self._tree.add_requested.connect(self._on_tree_add)
        self._tree.delete_requested.connect(self._delete_selected)
        self._tree_dock.setWidget(self._tree)
        self._tree_dock.setMinimumWidth(260)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._tree_dock)

        # Right: property panel
        self._prop_dock = QDockWidget("属性编辑器", self)
        self._prop_panel = PropertyPanel()
        self._prop_panel.data_modified.connect(self._on_property_modified)
        self._prop_dock.setWidget(self._prop_panel)
        self._prop_dock.setMinimumWidth(320)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._prop_dock)

        # Bottom: status table
        self._status_dock = QDockWidget("状态量管理", self)
        self._status_table = StatusTable(self._project)
        self._status_table.data_modified.connect(self._on_status_modified)
        self._status_dock.setWidget(self._status_table)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self._status_dock)

        # Bottom: log
        self._log_dock = QDockWidget("输出日志", self)
        self._log_widget = QPlainTextEdit()
        self._log_widget.setReadOnly(True)
        self._log_widget.setMaximumBlockCount(1000)
        self._log_dock.setWidget(self._log_widget)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self._log_dock)

        # Tabify status and log
        self.tabifyDockWidget(self._status_dock, self._log_dock)
        self._status_dock.raise_()

        # 注册各面板的 "视图" 菜单切换动作 (关闭后可重新打开)
        self._view_menu.addAction(self._topo_dock.toggleViewAction())
        self._view_menu.addAction(self._tree_dock.toggleViewAction())
        self._view_menu.addAction(self._prop_dock.toggleViewAction())
        self._view_menu.addAction(self._status_dock.toggleViewAction())
        self._view_menu.addAction(self._log_dock.toggleViewAction())

    def _setup_statusbar(self):
        sb = QStatusBar()
        self._status_label = QLabel("就绪")
        sb.addWidget(self._status_label)
        self.setStatusBar(sb)

    # ── Slots ──
    def _new_project(self):
        if not self._maybe_save():
            return
        name, ok = QInputDialog.getText(
            self, "新建工程", "请输入工程名称:", text="新工程"
        )
        if not ok or not name.strip():
            return
        self._project = Project(name=name.strip(), version="1.0", author="")
        self._current_file = None
        self._refresh_all()
        self._log(f"新建工程: {name.strip()}")
        self._save_as_project()

    def _init_new_project(self, name="新工程"):
        self._project = Project(name=name, version="1.0", author="")
        self._current_file = None
        self._refresh_all()
        self._dirty = False
        self._update_title()
        self._log(f"新建工程: {name}")

    def _open_project(self):
        if not self._maybe_save():
            return
        last_dir = self._settings.value("last_dir", str(Path.home()))
        path, _ = QFileDialog.getOpenFileName(
            self, "打开工程", last_dir, "协议工程文件 (*.commproj);;所有文件 (*.*)"
        )
        if not path:
            return
        try:
            self._project = load_project(path)
            self._current_file = path
            self._settings.setValue("last_dir", str(Path(path).parent))
            self._add_recent(path)
            self._refresh_all()
            self._dirty = False
            self._update_title()
            self._log(f"已打开: {path}")
        except Exception as e:
            QMessageBox.critical(self, "打开失败", f"无法打开工程文件:\n{e}")

    def _save_project(self):
        if self._current_file:
            try:
                save_project(self._project, self._current_file)
                self._dirty = False
                self._update_title()
                self._log(f"已保存: {self._current_file}")
            except Exception as e:
                QMessageBox.critical(self, "保存失败", str(e))
        else:
            self._save_as_project()

    def _save_as_project(self):
        last_dir = self._settings.value("last_dir", str(Path.home()))
        path, _ = QFileDialog.getSaveFileName(
            self, "另存为", f"{last_dir}/{self._project.name}.commproj",
            "协议工程文件 (*.commproj);;所有文件 (*.*)"
        )
        if not path:
            return
        try:
            save_project(self._project, path)
            self._current_file = path
            self._settings.setValue("last_dir", str(Path(path).parent))
            self._add_recent(path)
            self._dirty = False
            self._update_title()
            self._log(f"已保存: {path}")
        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e))

    def _maybe_save(self) -> bool:
        return True

    def _add_recent(self, path: str):
        recent = self._settings.value("recent_files", [])
        if not isinstance(recent, list):
            recent = []
        if path in recent:
            recent.remove(path)
        recent.insert(0, path)
        self._settings.setValue("recent_files", recent[:10])

    def _on_project_changed(self):
        self._update_title()

    def _update_title(self):
        dirty = "*" if self._dirty else ""
        self.setWindowTitle(f"通讯协议编辑器 — {self._project.name}{dirty}")

    def _on_tree_selection(self, obj_type: str, obj_id: str):
        """工程树选择变更 → 同步属性面板和状态量表。"""
        self._prop_panel.show_object(self._project, obj_type, obj_id)
        self._status_table.set_current_node_by_selection(obj_type, obj_id)

    def _on_device_selected(self, device_id: str):
        """拓扑图中设备被点击时: 同步树选中、状态量表和属性面板。"""
        self._tree.select_device(device_id)
        self._status_table.set_current_device(device_id)
        self._prop_panel.show_object(self._project, "device", device_id)

    def _on_property_modified(self):
        self._refresh_all()

    def _on_status_modified(self):
        self._refresh_all()

    def _on_tree_double_clicked(self, obj_type: str, obj_id: str):
        """工程树双击: 协议对象 → 在中心区域打开内容编辑表格。"""
        if obj_type == "protocol":
            device = self._project.find_parent_device_of_protocol(obj_id)
            proto = self._project.find_protocol(obj_id)
            if device and proto:
                self._proto_editor.set_protocol(self._project, proto, device)
                self._central_stack.setCurrentIndex(1)
            else:
                QMessageBox.warning(self, "错误", "无法找到协议或其所属设备。")

    def _on_protocol_saved(self):
        """协议内容保存 — 刷新工程树和属性面板 (协议字段数量可能变化)。"""
        self._refresh_all()
        self._log("协议内容已保存")

    def _on_protocol_cancelled(self):
        """协议编辑取消 — 回到欢迎页。"""
        self._central_stack.setCurrentIndex(0)

    def _on_tree_add(self, what: str):
        """右键菜单添加操作转发。"""
        dispatch = {
            "bus_config": self._add_bus_config,
            "device": self._add_device,
            "interface": self._add_interface,
            "status_var": self._add_status_var,
            "protocol": self._add_protocol,
        }
        action = dispatch.get(what)
        if action:
            action()

    def _on_device_double_clicked(self, device_id: str):
        """拓扑图中双击设备 → 弹出对话框编辑设备名称。"""
        device = self._project.find_device(device_id)
        if not device:
            return
        name, ok = QInputDialog.getText(
            self, "编辑设备名称", "设备名称:", text=device.name
        )
        if ok and name.strip():
            device.name = name.strip()
            self._refresh_all()
            self._log(f"设备重命名: {name.strip()}")

    # ── 编辑操作: 添加总线/设备/接口/状态量/协议 ──

    def _add_bus_config(self):
        """添加总线配置并在树中选中, 默认命名为 '总线N'。"""
        bc = BusConfig(name=f"总线{len(self._project.bus_configs) + 1}")
        self._project.bus_configs.append(bc)
        self._refresh_all()
        self._tree.select_bus_config(bc.id)
        self._log(f"添加总线: {bc.name}")

    def _add_device(self):
        """添加设备 (单机), 按两行排列 — 上行→下行, 左→右。两行中间为总线区域。"""
        d = Device(name=f"设备{len(self._project.devices) + 1}")
        idx = len(self._project.devices)
        row = idx % 2       # 0 = 上行, 1 = 下行
        col = idx // 2
        d.x = 100 + col * 180
        d.y = 80 if row == 0 else 330
        self._project.devices.append(d)
        self._refresh_all()
        self._tree.select_device(d.id)
        self._log(f"添加设备: {d.name}")

    def _add_interface(self):
        """为当前选中的设备添加通讯接口。弹出总线选择对话框, 默认绑定第一个总线。"""
        current_device_id = self._tree.current_device_id()
        device = self._project.find_device(current_device_id) if current_device_id else None
        if device is None:
            QMessageBox.information(self, "提示", "请先在工程树中选择一个设备。")
            return
        if not self._project.bus_configs:
            QMessageBox.information(self, "提示", "请先添加总线配置, 接口需要绑定到总线。")
            return

        # 弹窗选择总线 (当存在多条总线时让用户选择, 避免都默认绑定第一条)
        chosen_bus_id = self._project.bus_configs[0].id
        if len(self._project.bus_configs) > 1:
            bus_names = [f"{bc.name} ({bc.type.value.upper()})" for bc in self._project.bus_configs]
            bus_name, ok = QInputDialog.getItem(
                self, "选择总线", "请选择要绑定的总线:", bus_names, 0, False
            )
            if not ok:
                return
            idx = bus_names.index(bus_name)
            chosen_bus_id = self._project.bus_configs[idx].id

        iface = DeviceInterface(name="新接口")
        iface.bus_config_id = chosen_bus_id
        device.interfaces.append(iface)
        self._refresh_all()
        self._tree.select_interface(iface.id)
        self._log(f"添加接口: {iface.name} -> {device.name}")

    def _add_status_var(self):
        """为当前选中设备添加状态量。"""
        current_device_id = self._tree.current_device_id()
        device = self._project.find_device(current_device_id) if current_device_id else None
        if device is None:
            QMessageBox.information(self, "提示", "请先在工程树中选择一个设备。")
            return
        from app.models.protocol import StatusVariable
        sv = StatusVariable(name=f"状态量{len(device.status_variables) + 1}")
        device.status_variables.append(sv)
        self._refresh_all()
        self._log(f"添加状态量: {sv.name} -> {device.name}")

    def _add_protocol(self):
        """为当前选中接口添加协议, 默认使用 UART 帧格式。"""
        current_iface_id = self._tree.current_interface_id()
        if current_iface_id is None:
            QMessageBox.information(self, "提示", "请先在工程树中选择一个接口。")
            return
        result = self._project.find_interface(current_iface_id)
        if result is None:
            return
        _, iface = result
        from app.models.protocol import Protocol, UARTFrameConfig
        proto = Protocol(
            name=f"协议{len(iface.protocols) + 1}",
            frame_config=UARTFrameConfig(),
        )
        iface.protocols.append(proto)
        self._refresh_all()
        self._tree.select_protocol(proto.id)
        self._log(f"添加协议: {proto.name} -> {iface.name}")

    def _delete_selected(self):
        """删除树中当前选中的对象 (总线/设备/接口/协议/状态量)。
        删除总线时检查是否有接口引用, 删除设备时级联删除相关连线。"""
        obj_type, obj_id = self._tree.current_selection()
        if obj_type is None:
            return
        try:
            if obj_type == "bus_config":
                # 检查接口引用 — 有引用则禁止删除
                refs = []
                for d in self._project.devices:
                    for iface in d.interfaces:
                        if iface.bus_config_id == obj_id:
                            refs.append(f"{d.name}/{iface.name}")
                if refs:
                    QMessageBox.warning(self, "无法删除",
                        f"该总线被以下接口引用, 请先修改接口绑定:\n" + "\n".join(refs))
                    return
                self._project.bus_configs = [bc for bc in self._project.bus_configs if bc.id != obj_id]
            elif obj_type == "device":
                # 删除设备同时删除相关连线
                self._project.devices = [d for d in self._project.devices if d.id != obj_id]
                self._project.connections = [
                    c for c in self._project.connections
                    if c.from_device_id != obj_id and c.to_device_id != obj_id
                ]
            elif obj_type == "interface":
                for d in self._project.devices:
                    d.interfaces = [i for i in d.interfaces if i.id != obj_id]
                self._project.connections = [
                    c for c in self._project.connections
                    if c.from_interface_id != obj_id and c.to_interface_id != obj_id
                ]
            elif obj_type == "protocol":
                for d in self._project.devices:
                    for i in d.interfaces:
                        i.protocols = [p for p in i.protocols if p.id != obj_id]
            elif obj_type == "status_var":
                for d in self._project.devices:
                    d.status_variables = [sv for sv in d.status_variables if sv.id != obj_id]
            self._refresh_all()
            self._log(f"已删除: {obj_type} {obj_id}")
        except Exception as e:
            QMessageBox.critical(self, "删除失败", str(e))

    def _export_word(self):
        from app.generators.docx_generator import generate_docx
        last_dir = self._settings.value("last_dir", str(Path.home()))
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 Word 文档", f"{last_dir}/{self._project.name}_协议文档.docx",
            "Word 文档 (*.docx)"
        )
        if not path:
            return
        try:
            generate_docx(self._project, path)
            self._log(f"Word 文档已导出: {path}")
            QMessageBox.information(self, "导出成功", f"文档已保存到:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))

    def _about(self):
        QMessageBox.about(self, "关于", "通讯协议编辑器 v2.0\n\n辅助设计分布式通讯系统应用层协议。")

    # ── Helpers ──
    def _refresh_all(self):
        self._dirty = True
        self._tree.refresh(self._project)
        self._topology.set_project(self._project)
        self._status_table.set_project(self._project)
        self.project_changed.emit()

    def _log(self, msg: str):
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S")
        self._log_widget.appendPlainText(f"[{ts}] {msg}")
