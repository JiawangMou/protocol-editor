"""CRC and checksum algorithms for protocol validation."""


def _reflect(data: int, nbits: int) -> int:
    """Reflect (reverse) the lower nbits of data."""
    result = 0
    for i in range(nbits):
        if data & (1 << i):
            result |= 1 << (nbits - 1 - i)
    return result


def crc8(data: bytes, poly: int = 0x07, init: int = 0x00, refin: bool = False,
         refout: bool = False, xorout: int = 0x00) -> int:
    crc = init
    for byte in data:
        b = _reflect(byte, 8) if refin else byte
        crc ^= b
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ poly) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    if refout:
        crc = _reflect(crc, 8)
    return crc ^ xorout


def crc16_ccitt(data: bytes) -> int:
    poly = 0x1021
    crc = 0xFFFF
    for byte in data:
        crc ^= (byte << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ poly) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def crc16_modbus(data: bytes) -> int:
    poly = 0x8005
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = ((crc >> 1) ^ poly) & 0xFFFF
            else:
                crc = (crc >> 1) & 0xFFFF
    return crc


def crc32(data: bytes) -> int:
    poly = 0xEDB88320
    crc = 0xFFFFFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = ((crc >> 1) ^ poly) & 0xFFFFFFFF
            else:
                crc = (crc >> 1) & 0xFFFFFFFF
    return crc ^ 0xFFFFFFFF


def sum8(data: bytes) -> int:
    return sum(data) & 0xFF


def xor8(data: bytes) -> int:
    result = 0
    for b in data:
        result ^= b
    return result


CRC_FUNCTIONS = {
    "crc8": crc8,
    "crc16_ccitt": crc16_ccitt,
    "crc16_modbus": crc16_modbus,
    "crc32": crc32,
    "sum8": sum8,
    "xor8": xor8,
}

CRC_NAMES = {
    "crc8": "CRC-8",
    "crc16_ccitt": "CRC-16/CCITT",
    "crc16_modbus": "CRC-16/MODBUS",
    "crc32": "CRC-32",
    "sum8": "SUM-8 (校验和)",
    "xor8": "XOR-8 (异或校验)",
}


def compute_crc(crc_type: str, data: bytes) -> int:
    fn = CRC_FUNCTIONS.get(crc_type)
    if fn is None:
        return 0
    return fn(data)
