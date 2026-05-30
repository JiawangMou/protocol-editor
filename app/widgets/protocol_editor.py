"""协议内容编辑表格 — 双击协议对象在软件中心打开, 编辑消息帧中每个字节的含义"""
from copy import deepcopy

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableView, QHeaderView,
    QPushButton, QComboBox, QDialog, QListWidget, QListWidgetItem,
    QDialogButtonBox, QMessageBox, QStyledItemDelegate, QLabel,
)
from PySide6.QtCore import Qt, Signal, QAbstractTableModel, QModelIndex

from app.models.protocol import Project, Device, Protocol, ProtocolField, StatusVariable, DATA_TYPE_BYTE_SIZES
from app.models.enums import DataType, FieldSource


class FieldTableModel(QAbstractTableModel):
    """协议字段表格模型 — 列: 字节号, 名称, 字节数, 数据类型, 含义, 单位"""
    COLS = ["字节号", "名称", "字节数", "数据类型", "含义", "单位"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._fields: list[ProtocolField] = []

    def set_fields(self, fields: list[ProtocolField]):
        self.beginResetModel()
        self._fields = fields
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return len(self._fields)

    def columnCount(self, parent=QModelIndex()):
        return len(self.COLS)

    def headerData(self, section, orientation, role):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.COLS[section]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not self._fields:
            return None
        fld = self._fields[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                start = sum(f.byte_length for f in self._fields[:index.row()])
                length = fld.byte_length
                if length > 1:
                    return f"{start}-{start + length - 1}"
                return str(start)
            elif col == 1:
                return fld.name
            elif col == 2:
                return str(fld.byte_length)
            elif col == 3:
                return fld.data_type.value
            elif col == 4:
                return fld.description
            elif col == 5:
                return fld.unit

        if role == Qt.ItemDataRole.EditRole:
            if col == 1:
                return fld.name
            elif col == 2:
                return fld.byte_length
            elif col == 3:
                return fld.data_type.value
            elif col == 4:
                return fld.description
            elif col == 5:
                return fld.unit

        return None

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if not self._fields or role != Qt.ItemDataRole.EditRole:
            return False
        fld = self._fields[index.row()]
        col = index.column()
        try:
            if col == 1:
                fld.name = str(value)
            elif col == 2:
                fld.byte_length = int(value)
                self._recalc_offsets(index.row())
            elif col == 3:
                dt = DataType(value)
                fld.data_type = dt
                auto_size = DATA_TYPE_BYTE_SIZES.get(dt)
                if auto_size is not None and auto_size > 0:
                    fld.byte_length = auto_size
                    self._recalc_offsets(index.row())
            elif col == 4:
                fld.description = str(value)
            elif col == 5:
                fld.unit = str(value)
            else:
                return False
            self.dataChanged.emit(index, index)
            # When byte_length changes, notify all subsequent rows (offset shift)
            if col in (2, 3):
                last = self.index(self.rowCount() - 1, 0)
                if last.row() > index.row():
                    self.dataChanged.emit(
                        self.index(index.row() + 1, 0), last
                    )
            return True
        except (ValueError, KeyError):
            return False

    def _recalc_offsets(self, from_row: int):
        """通知视图 from_row 之后所有行的字节号列需要刷新。"""
        pass  # dataChanged handles this

    def flags(self, index):
        if index.column() == 0:
            return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEditable


class DataTypeDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        cb = QComboBox(parent)
        cb.addItems([dt.value for dt in DataType])
        return cb

    def setEditorData(self, editor, index):
        val = index.data(Qt.ItemDataRole.EditRole)
        idx = editor.findText(str(val))
        if idx >= 0:
            editor.setCurrentIndex(idx)

    def setModelData(self, editor, model, index):
        model.setData(index, editor.currentText())


class StatusVarPickerDialog(QDialog):
    """状态量选择对话框。

    防止选 A 得 B 问题的多层保障:
      1. itemClicked 信号在焦点转移前捕获所选 ID
      2. 直接存储 StatusVariable 对象引用 (避免 ID 查找歧义)
      3. 双击即确认, 不依赖 OK 按钮的焦点转移
    """
    def __init__(self, status_vars: list[StatusVariable], parent=None):
        super().__init__(parent)
        self.setWindowTitle("选择状态量")
        self.setMinimumSize(420, 300)
        self._selected_sv: StatusVariable | None = None

        layout = QVBoxLayout(self)
        self._list = QListWidget()
        for sv in status_vars:
            item = QListWidgetItem(
                f"{sv.name} | {sv.data_type.value} | {sv.byte_length}B | {sv.unit} | {sv.meaning}"
            )
            item.setData(Qt.ItemDataRole.UserRole, sv.id)
            # 直接存储对象引用, 后续取值无需 ID 查找, 彻底杜绝 ID 重复导致的选 A 得 B
            item.setData(Qt.ItemDataRole.UserRole + 1, sv)
            self._list.addItem(item)
        # 默认选中第一项
        if self._list.count() > 0:
            self._list.setCurrentRow(0)
            first_item = self._list.currentItem()
            if first_item:
                self._selected_sv = first_item.data(Qt.ItemDataRole.UserRole + 1)
        # 跟踪用户每一次点击, 在焦点转移前保存所选对象
        self._list.itemClicked.connect(self._on_item_clicked)
        # 双击列表项直接确认
        self._list.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self._list)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn_box.accepted.connect(self._on_accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _on_item_clicked(self, item):
        sv = item.data(Qt.ItemDataRole.UserRole + 1)
        if sv is not None:
            self._selected_sv = sv

    def _on_item_double_clicked(self, item):
        self._selected_sv = item.data(Qt.ItemDataRole.UserRole + 1)
        self.accept()

    def _on_accept(self):
        # _selected_sv 已由 _on_item_clicked 或默认选中提前设置
        self.accept()

    def selected_sv(self) -> StatusVariable | None:
        return self._selected_sv


class ProtocolContentEditor(QWidget):
    """协议内容编辑表格 — 在软件中心显示。双击协议对象打开。"""
    saved = Signal()
    cancelled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project: Project | None = None
        self._protocol: Protocol | None = None
        self._device: Device | None = None
        self._original_fields: list[ProtocolField] = []
        self._work_fields: list[ProtocolField] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # ── Header ──
        header = QHBoxLayout()
        self._title_label = QLabel("协议内容编辑")
        self._title_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        header.addWidget(self._title_label)
        header.addStretch()
        self._btn_pick_sv = QPushButton("从状态量选取")
        self._btn_pick_sv.clicked.connect(self._pick_status_var)
        header.addWidget(self._btn_pick_sv)
        self._btn_add = QPushButton("添加字段")
        self._btn_add.clicked.connect(self._add_field)
        header.addWidget(self._btn_add)
        self._btn_del = QPushButton("删除字段")
        self._btn_del.clicked.connect(self._del_field)
        header.addWidget(self._btn_del)
        layout.addLayout(header)

        # ── Table ──
        self._model = FieldTableModel()
        self._table = QTableView()
        self._table.setModel(self._model)
        self._table.setItemDelegateForColumn(3, DataTypeDelegate(self._table))
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        layout.addWidget(self._table)

        # ── Bottom buttons ──
        bottom = QHBoxLayout()
        bottom.addStretch()
        self._btn_save = QPushButton("保存")
        self._btn_save.setMinimumWidth(100)
        self._btn_save.clicked.connect(self._save)
        bottom.addWidget(self._btn_save)
        self._btn_cancel = QPushButton("取消")
        self._btn_cancel.setMinimumWidth(100)
        self._btn_cancel.clicked.connect(self._cancel)
        bottom.addWidget(self._btn_cancel)
        bottom.addStretch()
        layout.addLayout(bottom)

    def set_protocol(self, project: Project, proto: Protocol, device: Device):
        """打开协议编辑 — 使用工作副本, 确保取消可丢弃修改。"""
        self._project = project
        self._protocol = proto
        self._device = device
        self._original_fields = proto.fields
        self._work_fields = [deepcopy(f) for f in proto.fields]
        self._model.set_fields(self._work_fields)
        self._title_label.setText(f"协议内容编辑 — {proto.name}  [{device.name}]")

    def _save(self):
        """保存工作副本到协议对象, 不关闭窗口。"""
        if self._protocol is None:
            return
        self._protocol.fields = [deepcopy(f) for f in self._work_fields]
        self._original_fields = self._protocol.fields
        self.saved.emit()

    def _cancel(self):
        """丢弃修改并关闭窗口。"""
        self.cancelled.emit()

    def _add_field(self):
        if self._protocol is None:
            return
        fld = ProtocolField(name=f"字段{len(self._work_fields) + 1}")
        self._work_fields.append(fld)
        self._model.set_fields(self._work_fields)

    def _del_field(self):
        idx = self._table.currentIndex()
        if not idx.isValid():
            return
        self._work_fields.pop(idx.row())
        self._model.set_fields(self._work_fields)

    def _pick_status_var(self):
        """从当前设备的状态量中选择, 若表格中有选中行则替换, 否则追加到末尾。"""
        if not self._device or not self._protocol:
            QMessageBox.information(self, "提示", "请先打开协议。")
            return
        if not self._device.status_variables:
            QMessageBox.information(self, "提示", f"设备 \"{self._device.name}\" 暂无状态量, 请先添加。")
            return
        dlg = StatusVarPickerDialog(self._device.status_variables, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            sv = dlg.selected_sv()
            if sv:
                fld = ProtocolField(
                    name=sv.name,
                    data_type=sv.data_type,
                    byte_length=sv.byte_length,
                    source=FieldSource.STATUS_VAR,
                    status_var_ref=sv.id,
                    description=sv.meaning,
                    unit=sv.unit,
                )
                idx = self._table.currentIndex()
                if idx.isValid():
                    self._work_fields[idx.row()] = fld
                else:
                    self._work_fields.append(fld)
                self._model.set_fields(self._work_fields)
