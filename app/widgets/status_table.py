"""状态量管理表格

使用 QAbstractTableModel + QTableView 实现可编辑的状态量列表。
编辑时直接写回数据模型, 添加/删除后通过 beginResetModel/endResetModel
通知视图刷新, 避免直接调用 layoutChanged.emit() 可能导致的状态不一致。
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableView, QHeaderView,
    QPushButton, QComboBox, QSpinBox, QLineEdit, QMessageBox,
    QStyledItemDelegate, QStyleOptionViewItem,
)
from PySide6.QtCore import Qt, Signal, QAbstractTableModel, QModelIndex

from app.models.protocol import Project, Device, StatusVariable, DATA_TYPE_BYTE_SIZES
from app.models.enums import DataType


class StatusTableModel(QAbstractTableModel):
    COLUMNS = ["名称", "数据类型", "字节长度", "单位", "含义", "备注", "引用"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._device: Device | None = None
        self._project: Project | None = None

    def set_data(self, project: Project, device: Device | None):
        self.beginResetModel()
        self._project = project
        self._device = device
        self.endResetModel()

    def notify_changed(self):
        self.beginResetModel()
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return len(self._device.status_variables) if self._device else 0

    def columnCount(self, parent=QModelIndex()):
        return len(self.COLUMNS)

    def headerData(self, section, orientation, role):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.COLUMNS[section]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not self._device or not self._project:
            return None
        sv = self._device.status_variables[index.row()]
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
        if not self._device or role != Qt.ItemDataRole.EditRole:
            return False
        sv = self._device.status_variables[index.row()]
        col = index.column()

        if col == 0:
            sv.name = value
        elif col == 1:
            try:
                sv.data_type = DataType(value)
                # 自动根据数据类型设置字节长度
                auto_size = DATA_TYPE_BYTE_SIZES.get(sv.data_type)
                if auto_size is not None:
                    sv.byte_length = auto_size
                # 同时通知字节长度列刷新
                len_index = self.index(index.row(), 2)
                self.dataChanged.emit(len_index, len_index)
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
    status_var_edited = Signal(str)  # 携带被编辑状态量的 id

    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self._project = project

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        tb = QHBoxLayout()
        tb.addWidget(QPushButton("添加状态量"))

        self._device_label = QLineEdit()
        self._device_label.setReadOnly(True)
        self._device_label.setMaximumWidth(200)
        self._device_label.setStyleSheet("background: #3b3b3b; border: 1px solid #555; color: #ccc;")
        tb.addWidget(self._device_label)

        self._btn_add = tb.itemAt(0).widget()
        self._btn_add.clicked.connect(self._add_status_var)

        self._btn_del = QPushButton("删除选中")
        self._btn_del.clicked.connect(self._del_status_var)
        tb.addWidget(self._btn_del)

        tb.addStretch()
        layout.addLayout(tb)

        self._model = StatusTableModel()
        self._model.dataChanged.connect(self._on_model_data_changed)
        self._table = QTableView()
        self._table.setModel(self._model)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._table.setItemDelegateForColumn(1, DataTypeDelegate(self._table))
        self._table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        layout.addWidget(self._table)

    def set_project(self, project: Project):
        self._project = project
        self._model.set_data(project, self._model._device)

    def set_current_device(self, device_id: str):
        """切换到指定设备, 显示其状态量列表。"""
        device = self._project.find_device(device_id)
        self._model.set_data(self._project, device)
        self._device_label.setText(f"设备: {device.name}" if device else "")

    def set_current_node_by_selection(self, obj_type: str, obj_id: str):
        """从树选择推断所属 Device 并切换。"""
        if obj_type == "device":
            self.set_current_device(obj_id)
        elif obj_type in ("interface", "protocol", "status_var"):
            device = None
            for d in self._project.devices:
                for iface in d.interfaces:
                    if iface.id == obj_id:
                        device = d
                        break
                    for proto in iface.protocols:
                        if proto.id == obj_id:
                            device = d
                            break
                if device:
                    break
                for sv in d.status_variables:
                    if sv.id == obj_id:
                        device = d
                        break
                if device:
                    break
            if device:
                self.set_current_device(device.id)

    def _add_status_var(self):
        if not self._model._device:
            QMessageBox.information(self, "提示", "请先在工程树中选择一个设备。")
            return
        sv = StatusVariable(name=f"状态量{len(self._model._device.status_variables) + 1}")
        self._model._device.status_variables.append(sv)
        self._model.notify_changed()
        self.data_modified.emit()

    def _on_model_data_changed(self, topLeft, bottomRight):
        """状态量表格单元格编辑完成 → 同步协议字段 + 通知主窗口。"""
        if not self._model._device:
            return
        sv = self._model._device.status_variables[topLeft.row()]
        # 同步已保存到模型的协议字段 (Project 层)
        self._project.sync_fields_from_status_var(sv)
        # 通知主窗口刷新视图并同步编辑器工作副本
        self.status_var_edited.emit(sv.id)
        self.data_modified.emit()

    def _del_status_var(self):
        idx = self._table.currentIndex()
        if not idx.isValid() or not self._model._device:
            return
        sv = self._model._device.status_variables[idx.row()]
        ref_count = self._project.status_var_ref_count(sv.id)
        if ref_count > 0:
            reply = QMessageBox.warning(
                self, "警告",
                f"状态量 \"{sv.name}\" 被 {ref_count} 个协议字段引用，删除后引用将失效。确定删除？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        self._model._device.status_variables.pop(idx.row())
        self._model.notify_changed()
        self.data_modified.emit()
