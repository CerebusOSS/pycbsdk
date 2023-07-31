import struct
from pycbsdk.cbhw import packet


def test_pkt_base_structure():
    """
    Verify that there are no unexpected offsets in the packet structure.
    """
    cumu_bytes = 0
    for f, t in packet.CBPacketGeneric._fields_:
        a = getattr(packet.CBPacketGeneric, f)
        assert a.offset == cumu_bytes
        cumu_bytes += a.size


def test_pkt_base_init_without_data():
    pkt = packet.CBPacketGeneric()
    assert pkt.data == []
    assert pkt.header.chid == 0
    assert pkt.header.type == packet.CBPacketType.SYSHEARTBEAT
    assert pkt.header.dlen == 0


def test_pkt_base_init_with_data():
    pkt_bytes = b"\x01\x00\x00\x00\x02\x00\x03\x04\xa0\xa1\xa2\xa3"
    pkt1 = packet.CBPacketGeneric(pkt_bytes)
    pkt2 = packet.CBPacketGeneric(bytes(pkt1))
    for pkt in [pkt1, pkt2]:
        assert pkt.header.time == 1
        assert (
            pkt.header.chid == 2
        )  # Probably incorrect, but it was set from the buffer so this is expected.
        assert (
            pkt.header.type == 3
        )  # Unlikely type, but it was set from the buffer so this is expected.
        assert (
            pkt.header.dlen == 4
        )  # Technically incorrect, but it was set from the buffer so this is expected.
        assert pkt.data == [int.from_bytes(pkt_bytes[8:], "little")]


def test_pkt_base_modify_data():
    pkt = packet.CBPacketGeneric()
    N = 4
    new_data = list(range(N))
    pkt.data = new_data
    assert pkt.data == new_data
    assert pkt.header.dlen == N
    assert bytes(pkt._array) == struct.pack(f"{N}l", *new_data)
