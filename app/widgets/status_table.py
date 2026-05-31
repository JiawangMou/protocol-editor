"""状态量管理表格

工作副本模式:
  - 编辑 / 添加 / 删除均作用于 deepcopy 的 _work_vars，不影响真实数据。
  - 点击「保存」才将工作副本写回 device.status_variables，并同步协议字段。
  - 点击「取消」丢弃全部修改，恢复为原始数据。
"""
from copy import deepcopy

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
        self._device: Device | None = None       # 当前真实设备引用
        self._work_vars: list[StatusVariable] = []  # 工作副本
        self._project: Project | None = None

    def set_data(self, project: Project, device: Device | None):
        self.beginResetModel()
        self._project = project
        self._device = device
        self._work_vars = [deepcopy(sv) for sv in device.status_variables] if device else []
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return len(self._work_vars)

    def columnCount(self, parent=QModelIndex()):
        return len(self.COLUMNS)

    def headerData(self, section, orientation, role):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.COLUMNS[section]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not self._work_vars:
            return None
        sv = self._work_vars[index.row()]
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
                return str(self._project.status_var_ref_count(sv.id)) if self._project else "0"

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
        if not self._work_vars or role != Qt.ItemDataRole.EditRole:
            return False
        sv = self._work_vars[index.row()]
        col = index.column()

        if col == 0:
            sv.name = value
        elif col == 1:
            try:
                sv.data_type = DataType(value)
                auto_size = DATA_TYPE_BYTE_SIZES.get(sv.data_type)
                if auto_size is not None:
                    sv.byte_length = auto_size
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

    def add_var(self, sv: StatusVariable):
        self._work_vars.append(sv)
        self.beginResetModel()
        self.endResetModel()

    def remove_var(self, row: int):
        if 0 <= row < len(self._work_vars):
            self._work_vars.pop(row)
            self.beginResetModel()
            self.endResetModel()

    def get_work_vars(self) -> list[StatusVariable]:
        return self._work_vars


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
    """状态量管理组件 — 工作副本模式，保存按钮才提交。"""
    data_modified = Signal()           # 保存后发出，触发 _refresh_all
    status_var_edited = Signal(str)    # 携带被写入的状态量 id，触发协议字段同步

    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self._project = project

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # ── Toolbar: 单机下拉 + 操作按钮 (同一行) ──
        tb = QHBoxLayout()
        self._device_combo = QComboBox()
        self._device_combo.setMinimumWidth(160)
        self._device_combo.currentIndexChanged.connect(self._on_device_combo_changed)
        tb.addWidget(self._device_combo)

        self._btn_add = QPushButton("添加状态量")
        self._btn_add.clicked.connect(self._add_status_var)
        tb.addWidget(self._btn_add)

        self._btn_del = QPushButton("删除选中")
        self._btn_del.clicked.connect(self._del_status_var)
        tb.addWidget(self._btn_del)

        self._btn_save = QPushButton("保存")
        self._btn_save.setMinimumWidth(80)
        self._btn_save.clicked.connect(self._save)
        tb.addWidget(self._btn_save)

        tb.addStretch()
        layout.addLayout(tb)

        # ── Table ──
        self._model = StatusTableModel()
        self._table = QTableView()
        self._table.setModel(self._model)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._table.setItemDelegateForColumn(1, DataTypeDelegate(self._table))
        self._table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        layout.addWidget(self._table)

        self._refresh_device_combo()

    # ── 下拉联动 ──

    def _refresh_device_combo(self):
        """用当前工程中的所有设备填充下拉列表。"""
        self._device_combo.blockSignals(True)
        self._device_combo.clear()
        for d in self._project.devices:
            self._device_combo.addItem(d.name, d.id)
        self._device_combo.blockSignals(False)

    def _on_device_combo_changed(self, idx: int):
        """用户从下拉菜单中选择单机 → 加载该单机的状态量工作副本。"""
        if idx < 0:
            return
        device_id = self._device_combo.itemData(idx)
        if device_id:
            self._load_device(device_id)

    def _select_device_in_combo(self, device_id: str):
        """将下拉选项同步到指定的 device_id，不触发信号（避免循环）。"""
        self._device_combo.blockSignals(True)
        for i in range(self._device_combo.count()):
            if self._device_combo.itemData(i) == device_id:
                self._device_combo.setCurrentIndex(i)
                break
        self._device_combo.blockSignals(False)

    def _load_device(self, device_id: str):
        """加载指定设备的状态量工作副本到表格。"""
        device = self._project.find_device(device_id)
        self._model.set_data(self._project, device)

    # ── 公共接口 ──

    def set_project(self, project: Project):
        self._project = project
        prev_device = self._model._device
        self._refresh_device_combo()
        if prev_device:
            still_exists = self._project.find_device(prev_device.id)
            if still_exists:
                self._select_device_in_combo(prev_device.id)
                self._load_device(prev_device.id)
                return
        # 如果没有之前的设备但有设备存在，默认选第一个
        if self._project.devices:
            self._select_device_in_combo(self._project.devices[0].id)
            self._load_device(self._project.devices[0].id)
        else:
            self._model.set_data(self._project, None)

    def set_current_device(self, device_id: str):
        device = self._project.find_device(device_id)
        if device:
            self._select_device_in_combo(device_id)
            self._load_device(device_id)

    def set_current_node_by_selection(self, obj_type: str, obj_id: str):
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

    # ── 操作按钮 ──

    def _add_status_var(self):
        if not self._model._device:
            QMessageBox.information(self, "提示", "请先在下拉菜单中选择一个单机。")
            return
        from app.models.protocol import _new_id
        sv = StatusVariable(
            id=_new_id("sv"),
            name=f"状态量{len(self._model._work_vars) + 1}",
        )
        self._model.add_var(sv)

    def _del_status_var(self):
        idx = self._table.currentIndex()
        if not idx.isValid() or not self._model._work_vars:
            return
        sv = self._model._work_vars[idx.row()]
        ref_count = self._project.status_var_ref_count(sv.id)
        if ref_count > 0:
            reply = QMessageBox.warning(
                self, "警告",
                f"状态量 \"{sv.name}\" 被 {ref_count} 个协议字段引用，"
                f"删除后引用将失效。确定删除？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        self._model.remove_var(idx.row())

    def _save(self):
        """将工作副本写回 device.status_variables，同步协议字段，通知主窗口。"""
        if not self._model._device:
            return
        device = self._model._device
        work = self._model._work_vars

        # 检查当前工作副本中的 ID 是否有变化（新添加的 SV）
        old_ids = {sv.id for sv in device.status_variables}
        new_ids = {sv.id for sv in work}
        all_ids = old_ids | new_ids

        # 写回工作副本
        device.status_variables = [deepcopy(sv) for sv in work]

        # 同步 Project 层：对所有涉及的状态量 ID 同步协议字段
        edited_count = 0
        for sv_id in all_ids:
            sv = next((s for s in device.status_variables if s.id == sv_id), None)
            if sv:
                n = self._project.sync_fields_from_status_var(sv)
                edited_count += n
                self.status_var_edited.emit(sv_id)

        # 刷新模型以更新引用计数
        self._model.set_data(self._project, device)
        self.data_modified.emit()
