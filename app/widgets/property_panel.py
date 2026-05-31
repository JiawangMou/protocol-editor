"""属性编辑面板 — 按选中对象类型切换表单

信号级联崩溃原理与修复方案:
  当用户在工程树中点击节点时, show_object() -> _show_device() -> setText() 触发
  textChanged -> _save_current() -> data_modified.emit() -> _refresh_all()
  -> _tree.refresh() -> _model.clear() 会在树视图仍在处理选择事件期间清空模型,
  导致 Qt 访问已销毁的模型索引从而闪退。

  修复方法: 引入 _loading 标志位, 在 show_object() 填充控件值期间阻断
  _save_current() 的保存和信号发射, 避免在视图事件处理中触发模型重建。
"""
from PySide6.QtWidgets import (
    QWidget, QStackedWidget, QFormLayout, QLineEdit, QTextEdit,
    QComboBox, QSpinBox, QDoubleSpinBox, QGroupBox, QScrollArea, QVBoxLayout,
    QHBoxLayout, QPushButton, QLabel, QCheckBox,
)
from PySide6.QtCore import Signal

from app.models.protocol import (
    Project, Device, DeviceInterface, Protocol, StatusVariable, BusConfig,
    EthernetParams, RS422Params, RS232Params, CANParams, CANFDParams,
    UARTFrameConfig, CANFrameConfig, EthernetFrameConfig,
)
from app.models.enums import *


class PropertyPanel(QScrollArea):
    """属性编辑面板 — 根据工程树选中的对象类型动态切换编辑表单。"""
    data_modified = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self._project: Project | None = None
        self._current_type: str = ""
        self._current_id: str = ""
        self._loading: bool = False

        self._stack = QStackedWidget()
        self.setWidget(self._stack)

        # 页面索引: 0=空, 1=工程, 2=设备(原节点), 3=设备接口, 4=协议, 5=总线配置
        self._stack.addWidget(QLabel("请从左侧工程树中选择一项"))
        self._stack.addWidget(self._build_project_page())
        self._stack.addWidget(self._build_device_page())
        self._stack.addWidget(self._build_interface_page())
        self._stack.addWidget(self._build_protocol_page())
        self._stack.addWidget(self._build_bus_config_page())

    # ── Builders ──

    def _build_project_page(self) -> QWidget:
        w = QWidget()
        self._proj_name = QLineEdit()
        self._proj_version = QLineEdit()
        self._proj_author = QLineEdit()
        self._proj_endian = QComboBox()
        self._proj_endian.addItems(["big → 大端", "little → 小端"])
        self._proj_desc = QTextEdit()
        self._proj_desc.setMaximumHeight(80)

        layout = QVBoxLayout(w)
        g = QGroupBox("工程属性")
        f = QFormLayout(g)
        f.addRow("工程名称", self._proj_name)
        f.addRow("版本", self._proj_version)
        f.addRow("作者", self._proj_author)
        f.addRow("全局字节序", self._proj_endian)
        f.addRow("描述", self._proj_desc)
        layout.addWidget(g)
        layout.addStretch()

        for c in [self._proj_name, self._proj_version, self._proj_author,
                   self._proj_endian, self._proj_desc]:
            if hasattr(c, 'textChanged'):
                c.textChanged.connect(lambda: self._save_current())
            elif hasattr(c, 'currentIndexChanged'):
                c.currentIndexChanged.connect(lambda: self._save_current())
        return w

    def _build_device_page(self) -> QWidget:
        w = QWidget()
        self._dev_name = QLineEdit()
        self._dev_desc = QTextEdit()
        self._dev_desc.setMaximumHeight(80)

        layout = QVBoxLayout(w)
        g = QGroupBox("设备属性")
        f = QFormLayout(g)
        f.addRow("设备名称", self._dev_name)
        f.addRow("描述", self._dev_desc)
        layout.addWidget(g)
        layout.addStretch()

        self._dev_name.textChanged.connect(lambda: self._save_current())
        self._dev_desc.textChanged.connect(lambda: self._save_current())
        return w

    def _build_interface_page(self) -> QWidget:
        """设备接口页 — 名称 + 总线配置下拉选择。"""
        w = QWidget()
        layout = QVBoxLayout(w)

        g = QGroupBox("接口基本属性")
        f = QFormLayout(g)
        self._if_name = QLineEdit()
        f.addRow("接口名称", self._if_name)

        self._if_bus = QComboBox()
        self._if_bus.currentIndexChanged.connect(self._on_if_bus_changed)
        f.addRow("绑定总线", self._if_bus)

        self._if_bus_info = QLabel("")
        self._if_bus_info.setStyleSheet("color: #888; font-size: 11px;")
        f.addRow("", self._if_bus_info)

        layout.addWidget(g)
        layout.addStretch()

        self._if_name.textChanged.connect(lambda: self._save_current())
        self._if_bus.currentIndexChanged.connect(lambda: self._save_current())
        return w

    def _build_bus_config_page(self) -> QWidget:
        """总线配置页 — 名称 + 类型下拉 + 帧格式编辑。"""
        w = QWidget()
        layout = QVBoxLayout(w)

        # 基本属性
        g1 = QGroupBox("总线基本属性")
        f1 = QFormLayout(g1)
        self._bc_name = QLineEdit()
        self._bc_type = QComboBox()
        self._bc_type.addItems(["rs422", "rs232", "ethernet", "can", "canfd"])
        self._bc_type.currentIndexChanged.connect(self._on_bc_type_changed)
        f1.addRow("总线名称", self._bc_name)
        f1.addRow("总线类型", self._bc_type)
        layout.addWidget(g1)

        # 帧格式编辑 (按类型切换)
        # RS422 和 RS232 共用同一组 UART 控件，不可创建两份否则 self._bc_u_* 被覆盖
        self._bc_config_stack = QStackedWidget()
        self._bc_config_stack.addWidget(self._build_uart_config_widget())  # 0: UART (rs422/rs232)
        self._bc_config_stack.addWidget(self._build_eth_config_widget())   # 1: Ethernet
        self._bc_config_stack.addWidget(self._build_can_config_widget())   # 2: CAN
        self._bc_config_stack.addWidget(self._build_canfd_config_widget()) # 3: CANFD
        g2 = QGroupBox("帧格式参数")
        f2_layout = QVBoxLayout(g2)
        f2_layout.addWidget(self._bc_config_stack)
        layout.addWidget(g2)

        layout.addStretch()

        self._bc_name.textChanged.connect(lambda: self._save_current())
        self._bc_type.currentIndexChanged.connect(lambda: self._save_current())
        return w

    def _build_uart_config_widget(self) -> QWidget:
        """UART 帧格式 — 顺序结构: 起始标志 → 信息标识 → 信息长度 → 数据最大长度 → CRC校验 → 结束标志 → 字节序"""
        w = QWidget()
        f = QFormLayout(w)

        # 1. 起始标志
        self._bc_u_start_len = QSpinBox(); self._bc_u_start_len.setRange(0, 8)
        self._bc_u_start_len.valueChanged.connect(self._on_uart_start_len_changed)
        self._bc_u_start_mode = QComboBox()
        self._bc_u_start_mode.addItems(["固定值 (fixed)", "独立配置 (per_protocol)"])
        self._bc_u_start_mode.currentIndexChanged.connect(self._on_uart_start_mode_changed)
        self._bc_u_start_val = QLineEdit()
        self._bc_u_start_val.setPlaceholderText("hex, 如 A55A")
        start_row = QHBoxLayout()
        start_row.addWidget(self._bc_u_start_len)
        start_row.addWidget(self._bc_u_start_mode)
        start_row.addWidget(self._bc_u_start_val)
        f.addRow("起始标志", start_row)

        # 2. 信息标识 (消息ID)
        self._bc_u_msgid_len = QSpinBox(); self._bc_u_msgid_len.setRange(1, 8)
        f.addRow("信息标识字节数", self._bc_u_msgid_len)

        # 3. 信息长度
        self._bc_u_frm_len = QSpinBox(); self._bc_u_frm_len.setRange(1, 4)
        f.addRow("信息长度字节数", self._bc_u_frm_len)

        # 4. 信息内容最大长度
        self._bc_u_data_max = QSpinBox(); self._bc_u_data_max.setRange(0, 8192)
        f.addRow("信息内容最大长度 (字节)", self._bc_u_data_max)

        # 5. CRC校验
        self._bc_u_crc_len = QSpinBox(); self._bc_u_crc_len.setRange(0, 8)
        self._bc_u_crc_len.valueChanged.connect(self._on_uart_crc_len_changed)
        self._bc_u_crc_type = QComboBox()
        self._bc_u_crc_type.addItems(["none", "crc8", "crc16_ccitt", "crc16_modbus", "crc32", "sum8", "xor8"])
        self._bc_u_crc_type.setCurrentIndex(3)  # crc16_modbus
        crc_row = QHBoxLayout()
        crc_row.addWidget(self._bc_u_crc_len)
        crc_row.addWidget(self._bc_u_crc_type)
        f.addRow("CRC校验", crc_row)

        # 6. 结束标志
        self._bc_u_end_len = QSpinBox(); self._bc_u_end_len.setRange(0, 8)
        self._bc_u_end_len.valueChanged.connect(self._on_uart_end_len_changed)
        self._bc_u_end_mode = QComboBox()
        self._bc_u_end_mode.addItems(["固定值 (fixed)", "独立配置 (per_protocol)"])
        self._bc_u_end_mode.currentIndexChanged.connect(self._on_uart_end_mode_changed)
        self._bc_u_end_val = QLineEdit()
        self._bc_u_end_val.setPlaceholderText("hex, 如 0D0A")
        end_row = QHBoxLayout()
        end_row.addWidget(self._bc_u_end_len)
        end_row.addWidget(self._bc_u_end_mode)
        end_row.addWidget(self._bc_u_end_val)
        f.addRow("结束标志", end_row)

        # 7. 字节序
        self._bc_u_endian = QComboBox(); self._bc_u_endian.addItems(["big → 大端", "little → 小端"])
        f.addRow("字节序", self._bc_u_endian)

        for c in self._find_controls(w):
            if hasattr(c, 'textChanged'):
                c.textChanged.connect(lambda: self._save_current())
            elif hasattr(c, 'currentIndexChanged'):
                c.currentIndexChanged.connect(lambda: self._save_current())
            elif hasattr(c, 'valueChanged'):
                c.valueChanged.connect(lambda: self._save_current())
        return w

    def _on_uart_start_len_changed(self, val: int):
        enabled = val > 0
        self._bc_u_start_mode.setEnabled(enabled)
        self._bc_u_start_val.setVisible(enabled and self._bc_u_start_mode.currentIndex() == 0)

    def _on_uart_start_mode_changed(self, idx: int):
        """起始标志模式切换: 0=固定值(显示hex输入框), 1=独立配置(隐藏hex输入框)"""
        self._bc_u_start_val.setVisible(idx == 0 and self._bc_u_start_len.value() > 0)

    def _on_uart_end_len_changed(self, val: int):
        enabled = val > 0
        self._bc_u_end_mode.setEnabled(enabled)
        self._bc_u_end_val.setVisible(enabled and self._bc_u_end_mode.currentIndex() == 0)

    def _on_uart_end_mode_changed(self, idx: int):
        """结束标志模式切换: 0=固定值(显示hex输入框), 1=独立配置(隐藏hex输入框)"""
        self._bc_u_end_val.setVisible(idx == 0 and self._bc_u_end_len.value() > 0)

    def _on_uart_crc_len_changed(self, val: int):
        self._bc_u_crc_type.setVisible(val > 0)

    def _build_eth_config_widget(self) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)
        self._bc_eth_header = QSpinBox(); self._bc_eth_header.setRange(0, 256); self._bc_eth_header.setValue(8)
        self._bc_eth_msgtype_off = QSpinBox(); self._bc_eth_msgtype_off.setRange(0, 256)
        self._bc_eth_msgtype_len = QSpinBox(); self._bc_eth_msgtype_len.setRange(1, 8)
        self._bc_eth_seq_off = QSpinBox(); self._bc_eth_seq_off.setRange(-1, 256)
        self._bc_eth_seq_len = QSpinBox(); self._bc_eth_seq_len.setRange(1, 8)
        self._bc_eth_datalen_off = QSpinBox(); self._bc_eth_datalen_off.setRange(-1, 256)
        self._bc_eth_datalen_len = QSpinBox(); self._bc_eth_datalen_len.setRange(1, 8)
        self._bc_eth_ts_off = QSpinBox(); self._bc_eth_ts_off.setRange(-1, 256)
        self._bc_eth_ts_len = QSpinBox(); self._bc_eth_ts_len.setRange(1, 8)
        self._bc_eth_data_off = QSpinBox(); self._bc_eth_data_off.setRange(0, 256)
        self._bc_eth_data_max = QSpinBox(); self._bc_eth_data_max.setRange(0, 9000); self._bc_eth_data_max.setValue(1472)
        self._bc_eth_crc = QComboBox()
        self._bc_eth_crc.addItems(["none", "crc8", "crc16_ccitt", "crc16_modbus", "crc32", "sum8", "xor8"])
        self._bc_eth_crc_off = QSpinBox(); self._bc_eth_crc_off.setRange(-1, 256)
        self._bc_eth_endian = QComboBox(); self._bc_eth_endian.addItems(["big → 大端", "little → 小端"])

        f.addRow("头部长度", self._bc_eth_header)
        f.addRow("消息类型偏移", self._bc_eth_msgtype_off)
        f.addRow("消息类型长度", self._bc_eth_msgtype_len)
        f.addRow("序列号偏移 (-1=无)", self._bc_eth_seq_off)
        f.addRow("序列号长度", self._bc_eth_seq_len)
        f.addRow("数据长度偏移 (-1=无)", self._bc_eth_datalen_off)
        f.addRow("数据长度字段长", self._bc_eth_datalen_len)
        f.addRow("时间戳偏移 (-1=无)", self._bc_eth_ts_off)
        f.addRow("时间戳长度", self._bc_eth_ts_len)
        f.addRow("数据区偏移", self._bc_eth_data_off)
        f.addRow("数据区最大长度", self._bc_eth_data_max)
        f.addRow("CRC校验类型", self._bc_eth_crc)
        f.addRow("校验字偏移", self._bc_eth_crc_off)
        f.addRow("字节序", self._bc_eth_endian)

        for c in self._find_controls(w):
            if hasattr(c, 'textChanged'):
                c.textChanged.connect(lambda: self._save_current())
            elif hasattr(c, 'currentIndexChanged'):
                c.currentIndexChanged.connect(lambda: self._save_current())
            elif hasattr(c, 'valueChanged'):
                c.valueChanged.connect(lambda: self._save_current())
        return w

    def _build_can_config_widget(self) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)
        self._bc_c_arb_id = QLineEdit("0x000")
        self._bc_c_frm_type = QComboBox()
        self._bc_c_frm_type.addItems(["standard_data → 标准数据帧", "standard_remote → 标准远程帧",
                                       "extended_data → 扩展数据帧", "extended_remote → 扩展远程帧"])
        self._bc_c_dlc = QSpinBox(); self._bc_c_dlc.setRange(0, 64); self._bc_c_dlc.setValue(8)
        self._bc_c_brs = QCheckBox("启用可变速率 (BRS)")

        f.addRow("仲裁域ID", self._bc_c_arb_id)
        f.addRow("帧类型", self._bc_c_frm_type)
        f.addRow("DLC", self._bc_c_dlc)
        f.addRow("BRS", self._bc_c_brs)

        for c in self._find_controls(w):
            if hasattr(c, 'textChanged'):
                c.textChanged.connect(lambda: self._save_current())
            elif hasattr(c, 'currentIndexChanged'):
                c.currentIndexChanged.connect(lambda: self._save_current())
            elif hasattr(c, 'valueChanged'):
                c.valueChanged.connect(lambda: self._save_current())
            elif hasattr(c, 'toggled'):
                c.toggled.connect(lambda: self._save_current())
        return w

    def _build_canfd_config_widget(self) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)
        self._bc_cfd_arb_id = QLineEdit("0x000")
        self._bc_cfd_frm_type = QComboBox()
        self._bc_cfd_frm_type.addItems(["standard_data → 标准数据帧", "extended_data → 扩展数据帧"])
        self._bc_cfd_dlc = QSpinBox(); self._bc_cfd_dlc.setRange(0, 64); self._bc_cfd_dlc.setValue(8)
        self._bc_cfd_brs = QCheckBox("启用可变速率 (BRS)")

        f.addRow("仲裁域ID", self._bc_cfd_arb_id)
        f.addRow("帧类型", self._bc_cfd_frm_type)
        f.addRow("DLC", self._bc_cfd_dlc)
        f.addRow("BRS", self._bc_cfd_brs)

        for c in self._find_controls(w):
            if hasattr(c, 'textChanged'):
                c.textChanged.connect(lambda: self._save_current())
            elif hasattr(c, 'currentIndexChanged'):
                c.currentIndexChanged.connect(lambda: self._save_current())
            elif hasattr(c, 'valueChanged'):
                c.valueChanged.connect(lambda: self._save_current())
            elif hasattr(c, 'toggled'):
                c.toggled.connect(lambda: self._save_current())
        return w

    def _build_protocol_page(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        g1 = QGroupBox("协议基本属性")
        f1 = QFormLayout(g1)
        self._proto_name = QLineEdit()
        self._proto_cat = QComboBox()
        self._proto_cat.addItems([
            "control_request → 控制/请求指令",
            "periodic_report → 周期上报消息",
            "status_change → 状态变化上报消息",
            "execution_feedback → 执行结果反馈消息",
        ])
        self._proto_comm = QLineEdit()
        self._proto_comm.setReadOnly(True)
        self._proto_cat.currentIndexChanged.connect(self._on_proto_cat_changed)
        f1.addRow("协议名称", self._proto_name)
        f1.addRow("分类", self._proto_cat)
        f1.addRow("通讯方式", self._proto_comm)
        self._proto_period = QSpinBox()
        self._proto_period.setRange(0, 86400000)
        self._proto_period.setSuffix(" ms")
        self._proto_threshold = QLineEdit()
        f1.addRow("上报周期", self._proto_period)
        f1.addRow("变化阈值", self._proto_threshold)
        layout.addWidget(g1)

        g2 = QGroupBox("帧格式")
        f2 = QFormLayout(g2)
        self._frame_config_label = QLabel("(请在协议编辑器中配置帧格式详情)")
        f2.addRow(self._frame_config_label)
        layout.addWidget(g2)

        layout.addStretch()

        self._proto_name.textChanged.connect(lambda: self._save_current())
        self._proto_cat.currentIndexChanged.connect(lambda: self._save_current())
        self._proto_period.valueChanged.connect(lambda: self._save_current())
        self._proto_threshold.textChanged.connect(lambda: self._save_current())
        return w

    # ── Helpers ──

    def _find_controls(self, widget):
        result = []
        for tp in (QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QCheckBox):
            result.extend(widget.findChildren(tp))
        return result

    def _on_if_bus_changed(self, idx: int):
        if idx >= 0 and self._project:
            bc = self._project.bus_configs[idx]
            self._if_bus_info.setText(
                f"总线类型: {bc.type.value.upper()}, "
                f"帧格式: {bc.frame_config.__class__.__name__}"
            )

    def _on_bc_type_changed(self, idx: int):
        # 类型下拉: 0=rs422, 1=rs232, 2=ethernet, 3=can, 4=canfd
        # config_stack: 0=UART(rs422+rs232), 1=Eth, 2=CAN, 3=CANFD
        page = {0: 0, 1: 0, 2: 1, 3: 2, 4: 3}.get(idx, 0)
        self._bc_config_stack.setCurrentIndex(page)

    def _on_proto_cat_changed(self, idx: int):
        cat_map = {
            0: ProtocolCategory.CONTROL_REQUEST,
            1: ProtocolCategory.PERIODIC_REPORT,
            2: ProtocolCategory.STATUS_CHANGE,
            3: ProtocolCategory.EXECUTION_FEEDBACK,
        }
        cat = cat_map.get(idx, ProtocolCategory.CONTROL_REQUEST)
        methods = {
            ProtocolCategory.CONTROL_REQUEST: "请求-应答",
            ProtocolCategory.PERIODIC_REPORT: "周期发送",
            ProtocolCategory.STATUS_CHANGE: "变化触发",
            ProtocolCategory.EXECUTION_FEEDBACK: "应答返回",
        }
        self._proto_comm.setText(methods.get(cat, ""))
        self._proto_period.setVisible(idx == 1)
        self._proto_threshold.setVisible(idx == 2)

    # ── 对象展示 ──

    def show_object(self, project: Project, obj_type: str, obj_id: str):
        self._project = project
        self._current_type = obj_type
        self._current_id = obj_id
        self._loading = True

        try:
            if obj_type == "project":
                self._show_project(project)
                self._stack.setCurrentIndex(1)
            elif obj_type == "device":
                device = project.find_device(obj_id)
                if device:
                    self._show_device(device)
                    self._stack.setCurrentIndex(2)
            elif obj_type == "interface":
                result = project.find_interface(obj_id)
                if result:
                    self._show_interface(result[1])
                    self._stack.setCurrentIndex(3)
            elif obj_type == "protocol":
                proto = project.find_protocol(obj_id)
                if proto:
                    self._show_protocol(proto)
                    self._stack.setCurrentIndex(4)
            elif obj_type == "bus_config":
                bc = project.find_bus_config(obj_id)
                if bc:
                    self._show_bus_config(bc)
                    self._stack.setCurrentIndex(5)
            elif obj_type == "status_var":
                result = project.find_status_var(obj_id)
                if result:
                    self._show_status_var(result[1])
                    self._stack.setCurrentIndex(2)
            else:
                self._stack.setCurrentIndex(0)
        finally:
            self._loading = False

    def _show_project(self, proj: Project):
        self._proj_name.setText(proj.name)
        self._proj_version.setText(proj.version)
        self._proj_author.setText(proj.author)
        self._proj_endian.setCurrentIndex(0 if proj.endian == Endian.BIG else 1)
        self._proj_desc.setPlainText(proj.description)

    def _show_device(self, device: Device):
        self._dev_name.setText(device.name)
        self._dev_desc.setPlainText(device.description)

    def _show_status_var(self, sv: StatusVariable):
        self._dev_name.setText(sv.name)
        self._dev_desc.setPlainText(
            f"数据类型: {sv.data_type.value}, 字节长度: {sv.byte_length}\n"
            f"单位: {sv.unit}\n含义: {sv.meaning}\n备注: {sv.remarks}"
        )

    def _show_interface(self, iface: DeviceInterface):
        self._if_name.setText(iface.name)
        # 填充总线下拉
        self._if_bus.blockSignals(True)
        self._if_bus.clear()
        selected_idx = -1
        for i, bc in enumerate(self._project.bus_configs):
            self._if_bus.addItem(f"{bc.name} ({bc.type.value.upper()})", bc.id)
            if bc.id == iface.bus_config_id:
                selected_idx = i
        self._if_bus.blockSignals(False)
        if selected_idx >= 0:
            self._if_bus.setCurrentIndex(selected_idx)
            self._on_if_bus_changed(selected_idx)
        elif self._if_bus.count() > 0:
            self._if_bus.setCurrentIndex(0)
            self._on_if_bus_changed(0)

    def _show_bus_config(self, bc: BusConfig):
        self._bc_name.setText(bc.name)
        type_idx = {"rs422": 0, "rs232": 1, "ethernet": 2, "can": 3, "canfd": 4}
        self._bc_type.setCurrentIndex(type_idx.get(bc.type.value, 0))
        self._on_bc_type_changed(self._bc_type.currentIndex())

        cfg = bc.frame_config
        if isinstance(cfg, UARTFrameConfig):
            self._bc_u_start_len.setValue(cfg.start_flag_len)
            mode_map = {"fixed": 0, "per_protocol": 1}
            self._bc_u_start_mode.setCurrentIndex(mode_map.get(cfg.start_flag_mode, 0))
            self._bc_u_start_val.setText(cfg.start_flag_value)
            self._bc_u_msgid_len.setValue(cfg.msg_id_len)
            self._bc_u_frm_len.setValue(cfg.frame_len_len)
            self._bc_u_data_max.setValue(cfg.data_max_len)
            self._bc_u_crc_len.setValue(cfg.crc_len)
            crc_val = getattr(cfg.crc_type, 'value', cfg.crc_type)
            self._bc_u_crc_type.setCurrentText(str(crc_val))
            self._bc_u_end_len.setValue(cfg.end_flag_len)
            self._bc_u_end_mode.setCurrentIndex(mode_map.get(cfg.end_flag_mode, 0))
            self._bc_u_end_val.setText(cfg.end_flag_value)
            self._bc_u_endian.setCurrentIndex(0 if cfg.endian == Endian.BIG else 1)
            # 触发联动
            self._on_uart_start_len_changed(cfg.start_flag_len)
            self._on_uart_start_mode_changed(mode_map.get(cfg.start_flag_mode, 0))
            self._on_uart_end_len_changed(cfg.end_flag_len)
            self._on_uart_end_mode_changed(mode_map.get(cfg.end_flag_mode, 0))
            self._on_uart_crc_len_changed(cfg.crc_len)
        elif isinstance(cfg, CANFrameConfig):
            self._bc_c_arb_id.setText(cfg.arbitration_id)
            type_map = {"standard_data": 0, "standard_remote": 1, "extended_data": 2, "extended_remote": 3}
            self._bc_c_frm_type.setCurrentIndex(type_map.get(cfg.frame_type.value, 0))
            self._bc_c_dlc.setValue(cfg.dlc)
            self._bc_c_brs.setChecked(cfg.brs)
        elif isinstance(cfg, EthernetFrameConfig):
            self._bc_eth_header.setValue(cfg.header_len)
            self._bc_eth_msgtype_off.setValue(cfg.msg_type_offset)
            self._bc_eth_msgtype_len.setValue(cfg.msg_type_len)
            self._bc_eth_seq_off.setValue(cfg.seq_offset)
            self._bc_eth_seq_len.setValue(cfg.seq_len)
            self._bc_eth_datalen_off.setValue(cfg.data_len_offset)
            self._bc_eth_datalen_len.setValue(cfg.data_len_len)
            self._bc_eth_ts_off.setValue(cfg.timestamp_offset)
            self._bc_eth_ts_len.setValue(cfg.timestamp_len)
            self._bc_eth_data_off.setValue(cfg.data_offset)
            self._bc_eth_data_max.setValue(cfg.data_max_len)
            self._bc_eth_crc.setCurrentText(cfg.crc_type.value)
            self._bc_eth_crc_off.setValue(cfg.crc_offset)
            self._bc_eth_endian.setCurrentIndex(0 if cfg.endian == Endian.BIG else 1)

    def _show_protocol(self, proto: Protocol):
        self._proto_name.setText(proto.name)
        cat_idx = {
            ProtocolCategory.CONTROL_REQUEST: 0,
            ProtocolCategory.PERIODIC_REPORT: 1,
            ProtocolCategory.STATUS_CHANGE: 2,
            ProtocolCategory.EXECUTION_FEEDBACK: 3,
        }
        self._proto_cat.setCurrentIndex(cat_idx.get(proto.category, 0))
        self._on_proto_cat_changed(self._proto_cat.currentIndex())
        self._proto_comm.setText(proto.comm_method)
        self._proto_period.setValue(proto.report_period_ms)
        self._proto_threshold.setText(proto.change_threshold)

    # ── 数据回写 ──

    def _save_current(self):
        if not self._project or self._loading:
            return
        saved = False
        if self._current_type == "project":
            self._save_project()
            saved = True
        elif self._current_type == "device":
            self._save_device()
            saved = True
        elif self._current_type == "interface":
            self._save_interface()
            saved = True
        elif self._current_type == "protocol":
            self._save_protocol()
            saved = True
        elif self._current_type == "bus_config":
            self._save_bus_config()
            saved = True
        if saved:
            self.data_modified.emit()

    def _save_project(self):
        self._project.name = self._proj_name.text()
        self._project.version = self._proj_version.text()
        self._project.author = self._proj_author.text()
        self._project.endian = Endian.BIG if self._proj_endian.currentIndex() == 0 else Endian.LITTLE
        self._project.description = self._proj_desc.toPlainText()

    def _save_device(self):
        device = self._project.find_device(self._current_id)
        if device:
            device.name = self._dev_name.text()
            device.description = self._dev_desc.toPlainText()

    def _save_interface(self):
        result = self._project.find_interface(self._current_id)
        if not result:
            return
        _, iface = result
        iface.name = self._if_name.text()
        idx = self._if_bus.currentIndex()
        if idx >= 0 and idx < len(self._project.bus_configs):
            iface.bus_config_id = self._project.bus_configs[idx].id

    def _save_bus_config(self):
        bc = self._project.find_bus_config(self._current_id)
        if not bc:
            return
        bc.name = self._bc_name.text()
        type_idx = self._bc_type.currentIndex()
        type_map = {0: InterfaceType.RS422, 1: InterfaceType.RS232, 2: InterfaceType.ETHERNET,
                    3: InterfaceType.CAN, 4: InterfaceType.CANFD}
        bc.type = type_map.get(type_idx, InterfaceType.RS422)

        # 根据类型保存帧格式
        if type_idx <= 1:  # UART (RS422/RS232)
            cfg = UARTFrameConfig()
            if isinstance(bc.frame_config, UARTFrameConfig):
                cfg = bc.frame_config
            cfg.start_flag_len = self._bc_u_start_len.value()
            cfg.start_flag_mode = "fixed" if self._bc_u_start_mode.currentIndex() == 0 else "per_protocol"
            cfg.start_flag_value = self._bc_u_start_val.text().strip()
            cfg.msg_id_len = self._bc_u_msgid_len.value()
            cfg.frame_len_len = self._bc_u_frm_len.value()
            cfg.data_max_len = self._bc_u_data_max.value()
            cfg.crc_len = self._bc_u_crc_len.value()
            cfg.crc_type = CRCType(self._bc_u_crc_type.currentText())
            cfg.end_flag_len = self._bc_u_end_len.value()
            cfg.end_flag_mode = "fixed" if self._bc_u_end_mode.currentIndex() == 0 else "per_protocol"
            cfg.end_flag_value = self._bc_u_end_val.text().strip()
            cfg.endian = Endian.BIG if self._bc_u_endian.currentIndex() == 0 else Endian.LITTLE
            bc.frame_config = cfg
        elif type_idx == 2:  # Ethernet
            cfg = EthernetFrameConfig()
            if isinstance(bc.frame_config, EthernetFrameConfig):
                cfg = bc.frame_config
            cfg.header_len = self._bc_eth_header.value()
            cfg.msg_type_offset = self._bc_eth_msgtype_off.value()
            cfg.msg_type_len = self._bc_eth_msgtype_len.value()
            cfg.seq_offset = self._bc_eth_seq_off.value()
            cfg.seq_len = self._bc_eth_seq_len.value()
            cfg.data_len_offset = self._bc_eth_datalen_off.value()
            cfg.data_len_len = self._bc_eth_datalen_len.value()
            cfg.timestamp_offset = self._bc_eth_ts_off.value()
            cfg.timestamp_len = self._bc_eth_ts_len.value()
            cfg.data_offset = self._bc_eth_data_off.value()
            cfg.data_max_len = self._bc_eth_data_max.value()
            cfg.crc_type = CRCType(self._bc_eth_crc.currentText())
            cfg.crc_offset = self._bc_eth_crc_off.value()
            cfg.endian = Endian.BIG if self._bc_eth_endian.currentIndex() == 0 else Endian.LITTLE
            bc.frame_config = cfg
        elif type_idx >= 3:  # CAN / CANFD
            cfg = CANFrameConfig()
            if isinstance(bc.frame_config, CANFrameConfig):
                cfg = bc.frame_config
            if type_idx == 3:  # CAN
                cfg.arbitration_id = self._bc_c_arb_id.text()
                type_map = {0: CANFrameType.STANDARD_DATA, 1: CANFrameType.STANDARD_REMOTE,
                            2: CANFrameType.EXTENDED_DATA, 3: CANFrameType.EXTENDED_REMOTE}
                cfg.frame_type = type_map.get(self._bc_c_frm_type.currentIndex(), CANFrameType.STANDARD_DATA)
                cfg.dlc = self._bc_c_dlc.value()
                cfg.brs = self._bc_c_brs.isChecked()
            else:  # CANFD
                cfg.arbitration_id = self._bc_cfd_arb_id.text()
                type_map = {0: CANFrameType.STANDARD_DATA, 1: CANFrameType.EXTENDED_DATA}
                cfg.frame_type = type_map.get(self._bc_cfd_frm_type.currentIndex(), CANFrameType.STANDARD_DATA)
                cfg.dlc = self._bc_cfd_dlc.value()
                cfg.brs = self._bc_cfd_brs.isChecked()
            bc.frame_config = cfg

    def _save_protocol(self):
        proto = self._project.find_protocol(self._current_id)
        if not proto:
            return
        proto.name = self._proto_name.text()
        cat_map = {
            0: ProtocolCategory.CONTROL_REQUEST,
            1: ProtocolCategory.PERIODIC_REPORT,
            2: ProtocolCategory.STATUS_CHANGE,
            3: ProtocolCategory.EXECUTION_FEEDBACK,
        }
        proto.category = cat_map.get(self._proto_cat.currentIndex(), ProtocolCategory.CONTROL_REQUEST)
        proto.comm_method = self._proto_comm.text()
        proto.report_period_ms = self._proto_period.value()
        proto.change_threshold = self._proto_threshold.text()
