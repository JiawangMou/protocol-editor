"""通讯协议编辑器 — 主窗口"""
from __future__ import annotations
from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QMenuBar, QToolBar, QStatusBar, QDockWidget, QWidget,
    QVBoxLayout, QHBoxLayout, QSplitter, QFileDialog, QMessageBox, QLabel, QPlainTextEdit,
)
from PySide6.QtCore import Qt, QSettings, Signal
from PySide6.QtGui import QAction, QKeySequence

from app.models.protocol import Project
from app.utils.serializer import save_project, load_project
from app.widgets.project_tree import ProjectTree
from app.widgets.property_panel import PropertyPanel
from app.widgets.topology_canvas import TopologyCanvas
from app.widgets.status_table import StatusTable
from app.widgets.protocol_editor import ProtocolEditor


class MainWindow(QMainWindow):
    project_changed = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("通讯协议编辑器")
        self._project: Project = Project()
        self._current_file: str | None = None
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
        self.act_add_node = QAction("添加节点", self)
        self.act_add_node.triggered.connect(self._add_node)
        edit_menu.addAction(self.act_add_node)

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
        tb.addAction(self.act_add_node)
        tb.addAction(self.act_add_interface)
        tb.addAction(self.act_add_status_var)
        tb.addAction(self.act_add_protocol)
        tb.addSeparator()
        tb.addAction(self.act_export_word)

    # ── Central widget ──
    def _setup_central(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)

        self._topology = TopologyCanvas(self._project)
        self._topology.node_selected.connect(self._on_node_selected)
        layout.addWidget(self._topology)

    # ── Docks ──
    def _setup_docks(self):
        # Left: project tree
        self._tree_dock = QDockWidget("工程导航", self)
        self._tree = ProjectTree(self._project)
        self._tree.item_selected.connect(self._on_tree_selection)
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

    def _setup_statusbar(self):
        sb = QStatusBar()
        self._status_label = QLabel("就绪")
        sb.addWidget(self._status_label)
        self.setStatusBar(sb)

    # ── Slots ──
    def _new_project(self):
        if self._maybe_save():
            self._init_new_project()

    def _init_new_project(self):
        self._project = Project(name="新工程", version="1.0", author="")
        self._current_file = None
        self._refresh_all()
        self._log("新建工程")

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
            self._log(f"已打开: {path}")
        except Exception as e:
            QMessageBox.critical(self, "打开失败", f"无法打开工程文件:\n{e}")

    def _save_project(self):
        if self._current_file:
            try:
                save_project(self._project, self._current_file)
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
            self._log(f"已保存: {path}")
        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e))

    def _maybe_save(self) -> bool:
        # Simple check; could track dirty state
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
        self.setWindowTitle(f"通讯协议编辑器 — {self._project.name}*")

    def _on_tree_selection(self, obj_type: str, obj_id: str):
        """Handle selection from project tree."""
        self._prop_panel.show_object(self._project, obj_type, obj_id)
        self._status_table.set_current_node_by_selection(obj_type, obj_id)

    def _on_node_selected(self, node_id: str):
        self._tree.select_node(node_id)
        self._status_table.set_current_node(node_id)

    def _on_property_modified(self):
        self._refresh_all()

    def _on_status_modified(self):
        self._refresh_all()

    def _add_node(self):
        from app.models.protocol import Node
        n = Node(name=f"节点{len(self._project.nodes) + 1}")
        n.x = 100 + len(self._project.nodes) * 180
        n.y = 200
        self._project.nodes.append(n)
        self._refresh_all()
        self._log(f"添加节点: {n.name}")

    def _add_interface(self):
        current_node_id = self._tree.current_node_id()
        node = self._project.find_node(current_node_id) if current_node_id else None
        if node is None:
            QMessageBox.information(self, "提示", "请先在工程树中选择一个节点。")
            return
        from app.models.protocol import Interface, RS422Params
        iface = Interface(name="新接口", params=RS422Params())
        node.interfaces.append(iface)
        self._refresh_all()
        self._tree.select_interface(iface.id)
        self._log(f"添加接口: {iface.name} → {node.name}")

    def _add_status_var(self):
        current_node_id = self._tree.current_node_id()
        node = self._project.find_node(current_node_id) if current_node_id else None
        if node is None:
            QMessageBox.information(self, "提示", "请先在工程树中选择一个节点。")
            return
        from app.models.protocol import StatusVariable
        sv = StatusVariable(name=f"状态量{len(node.status_variables) + 1}")
        node.status_variables.append(sv)
        self._refresh_all()
        self._log(f"添加状态量: {sv.name} → {node.name}")

    def _add_protocol(self):
        current_iface_id = self._tree.current_interface_id()
        if current_iface_id is None:
            QMessageBox.information(self, "提示", "请先在工程树中选择一个接口。")
            return
        result = self._project.find_interface(current_iface_id)
        if result is None:
            return
        node, iface = result
        from app.models.protocol import Protocol, UARTFrameConfig
        proto = Protocol(
            name=f"协议{len(iface.protocols) + 1}",
            frame_config=UARTFrameConfig(),
        )
        iface.protocols.append(proto)
        self._refresh_all()
        self._tree.select_protocol(proto.id)
        self._log(f"添加协议: {proto.name} → {iface.name}")

    def _delete_selected(self):
        obj_type, obj_id = self._tree.current_selection()
        if obj_type is None:
            return
        try:
            if obj_type == "node":
                self._project.nodes = [n for n in self._project.nodes if n.id != obj_id]
                self._project.connections = [
                    c for c in self._project.connections
                    if c.from_node_id != obj_id and c.to_node_id != obj_id
                ]
            elif obj_type == "interface":
                for n in self._project.nodes:
                    n.interfaces = [i for i in n.interfaces if i.id != obj_id]
                self._project.connections = [
                    c for c in self._project.connections
                    if c.from_interface_id != obj_id and c.to_interface_id != obj_id
                ]
            elif obj_type == "protocol":
                for n in self._project.nodes:
                    for i in n.interfaces:
                        i.protocols = [p for p in i.protocols if p.id != obj_id]
            elif obj_type == "status_var":
                for n in self._project.nodes:
                    n.status_variables = [sv for sv in n.status_variables if sv.id != obj_id]
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
        QMessageBox.about(self, "关于", "通讯协议编辑器 v1.0\n\n辅助设计分布式通讯系统应用层协议。")

    # ── Helpers ──
    def _refresh_all(self):
        self._tree.refresh(self._project)
        self._topology.set_project(self._project)
        self._status_table.set_project(self._project)
        self.project_changed.emit()

    def _log(self, msg: str):
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S")
        self._log_widget.appendPlainText(f"[{ts}] {msg}")
