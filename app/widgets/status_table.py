"""状态量管理表格"""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableView, QHeaderView,
    QPushButton, QComboBox, QSpinBox, QLineEdit, QMessageBox,
    QStyledItemDelegate, QStyleOptionViewItem,
)
from PySide6.QtCore import Qt, Signal, QAbstractTableModel, QModelIndex

from app.models.protocol import Project, Node, StatusVariable
from app.models.enums import DataType


class StatusTableModel(QAbstractTableModel):
    COLUMNS = ["名称", "数据类型", "字节长度", "单位", "含义", "备注", "引用"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._node: Node | None = None
        self._project: Project | None = None

    def set_data(self, project: Project, node: Node | None):
        self.beginResetModel()
        self._project = project
        self._node = node
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return len(self._node.status_variables) if self._node else 0

    def columnCount(self, parent=QModelIndex()):
        return len(self.COLUMNS)

    def headerData(self, section, orientation, role):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.COLUMNS[section]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not self._node or not self._project:
            return None
        sv = self._node.status_variables[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return sv.name
            elif col == 1:
                return sv.data_type.value
            elif col == 2:
                return str(sv.byte_length)
            elif col == 3:
                return sv.unit
            elif col == 4:
                return sv.meaning
            elif col == 5:
                return sv.remarks
            elif col == 6:
                return str(self._project.status_var_ref_count(sv.id))

        elif role == Qt.ItemDataRole.EditRole:
            if col == 0:
                return sv.name
            elif col == 1:
                return sv.data_type.value
            elif col == 2:
                return sv.byte_length
            elif col == 3:
                return sv.unit
            elif col == 4:
                return sv.meaning
            elif col == 5:
                return sv.remarks

        return None

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if not self._node or role != Qt.ItemDataRole.EditRole:
            return False
        sv = self._node.status_variables[index.row()]
        col = index.column()

        if col == 0:
            sv.name = value
        elif col == 1:
            try:
                sv.data_type = DataType(value)
            except ValueError:
                pass
        elif col == 2:
            try:
                sv.byte_length = int(value)
            except ValueError:
                pass
        elif col == 3:
            sv.unit = value
        elif col == 4:
            sv.meaning = value
        elif col == 5:
            sv.remarks = value
        else:
            return False

        self.dataChanged.emit(index, index)
        return True

    def flags(self, index):
        if index.column() == 6:
            return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEditable


class DataTypeDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        cb = QComboBox(parent)
        cb.addItems([dt.value for dt in DataType])
        return cb

    def setEditorData(self, editor, index):
        val = index.data(Qt.ItemDataRole.EditRole)
        idx = editor.findText(val)
        if idx >= 0:
            editor.setCurrentIndex(idx)

    def setModelData(self, editor, model, index):
        model.setData(index, editor.currentText())


class StatusTable(QWidget):
    data_modified = Signal()

    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self._project = project

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # Toolbar
        tb = QHBoxLayout()
        tb.addWidget(QPushButton("➕ 添加状态量"))

        self._node_label = QLineEdit()
        self._node_label.setReadOnly(True)
        self._node_label.setMaximumWidth(200)
        self._node_label.setStyleSheet("background: #3b3b3b; border: 1px solid #555; color: #ccc;")
        tb.addWidget(self._node_label)

        self._btn_add = tb.itemAt(0).widget()
        self._btn_add.clicked.connect(self._add_status_var)

        self._btn_del = QPushButton("🗑 删除选中")
        self._btn_del.clicked.connect(self._del_status_var)
        tb.addWidget(self._btn_del)

        tb.addStretch()
        layout.addLayout(tb)

        # Table
        self._model = StatusTableModel()
        self._table = QTableView()
        self._table.setModel(self._model)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._table.setItemDelegateForColumn(1, DataTypeDelegate(self._table))
        self._table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        layout.addWidget(self._table)

    def set_project(self, project: Project):
        self._project = project
        self._model.set_data(project, self._model._node)
        self._model.layoutChanged.emit()

    def set_current_node(self, node_id: str):
        node = self._project.find_node(node_id)
        self._model.set_data(self._project, node)
        self._node_label.setText(f"节点: {node.name}" if node else "")
        self._model.layoutChanged.emit()

    def set_current_node_by_selection(self, obj_type: str, obj_id: str):
        """Infer the node from a tree selection."""
        if obj_type == "node":
            self.set_current_node(obj_id)
        elif obj_type in ("interface", "protocol", "status_var"):
            node = self._project.find_node(obj_id)
            if node is None:
                # Need to search
                for n in self._project.nodes:
                    for iface in n.interfaces:
                        if iface.id == obj_id:
                            self.set_current_node(n.id)
                            return
                        for proto in iface.protocols:
                            if proto.id == obj_id:
                                self.set_current_node(n.id)
                                return
                    for sv in n.status_variables:
                        if sv.id == obj_id:
                            self.set_current_node(n.id)
                            return

    def _add_status_var(self):
        if not self._model._node:
            QMessageBox.information(self, "提示", "请先在工程树中选择一个节点。")
            return
        sv = StatusVariable(name=f"状态量{len(self._model._node.status_variables) + 1}")
        self._model._node.status_variables.append(sv)
        self._model.layoutChanged.emit()
        self.data_modified.emit()

    def _del_status_var(self):
        idx = self._table.currentIndex()
        if not idx.isValid() or not self._model._node:
            return
        sv = self._model._node.status_variables[idx.row()]
        ref_count = self._project.status_var_ref_count(sv.id)
        if ref_count > 0:
            reply = QMessageBox.warning(
                self, "警告",
                f"状态量 \"{sv.name}\" 被 {ref_count} 个协议字段引用，删除后引用将失效。确定删除？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        self._model._node.status_variables.pop(idx.row())
        self._model.layoutChanged.emit()
        self.data_modified.emit()
