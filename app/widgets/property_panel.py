"""属性编辑面板 — 按选中对象类型切换表单"""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QStackedWidget, QFormLayout, QLineEdit, QTextEdit,
    QComboBox, QSpinBox, QDoubleSpinBox, QGroupBox, QScrollArea, QVBoxLayout,
    QPushButton, QLabel, QCheckBox,
)
from PySide6.QtCore import Signal

from app.models.protocol import (
    Project, Node, Interface, Protocol, StatusVariable,
    EthernetParams, RS422Params, RS232Params, CANParams, CANFDParams,
    UARTFrameConfig, CANFrameConfig, EthernetFrameConfig,
)
from app.models.enums import *


class PropertyPanel(QScrollArea):
    data_modified = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self._project: Project | None = None
        self._current_type: str = ""
        self._current_id: str = ""

        self._stack = QStackedWidget()
        self.setWidget(self._stack)

        # Pages: 0=empty, 1=project, 2=node, 3=interface, 4=protocol
        self._stack.addWidget(QLabel("请从左侧工程树中选择一项"))
        self._stack.addWidget(self._build_project_page())
        self._stack.addWidget(self._build_node_page())
        self._stack.addWidget(self._build_interface_page())
        self._stack.addWidget(self._build_protocol_page())

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

    def _build_node_page(self) -> QWidget:
        w = QWidget()
        self._node_name = QLineEdit()
        self._node_desc = QTextEdit()
        self._node_desc.setMaximumHeight(80)

        layout = QVBoxLayout(w)
        g = QGroupBox("节点属性")
        f = QFormLayout(g)
        f.addRow("节点名称", self._node_name)
        f.addRow("描述", self._node_desc)
        layout.addWidget(g)
        layout.addStretch()

        self._node_name.textChanged.connect(lambda: self._save_current())
        self._node_desc.textChanged.connect(lambda: self._save_current())
        return w

    def _build_interface_page(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        # Common
        self._if_name = QLineEdit()
        self._if_type = QComboBox()
        self._if_type.addItems(["rs422", "rs232", "ethernet", "can", "canfd"])
        self._if_type.currentIndexChanged.connect(self._on_if_type_changed)

        g_common = QGroupBox("接口基本属性")
        f = QFormLayout(g_common)
        f.addRow("接口名称", self._if_name)
        f.addRow("接口类型", self._if_type)
        layout.addWidget(g_common)

        # Type-specific params (stacked)
        self._if_param_stack = QStackedWidget()
        self._if_param_stack.addWidget(self._build_uart_params())
        self._if_param_stack.addWidget(self._build_uart_params())  # RS232
        self._if_param_stack.addWidget(self._build_eth_params())
        self._if_param_stack.addWidget(self._build_can_params())
        self._if_param_stack.addWidget(self._build_canfd_params())
        layout.addWidget(self._if_param_stack)

        layout.addStretch()

        self._if_name.textChanged.connect(lambda: self._save_current())
        self._if_type.currentIndexChanged.connect(lambda: self._save_current())
        return w

    def _build_uart_params(self) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)
        self._uart_port = QLineEdit("COM1")
        self._uart_baud = QComboBox()
        self._uart_baud.addItems(["9600", "19200", "38400", "57600", "115200", "230400", "460800", "921600"])
        self._uart_data = QComboBox()
        self._uart_data.addItems(["5", "6", "7", "8"])
        self._uart_data.setCurrentIndex(3)
        self._uart_stop = QComboBox()
        self._uart_stop.addItems(["1", "1.5", "2"])
        self._uart_parity = QComboBox()
        self._uart_parity.addItems(["none → 无校验", "odd → 奇校验", "even → 偶校验"])
        self._uart_flow = QComboBox()
        self._uart_flow.addItems(["none → 无", "rts_cts → RTS/CTS", "xon_xoff → XON/XOFF"])

        f.addRow("端口号", self._uart_port)
        f.addRow("波特率", self._uart_baud)
        f.addRow("数据位", self._uart_data)
        f.addRow("停止位", self._uart_stop)
        f.addRow("校验位", self._uart_parity)
        f.addRow("流控", self._uart_flow)

        for c in [self._uart_port, self._uart_baud, self._uart_data,
                   self._uart_stop, self._uart_parity, self._uart_flow]:
            if hasattr(c, 'textChanged'):
                c.textChanged.connect(lambda: self._save_current())
            elif hasattr(c, 'currentIndexChanged'):
                c.currentIndexChanged.connect(lambda: self._save_current())
        return w

    def _build_eth_params(self) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)
        self._eth_ip = QLineEdit("192.168.1.1")
        self._eth_port = QSpinBox()
        self._eth_port.setRange(1, 65535)
        self._eth_port.setValue(5000)
        self._eth_proto = QComboBox()
        self._eth_proto.addItems(["tcp", "udp"])
        self._eth_mac = QLineEdit()
        f.addRow("IP 地址", self._eth_ip)
        f.addRow("端口号", self._eth_port)
        f.addRow("协议", self._eth_proto)
        f.addRow("MAC 地址", self._eth_mac)
        for c in [self._eth_ip, self._eth_port, self._eth_proto, self._eth_mac]:
            if hasattr(c, 'textChanged'):
                c.textChanged.connect(lambda: self._save_current())
            elif hasattr(c, 'valueChanged'):
                c.valueChanged.connect(lambda: self._save_current())
            elif hasattr(c, 'currentIndexChanged'):
                c.currentIndexChanged.connect(lambda: self._save_current())
        return w

    def _build_can_params(self) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)
        self._can_ch = QLineEdit("can0")
        self._can_bitrate = QComboBox()
        self._can_bitrate.addItems(["125000", "250000", "500000", "1000000"])
        self._can_bitrate.setCurrentIndex(2)
        self._can_format = QComboBox()
        self._can_format.addItems(["standard → 标准帧", "extended → 扩展帧"])
        self._can_term = QCheckBox("启用终端电阻")
        self._can_term.setChecked(True)
        f.addRow("通道", self._can_ch)
        f.addRow("波特率", self._can_bitrate)
        f.addRow("帧格式", self._can_format)
        f.addRow("终端电阻", self._can_term)
        for c in [self._can_ch, self._can_bitrate, self._can_format, self._can_term]:
            if hasattr(c, 'textChanged'):
                c.textChanged.connect(lambda: self._save_current())
            elif hasattr(c, 'currentIndexChanged'):
                c.currentIndexChanged.connect(lambda: self._save_current())
            elif hasattr(c, 'toggled'):
                c.toggled.connect(lambda: self._save_current())
        return w

    def _build_canfd_params(self) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)
        self._canfd_ch = QLineEdit("can0")
        self._canfd_arb = QComboBox()
        self._canfd_arb.addItems(["125000", "250000", "500000", "1000000"])
        self._canfd_arb.setCurrentIndex(2)
        self._canfd_data_br = QComboBox()
        self._canfd_data_br.addItems(["500000", "1000000", "2000000", "4000000", "8000000"])
        self._canfd_data_br.setCurrentIndex(1)
        self._canfd_format = QComboBox()
        self._canfd_format.addItems(["standard → 标准帧", "extended → 扩展帧"])
        f.addRow("通道", self._canfd_ch)
        f.addRow("仲裁域波特率", self._canfd_arb)
        f.addRow("数据域波特率", self._canfd_data_br)
        f.addRow("帧格式", self._canfd_format)
        for c in [self._canfd_ch, self._canfd_arb, self._canfd_data_br, self._canfd_format]:
            if hasattr(c, 'textChanged'):
                c.textChanged.connect(lambda: self._save_current())
            elif hasattr(c, 'currentIndexChanged'):
                c.currentIndexChanged.connect(lambda: self._save_current())
        return w

    def _build_protocol_page(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        # Protocol basics
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

        # Frame config (placeholder — ProtocolEditor handles detailed editing)
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

    # ── Show object ──

    def show_object(self, project: Project, obj_type: str, obj_id: str):
        self._project = project
        self._current_type = obj_type
        self._current_id = obj_id

        if obj_type == "project":
            self._show_project(project)
            self._stack.setCurrentIndex(1)
        elif obj_type == "node":
            node = project.find_node(obj_id)
            if node:
                self._show_node(node)
                self._stack.setCurrentIndex(2)
        elif obj_type == "interface":
            result = project.find_interface(obj_id)
            if result:
                self._show_interface(result[1])
                self._stack.setCurrentIndex(3)
        elif obj_type == "protocol":
            proto = self._find_protocol(obj_id)
            if proto:
                self._show_protocol(proto)
                self._stack.setCurrentIndex(4)
        elif obj_type == "status_var":
            result = project.find_status_var(obj_id)
            if result:
                self._show_status_var(result[1])
                self._stack.setCurrentIndex(2)
        else:
            self._stack.setCurrentIndex(0)

    def _show_project(self, proj: Project):
        self._proj_name.setText(proj.name)
        self._proj_version.setText(proj.version)
        self._proj_author.setText(proj.author)
        self._proj_endian.setCurrentIndex(0 if proj.endian == Endian.BIG else 1)
        self._proj_desc.setPlainText(proj.description)

    def _show_node(self, node: Node):
        self._node_name.setText(node.name)
        self._node_desc.setPlainText(node.description)

    def _show_status_var(self, sv: StatusVariable):
        self._node_name.setText(sv.name)
        self._node_desc.setPlainText(f"数据类型: {sv.data_type.value}, 字节长度: {sv.byte_length}\n单位: {sv.unit}\n含义: {sv.meaning}\n备注: {sv.remarks}")

    def _show_interface(self, iface: Interface):
        self._if_name.setText(iface.name)
        type_idx = {"ethernet": 0, "rs422": 1, "rs232": 2, "can": 3, "canfd": 4}
        self._if_type.setCurrentIndex(type_idx.get(iface.type.value, 1))
        self._on_if_type_changed(self._if_type.currentIndex())

        params = iface.params
        if isinstance(params, RS422Params):
            self._uart_port.setText(params.port_name)
            self._uart_baud.setCurrentText(str(params.baud_rate))
            self._uart_data.setCurrentText(str(params.data_bits))
            self._uart_stop.setCurrentText(str(params.stop_bits))
            self._uart_parity.setCurrentIndex(
                {"none": 0, "odd": 1, "even": 2}.get(params.parity.value, 0)
            )
        elif isinstance(params, RS232Params):
            self._uart_port.setText(params.port_name)
            self._uart_baud.setCurrentText(str(params.baud_rate))
            self._uart_data.setCurrentText(str(params.data_bits))
            self._uart_stop.setCurrentText(str(params.stop_bits))
            self._uart_parity.setCurrentIndex(
                {"none": 0, "odd": 1, "even": 2}.get(params.parity.value, 0)
            )
            self._uart_flow.setCurrentIndex(
                {"none": 0, "rts_cts": 1, "xon_xoff": 2}.get(params.flow_control.value, 0)
            )
        elif isinstance(params, EthernetParams):
            self._eth_ip.setText(params.ip)
            self._eth_port.setValue(params.port)
            self._eth_proto.setCurrentText(params.protocol)
            self._eth_mac.setText(params.mac_addr)
        elif isinstance(params, CANParams):
            self._can_ch.setText(params.channel)
            self._can_bitrate.setCurrentText(str(params.bitrate))
            self._can_format.setCurrentIndex(0 if params.frame_format == "standard" else 1)
            self._can_term.setChecked(params.termination)
        elif isinstance(params, CANFDParams):
            self._canfd_ch.setText(params.channel)
            self._canfd_arb.setCurrentText(str(params.arb_bitrate))
            self._canfd_data_br.setCurrentText(str(params.data_bitrate))
            self._canfd_format.setCurrentIndex(0 if params.frame_format == "standard" else 1)

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

    def _on_if_type_changed(self, idx: int):
        # idx: 0=rs422, 1=rs232, 2=eth, 3=can, 4=canfd
        self._if_param_stack.setCurrentIndex(idx)

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

    # ── Save back ──

    def _save_current(self):
        if not self._project:
            return
        if self._current_type == "project":
            self._save_project()
        elif self._current_type == "node":
            self._save_node()
        elif self._current_type == "interface":
            self._save_interface()
        elif self._current_type == "protocol":
            self._save_protocol()
        self.data_modified.emit()

    def _save_project(self):
        self._project.name = self._proj_name.text()
        self._project.version = self._proj_version.text()
        self._project.author = self._proj_author.text()
        self._project.endian = Endian.BIG if self._proj_endian.currentIndex() == 0 else Endian.LITTLE
        self._project.description = self._proj_desc.toPlainText()

    def _save_node(self):
        node = self._project.find_node(self._current_id)
        if node:
            node.name = self._node_name.text()
            node.description = self._node_desc.toPlainText()

    def _save_interface(self):
        result = self._project.find_interface(self._current_id)
        if not result:
            return
        _, iface = result
        iface.name = self._if_name.text()
        type_idx = self._if_type.currentIndex()

        if type_idx <= 1:  # RS422 or RS232
            port = self._uart_port.text()
            baud = int(self._uart_baud.currentText())
            data_bits = int(self._uart_data.currentText())
            stop_bits = float(self._uart_stop.currentText())
            parity = [Parity.NONE, Parity.ODD, Parity.EVEN][self._uart_parity.currentIndex()]
            if type_idx == 0:  # RS422
                iface.type = InterfaceType.RS422
                iface.params = RS422Params(port_name=port, baud_rate=baud, data_bits=data_bits,
                                            stop_bits=stop_bits, parity=parity)
            else:
                iface.type = InterfaceType.RS232
                flow = [FlowControl.NONE, FlowControl.RTS_CTS, FlowControl.XON_XOFF][self._uart_flow.currentIndex()]
                iface.params = RS232Params(port_name=port, baud_rate=baud, data_bits=data_bits,
                                            stop_bits=stop_bits, parity=parity, flow_control=flow)
        elif type_idx == 2:
            iface.type = InterfaceType.ETHERNET
            iface.params = EthernetParams(ip=self._eth_ip.text(), port=self._eth_port.value(),
                                          protocol=self._eth_proto.currentText(), mac_addr=self._eth_mac.text())
        elif type_idx == 3:
            iface.type = InterfaceType.CAN
            iface.params = CANParams(channel=self._can_ch.text(), bitrate=int(self._can_bitrate.currentText()),
                                     frame_format="standard" if self._can_format.currentIndex() == 0 else "extended",
                                     termination=self._can_term.isChecked())
        elif type_idx == 4:
            iface.type = InterfaceType.CANFD
            iface.params = CANFDParams(channel=self._canfd_ch.text(), arb_bitrate=int(self._canfd_arb.currentText()),
                                       data_bitrate=int(self._canfd_data_br.currentText()),
                                       frame_format="standard" if self._canfd_format.currentIndex() == 0 else "extended")

    def _save_protocol(self):
        proto = self._find_protocol(self._current_id)
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

    def _find_protocol(self, proto_id: str):
        if not self._project:
            return None
        for node in self._project.nodes:
            for iface in node.interfaces:
                for proto in iface.protocols:
                    if proto.id == proto_id:
                        return proto
        return None
