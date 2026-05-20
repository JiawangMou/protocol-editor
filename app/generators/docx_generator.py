"""Word 文档生成器 — 导出协议文档"""
from __future__ import annotations
from datetime import datetime

from docx import Document
from docx.shared import Inches, Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn

from app.models.protocol import (
    Project, Node, Interface, Protocol, StatusVariable, Connection,
    UARTFrameConfig, CANFrameConfig, EthernetFrameConfig,
    EthernetParams, RS422Params, RS232Params, CANParams, CANFDParams,
)
from app.models.enums import *

CATEGORY_NAMES = {
    ProtocolCategory.CONTROL_REQUEST: "控制/请求指令",
    ProtocolCategory.PERIODIC_REPORT: "周期上报消息",
    ProtocolCategory.STATUS_CHANGE: "状态变化上报消息",
    ProtocolCategory.EXECUTION_FEEDBACK: "执行结果反馈消息",
}

DTYPE_SIZES = {
    DataType.UINT8: 1, DataType.UINT16: 2, DataType.UINT32: 4, DataType.UINT64: 8,
    DataType.INT8: 1, DataType.INT16: 2, DataType.INT32: 4, DataType.INT64: 8,
    DataType.FLOAT: 4, DataType.DOUBLE: 8, DataType.BOOL: 1, DataType.STRING: 0,
}

COMM_METHODS = {
    "control_request": "请求-应答",
    "periodic_report": "周期发送",
    "status_change": "变化触发",
    "execution_feedback": "应答返回",
}


def _set_cell_bg(cell, color):
    shading = cell._element.get_or_add_tcPr()
    shading_elm = shading.makeelement(qn('w:shd'), {
        qn('w:fill'): color,
        qn('w:val'): 'clear',
    })
    shading.append(shading_elm)


def _add_styled_table(doc, headers, rows, col_widths=None):
    """Add a styled table with header row."""
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.style = 'Light Grid Accent 1'
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    # Header
    for i, h in enumerate(headers):
        cell = table.rows[0].cells[i]
        cell.text = h
        for p in cell.paragraphs:
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for run in p.runs:
                run.bold = True
                run.font.size = Pt(9)

    # Data
    for r, row_data in enumerate(rows):
        for c, val in enumerate(row_data):
            cell = table.rows[r + 1].cells[c]
            cell.text = str(val) if val is not None else ""
            for p in cell.paragraphs:
                for run in p.runs:
                    run.font.size = Pt(9)

    doc.add_paragraph()
    return table


def generate_docx(project: Project, output_path: str):
    doc = Document()

    # ── Default font ──
    style = doc.styles['Normal']
    style.font.name = 'Microsoft YaHei'
    style.font.size = Pt(10)

    # ── Cover ──
    for _ in range(6):
        doc.add_paragraph()
    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run(project.name or "通讯协议文档")
    run.bold = True
    run.font.size = Pt(28)

    info = doc.add_paragraph()
    info.alignment = WD_ALIGN_PARAGRAPH.CENTER
    info.add_run(f"\n版本: {project.version}").font.size = Pt(12)

    info.add_run(f"\n作者: {project.author or '—'}").font.size = Pt(12)
    info.add_run(f"\n日期: {datetime.now().strftime('%Y-%m-%d')}").font.size = Pt(12)
    info.add_run(f"\n全局字节序: {'大端 (Big-Endian)' if project.endian == Endian.BIG else '小端 (Little-Endian)'}").font.size = Pt(12)

    doc.add_page_break()

    # ── 1. Overview ──
    doc.add_heading('一、工程概述', level=1)
    _add_styled_table(doc,
        ["项目", "内容"],
        [
            ["工程名称", project.name],
            ["版本", project.version],
            ["作者", project.author],
            ["全局字节序", "大端" if project.endian == Endian.BIG else "小端"],
            ["节点数量", str(len(project.nodes))],
            ["连线数量", str(len(project.connections))],
        ]
    )

    if project.description:
        doc.add_paragraph(f"描述: {project.description}")

    # ── 2. Network Topology ──
    doc.add_heading('二、网络拓扑', level=1)
    if project.connections:
        rows = []
        for conn in project.connections:
            from_name = ""
            to_name = ""
            for n in project.nodes:
                if n.id == conn.from_node_id:
                    from_name = n.name
                    for i in n.interfaces:
                        if i.id == conn.from_interface_id:
                            from_name += f" ({i.name})"
                if n.id == conn.to_node_id:
                    to_name = n.name
                    for i in n.interfaces:
                        if i.id == conn.to_interface_id:
                            to_name += f" ({i.name})"
            rows.append([from_name, "→", to_name, conn.label])
        _add_styled_table(doc,
            ["源节点 (接口)", "方向", "目标节点 (接口)", "标注"],
            rows,
        )

    # Node list
    for node in project.nodes:
        doc.add_heading(f'2.{project.nodes.index(node) + 1} 节点: {node.name}', level=2)
        _add_styled_table(doc,
            ["属性", "内容"],
            [
                ["节点名称", node.name],
                ["描述", node.description or "—"],
                ["接口数量", str(len(node.interfaces))],
                ["状态量数量", str(len(node.status_variables))],
            ]
        )

    # ── 3. Status Variables ──
    doc.add_heading('三、状态量定义', level=1)
    for node in project.nodes:
        if not node.status_variables:
            continue
        doc.add_heading(f'3.{project.nodes.index(node) + 1} {node.name}', level=2)

        rows = []
        for sv in node.status_variables:
            ref_count = project.status_var_ref_count(sv.id)
            rows.append([
                sv.name, sv.data_type.value, str(sv.byte_length),
                sv.unit, sv.meaning, sv.remarks, str(ref_count),
            ])
        _add_styled_table(doc,
            ["名称", "数据类型", "字节长度", "单位", "含义", "备注", "引用数"],
            rows,
        )

    # ── 4. Communication Interfaces ──
    doc.add_heading('四、通讯接口参数', level=1)
    for node in project.nodes:
        if not node.interfaces:
            continue
        doc.add_heading(f'4.{project.nodes.index(node) + 1} {node.name}', level=2)

        for iface in node.interfaces:
            doc.add_heading(f'接口: {iface.name} ({iface.type.value.upper()})', level=3)

            params = iface.params
            rows = []
            if isinstance(params, RS422Params):
                rows = [
                    ["类型", "RS-422"],
                    ["端口号", params.port_name],
                    ["波特率", str(params.baud_rate)],
                    ["数据位", str(params.data_bits)],
                    ["停止位", str(params.stop_bits)],
                    ["校验位", {"none": "无", "odd": "奇校验", "even": "偶校验"}.get(params.parity.value, "")],
                ]
            elif isinstance(params, RS232Params):
                rows = [
                    ["类型", "RS-232"],
                    ["端口号", params.port_name],
                    ["波特率", str(params.baud_rate)],
                    ["数据位", str(params.data_bits)],
                    ["停止位", str(params.stop_bits)],
                    ["校验位", {"none": "无", "odd": "奇校验", "even": "偶校验"}.get(params.parity.value, "")],
                    ["流控", {"none": "无", "rts_cts": "RTS/CTS", "xon_xoff": "XON/XOFF"}.get(params.flow_control.value, "")],
                ]
            elif isinstance(params, EthernetParams):
                rows = [
                    ["类型", "Ethernet"],
                    ["IP 地址", params.ip],
                    ["端口号", str(params.port)],
                    ["协议", params.protocol.upper()],
                    ["MAC 地址", params.mac_addr or "—"],
                ]
            elif isinstance(params, CANParams):
                rows = [
                    ["类型", "CAN"],
                    ["通道", params.channel],
                    ["波特率", str(params.bitrate)],
                    ["帧格式", "标准帧 (11-bit)" if params.frame_format == "standard" else "扩展帧 (29-bit)"],
                    ["终端电阻", "已启用" if params.termination else "未启用"],
                ]
            elif isinstance(params, CANFDParams):
                rows = [
                    ["类型", "CAN FD"],
                    ["通道", params.channel],
                    ["仲裁域波特率", str(params.arb_bitrate)],
                    ["数据域波特率", str(params.data_bitrate)],
                    ["帧格式", "标准帧" if params.frame_format == "standard" else "扩展帧"],
                ]
            _add_styled_table(doc, ["参数", "值"], rows)

    # ── 5. Protocol Definitions ──
    doc.add_heading('五、通讯协议定义', level=1)
    for node in project.nodes:
        for iface in node.interfaces:
            if not iface.protocols:
                continue
            doc.add_heading(f'5.{project.nodes.index(node) + 1}.{node.interfaces.index(iface) + 1} {node.name} — {iface.name} ({iface.type.value.upper()})', level=2)

            for proto in iface.protocols:
                cat_name = CATEGORY_NAMES.get(proto.category, proto.category.value)
                doc.add_heading(f'协议: {proto.name} ({cat_name})', level=3)

                # Protocol basic
                _add_styled_table(doc,
                    ["属性", "值"],
                    [
                        ["协议名称", proto.name],
                        ["分类", cat_name],
                        ["通讯方式", proto.comm_method],
                        ["上报周期", f"{proto.report_period_ms} ms" if proto.category == ProtocolCategory.PERIODIC_REPORT else "—"],
                        ["变化阈值", proto.change_threshold or "—"],
                    ]
                )

                # Frame config
                cfg = proto.frame_config
                doc.add_heading('帧格式参数', level=4)

                if isinstance(cfg, UARTFrameConfig):
                    _add_styled_table(doc,
                        ["参数", "值"],
                        [
                            ["同步字长度", f"{cfg.sync_word_len} 字节"],
                            ["同步字内容", cfg.sync_word],
                            ["消息ID偏移", str(cfg.msg_id_offset)],
                            ["消息ID长度", f"{cfg.msg_id_len} 字节"],
                            ["帧长度字段偏移", str(cfg.frame_len_offset) if cfg.frame_len_offset >= 0 else "未使用"],
                            ["帧长度字段长度", f"{cfg.frame_len_len} 字节"],
                            ["帧长度含义", cfg.frame_len_meaning.value],
                            ["数据区偏移", str(cfg.data_offset)],
                            ["数据区最大长度", f"{cfg.data_max_len} 字节"],
                            ["CRC校验类型", cfg.crc_type.value],
                            ["校验字偏移", f"{cfg.crc_offset}" if cfg.crc_offset >= 0 else "帧尾"],
                            ["校验范围", f"[{cfg.crc_range_start}, {cfg.crc_range_end})"],
                            ["停止标志", cfg.stop_flag or "无"],
                            ["字节序", "大端" if cfg.endian == Endian.BIG else "小端"],
                        ]
                    )
                elif isinstance(cfg, CANFrameConfig):
                    _add_styled_table(doc,
                        ["参数", "值"],
                        [
                            ["仲裁域ID", cfg.arbitration_id],
                            ["帧类型", cfg.frame_type.value],
                            ["DLC", str(cfg.dlc)],
                            ["BRS", "启用" if cfg.brs else "未启用"],
                        ]
                    )
                elif isinstance(cfg, EthernetFrameConfig):
                    _add_styled_table(doc,
                        ["参数", "值"],
                        [
                            ["协议", cfg.protocol],
                            ["头部长度", f"{cfg.header_len} 字节"],
                            ["消息类型偏移", str(cfg.msg_type_offset)],
                            ["消息类型长度", f"{cfg.msg_type_len} 字节"],
                            ["序列号偏移", str(cfg.seq_offset)],
                            ["数据长度偏移", str(cfg.data_len_offset)],
                            ["数据区偏移", str(cfg.data_offset)],
                            ["数据区最大长度", f"{cfg.data_max_len} 字节"],
                            ["CRC校验类型", cfg.crc_type.value],
                            ["校验字偏移", str(cfg.crc_offset)],
                        ]
                    )

                # Field definitions
                if proto.fields:
                    doc.add_heading('字段定义', level=4)
                    field_rows = []
                    offset = 0
                    for fld in proto.fields:
                        source_name_map = {
                            "status_var": "状态量引用",
                            "constant": "常量",
                            "calculated": "计算值",
                            "custom": "自定义",
                        }
                        field_rows.append([
                            fld.name,
                            fld.data_type.value,
                            str(fld.byte_length),
                            str(offset),
                            source_name_map.get(fld.source.value, fld.source.value),
                            fld.status_var_ref or fld.constant_value or "—",
                            fld.description,
                        ])
                        offset += fld.byte_length
                    _add_styled_table(doc,
                        ["字段名", "数据类型", "字节长度", "偏移", "来源", "绑定/值", "描述"],
                        field_rows,
                    )

    # ── 6. Appendix ──
    doc.add_heading('六、附录: CRC 校验算法说明', level=1)
    doc.add_paragraph("本协议中可能使用的校验算法如下:")
    crc_info = [
        ("CRC-8", "多项式 0x07, 初始值 0x00, 8位", "短帧快速校验"),
        ("CRC-16/CCITT", "多项式 0x1021, 初始值 0xFFFF, 16位", "XMODEM, 通用数据通讯"),
        ("CRC-16/MODBUS", "多项式 0x8005, 初始值 0xFFFF, 16位, 低位在前", "Modbus RTU 协议"),
        ("CRC-32", "多项式 0xEDB88320, 初始值 0xFFFFFFFF, 32位", "Ethernet, ZIP, PNG"),
        ("SUM-8", "字节累加, 取低8位", "简单校验和"),
        ("XOR-8", "字节异或, 8位", "快速异或校验"),
    ]
    _add_styled_table(doc, ["算法", "参数", "典型应用"], crc_info)

    # ── Save ──
    doc.save(output_path)
