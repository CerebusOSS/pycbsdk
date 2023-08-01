import struct
from pycbsdk.cbhw import config

config.protocol = "4.1"
from pycbsdk.cbhw.packet import packets


def test_pkt_base_structure():
    """
    Verify that there are no unexpected offsets in the packet structure.
    """
    cumu_bytes = 0
    for f, t in packets.CBPacketGeneric._fields_:
        a = getattr(packets.CBPacketGeneric, f)
        assert a.offset == cumu_bytes
        cumu_bytes += a.size


def test_pkt_base_init_without_data():
    pkt = packets.CBPacketGeneric()
    assert pkt.data == []
    assert pkt.header.chid == 0
    assert pkt.header.type == packets.CBPacketType.SYSHEARTBEAT
    assert pkt.header.dlen == 0


def test_pkt_base_init_with_data():
    header_bytes = b"\x01\x00\x00\x00\x00\x00\x00\x00\x02\x00\x03\x00\x04\x00\x05\x06"
    pkt_bytes = header_bytes + b"\xa0\xa1\xa2\xa3"
    pkt1 = packets.CBPacketGeneric(pkt_bytes)
    pkt2 = packets.CBPacketGeneric(bytes(pkt1))
    for pkt in [pkt1, pkt2]:
        assert pkt.data == [int.from_bytes(pkt_bytes[16:], "little")]


def test_pkt_base_modify_data():
    pkt = packets.CBPacketGeneric()
    N = 4
    new_data = list(range(N))
    pkt.data = new_data
    # Note that pkt.data is a generic payload with 32-bit values,
    # unlike channel data which would have 16-bit values.
    assert pkt.data == new_data
    assert pkt.header.dlen == N
    assert bytes(pkt._array) == struct.pack(f"{N}i", *new_data)
